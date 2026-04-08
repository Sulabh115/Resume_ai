"""
applications/views.py

FIX #10:
    company_base.html navbar avatar uses {{ company }} to render the
    company logo or initials.  Views that extend company_base.html but
    don't pass 'company' in their render context cause the avatar to
    render blank (empty string, no logo, no initials).

    Affected views in this file:
        view_applicants      — added 'company': company to render context
        application_detail   — added 'company': company to render context
                               (both the GET render and the POST re-render
                               on form invalid already redirect, but the
                               GET path and the form-invalid re-render path
                               both need the key)

    Views that only redirect (no render call) are unaffected:
        update_application_status  — redirects only
        withdraw_application       — candidate-facing, uses candidate_base.html

E3 — Status change notification emails:
    When a company updates an application status via either:
        - update_application_status  (inline dropdown in applicants table)
        - application_detail         (full status form on detail page)

    …the candidate receives an email notifying them of the change.

FIX #8 — Pre-submission score preview:
    score_preview(request, job_id) accepts a resume file via multipart
    POST, runs compute_match_score against the job, and returns JSON:
        {
            score, skill_score, exp_score, qual_score, cosine_score,
            matched_skills, missing_skills
        }
    The candidate can trigger this from apply_job.html before submitting
    the actual application.  The uploaded file is never persisted — it is
    passed directly to compute_match_score (which calls
    extract_text_from_pdf on the InMemoryUploadedFile) and then
    discarded.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.http import Http404, JsonResponse
from django.template.loader import render_to_string
from datetime import date

from .models import Application, Resume
from .forms import ApplyJobForm, ResumeUploadForm, ApplicationStatusForm
from jobs.models import Job


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_candidate(request):
    return getattr(request.user, "candidateprofile", None)


def _get_company(request):
    return getattr(request.user, "companyprofile", None)


# ─── E3: Status notification email helper ───────────────────────────────────

_STATUS_MESSAGES = {
    Application.Status.PENDING: {
        "subject_suffix": "is under review",
        "headline":       "Your application is under review",
        "body":           (
            "Thank you for your patience. Our team is currently reviewing "
            "your application and will be in touch with an update soon."
        ),
        "color":  "#fcd34d",
        "border": "rgba(251,191,36,0.38)",
        "bg":     "rgba(251,191,36,0.15)",
    },
    Application.Status.REVIEWED: {
        "subject_suffix": "has been reviewed",
        "headline":       "Your application has been reviewed",
        "body":           (
            "Good news — our team has reviewed your application. "
            "We will contact you shortly with next steps."
        ),
        "color":  "#a5b4fc",
        "border": "rgba(99,102,241,0.38)",
        "bg":     "rgba(99,102,241,0.15)",
    },
    Application.Status.SHORTLISTED: {
        "subject_suffix": "— you've been shortlisted!",
        "headline":       "Congratulations — you've been shortlisted!",
        "body":           (
            "We are pleased to let you know that you have been shortlisted "
            "for this role. Our hiring team will reach out soon with "
            "details about the next steps, including interview scheduling."
        ),
        "color":  "#6ee7b7",
        "border": "rgba(16,185,129,0.38)",
        "bg":     "rgba(16,185,129,0.15)",
    },
    Application.Status.REJECTED: {
        "subject_suffix": "— application outcome",
        "headline":       "Thank you for applying",
        "body":           (
            "After careful consideration, we have decided not to move "
            "forward with your application at this time. We appreciate "
            "the time and effort you put into applying and encourage "
            "you to apply for future openings that match your profile."
        ),
        "color":  "#fca5a5",
        "border": "rgba(239,68,68,0.38)",
        "bg":     "rgba(239,68,68,0.15)",
    },
    Application.Status.HIRED: {
        "subject_suffix": "— offer incoming!",
        "headline":       "Great news — you've been selected!",
        "body":           (
            "Congratulations! We are delighted to inform you that you "
            "have been selected for this role. Our HR team will be in "
            "touch shortly with your offer details and onboarding "
            "information. Welcome to the team!"
        ),
        "color":  "#34d399",
        "border": "rgba(52,211,153,0.45)",
        "bg":     "rgba(52,211,153,0.20)",
    },
    Application.Status.WITHDRAWN: {
        "subject_suffix": "— withdrawal confirmed",
        "headline":       "Your withdrawal has been confirmed",
        "body":           (
            "This email confirms that your application has been withdrawn "
            "as requested. If you change your mind, feel free to apply "
            "again when a suitable opportunity arises."
        ),
        "color":  "#d1d5db",
        "border": "rgba(156,163,175,0.38)",
        "bg":     "rgba(156,163,175,0.15)",
    },
}


def _send_status_notification(application):
    """
    Send a status-change notification email to the candidate.
    Silently swallows all exceptions so a broken email backend
    never prevents the status update from completing.
    """
    candidate_user = application.candidate.user
    email          = candidate_user.email

    if not email:
        return

    copy = _STATUS_MESSAGES.get(application.status)
    if not copy:
        return

    name    = candidate_user.get_full_name() or candidate_user.username
    company = application.job.company
    subject = f"{application.job.title} at {company.company_name} {copy['subject_suffix']}"

    text_body = (
        f"Hi {name},\n\n"
        f"{copy['headline']}\n\n"
        f"Job:     {application.job.title}\n"
        f"Company: {company.company_name}\n"
        f"Status:  {application.get_status_display()}\n\n"
        f"{copy['body']}\n\n"
        f"— The hirepath team"
    )

    html_body = render_to_string(
        "applications/email/status_change.html",
        {
            "name":         name,
            "application":  application,
            "job":          application.job,
            "company":      company,
            "copy":         copy,
            "status_label": application.get_status_display(),
        },
    )

    try:
        msg = EmailMultiAlternatives(
            subject    = subject,
            body       = text_body,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
    except Exception:
        pass


# ─── Candidate: Apply ───────────────────────────────────────────────────────

@login_required
def apply_job(request, job_id):
    candidate = _get_candidate(request)
    if not candidate:
        messages.error(request, "Only candidate accounts can apply for jobs.")
        return redirect("company_dashboard")

    job = get_object_or_404(Job, id=job_id, status=Job.Status.OPEN)

    if Application.objects.filter(candidate=candidate, job=job).exists():
        return redirect("already_applied", job_id=job_id)

    if request.method == "POST":
        form = ApplyJobForm(candidate, request.POST, request.FILES)
        if form.is_valid():
            existing = form.cleaned_data.get("existing_resume")
            new_file = form.cleaned_data.get("new_resume")

            if new_file:
                resume_obj = Resume.objects.create(
                    candidate=candidate,
                    file=new_file,
                    label=form.cleaned_data.get("resume_label") or "",
                )
            else:
                resume_obj = existing

            Application.objects.create(
                candidate=candidate,
                job=job,
                resume=resume_obj,
                cover_letter=form.cleaned_data.get("cover_letter") or "",
            )
            messages.success(request, f'Application to "{job.title}" submitted successfully!')
            return redirect("candidate_dashboard")
    else:
        form = ApplyJobForm(candidate)

    return render(request, "applications/apply_job.html", {
        "form":        form,
        "job":         job,
        "has_resumes": Resume.objects.filter(candidate=candidate).exists(),
    })


@login_required
def already_applied(request, job_id):
    job = get_object_or_404(Job, id=job_id)
    return render(request, "applications/already_applied.html", {"job": job})


@login_required
def withdraw_application(request, application_id):
    candidate = _get_candidate(request)
    if not candidate:
        return redirect("company_dashboard")

    application = get_object_or_404(Application, id=application_id, candidate=candidate)

    if request.method == "POST":
        job_title = application.job.title
        application.status = Application.Status.WITHDRAWN
        application.save(update_fields=["status"])
        _send_status_notification(application)
        messages.info(request, f'Application to "{job_title}" withdrawn.')
        return redirect("candidate_dashboard")

    return render(request, "applications/withdraw_confirm.html", {"application": application})


# ─── FIX #8: Pre-submission score preview ────────────────────────────────────

@login_required
def score_preview(request, job_id):
    """
    POST only.  Accepts a resume file (multipart), runs compute_match_score
    against the specified job, and returns JSON:

        {
            "score":          float  (0–100, overall weighted score),
            "skill_score":    float  (0–100),
            "exp_score":      float  (0–100),
            "qual_score":     float  (0–100),
            "cosine_score":   float  (0–100),
            "matched_skills": list[str],
            "missing_skills": list[str],
        }

    On error returns {"error": "<message>"} with HTTP 400 or 500.

    The uploaded file is NEVER saved to disk — it is passed as an
    InMemoryUploadedFile directly to compute_match_score → extract_text_from_resume
    (which calls fitz.open() on the raw bytes via a temporary file path).
    Django writes InMemoryUploadedFile objects to a temp path automatically
    when they exceed FILE_UPLOAD_MAX_MEMORY_SIZE, so fitz.open() works
    on the .temporary_file_path() or via a NamedTemporaryFile helper.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    candidate = _get_candidate(request)
    if not candidate:
        return JsonResponse({"error": "Candidate account required"}, status=403)

    job = get_object_or_404(Job, id=job_id)

    resume_file = request.FILES.get("resume_file")
    if not resume_file:
        return JsonResponse({"error": "No resume file provided"}, status=400)

    # Validate file type (basic check — the screening engine accepts PDF)
    name_lower = resume_file.name.lower()
    if not (name_lower.endswith(".pdf") or name_lower.endswith(".doc") or name_lower.endswith(".docx")):
        return JsonResponse({"error": "Only PDF, DOC, and DOCX files are supported."}, status=400)

    # compute_match_score expects an object with a .path attribute (Django
    # FileField / InMemoryUploadedFile).  InMemoryUploadedFile exposes .read()
    # but NOT .path for small files.  We write to a NamedTemporaryFile so
    # fitz.open() can always read from a real path.
    import tempfile, os

    suffix = os.path.splitext(resume_file.name)[1] or ".pdf"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in resume_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        # Build a minimal file-like wrapper that exposes .path (needed by
        # extract_text_from_resume which calls resume_file.path internally).
        class _TmpFile:
            def __init__(self, path):
                self.path = path

        from screening.utils import compute_match_score
        result = compute_match_score(_TmpFile(tmp_path), job)

    except Exception as exc:
        return JsonResponse({"error": f"Screening failed: {exc}"}, status=500)
    finally:
        # Always clean up the temp file, even if compute_match_score raises.
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    matched = [s.strip() for s in result.get("matched_skills", "").split(",") if s.strip()]
    missing = [s.strip() for s in result.get("missing_skills", "").split(",") if s.strip()]

    return JsonResponse({
        "score":          result.get("score", 0),
        "skill_score":    result.get("skill_score", 0),
        "exp_score":      result.get("experience_score", 0),
        "qual_score":     result.get("qualification_score", 0),
        "cosine_score":   result.get("cosine_score", 0),
        "matched_skills": matched,
        "missing_skills": missing,
    })


# ─── Company: View applicants ───────────────────────────────────────────────

@login_required
def view_applicants(request, job_id):
    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    # All active (non-withdrawn) applications — used for counts
    all_active = job.applications.exclude(status=Application.Status.WITHDRAWN)

    applications = (
        all_active
        .select_related("candidate__user", "resume")
        .order_by("-match_score", "-applied_at")
    )

    status_filter = request.GET.get("status", "")
    if status_filter:
        applications = applications.filter(status=status_filter)

    # FIX #1: count unscreened applications for the warning banner.
    unscreened_count = all_active.filter(match_score=0).count()

    # FIX #4: shortlisted candidates for the email composition modal
    shortlisted_applications = (
        job.applications
           .filter(status=Application.Status.SHORTLISTED)
           .select_related("candidate__user")
           .order_by("-match_score")
    )

    return render(request, "applications/view_applicants.html", {
        "job":                      job,
        "applications":             applications,
        "status_choices":           Application.Status.choices,
        "status_filter":            status_filter,
        "total":                    all_active.count(),
        "company":                  company,
        "open_positions":           job.open_positions,
        "unscreened_count":         unscreened_count,
        # FIX #4: used to populate the email modal recipient list
        "shortlisted_applications": shortlisted_applications,
    })


# FIX #1: Bulk auto-shortlist

@login_required
def bulk_shortlist(request, job_id):
    """
    POST only. Marks top N applications (by match_score desc) as SHORTLISTED
    and the rest as REJECTED. HIRED applications are never overwritten.
    """
    if request.method != "POST":
        return redirect("view_applicants", job_id=job_id)

    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    try:
        top_n = int(request.POST.get("top_n", 0))
    except (ValueError, TypeError):
        top_n = 0

    if top_n <= 0:
        messages.warning(request, "Please enter a number of candidates to shortlist (must be >= 1).")
        return redirect("view_applicants", job_id=job_id)

    eligible = (
        job.applications
           .exclude(status__in=[
               Application.Status.WITHDRAWN,
               Application.Status.HIRED,
           ])
           .order_by("-match_score", "-applied_at")
    )

    total_eligible = eligible.count()

    if total_eligible == 0:
        messages.info(request, "No eligible applications to shortlist.")
        return redirect("view_applicants", job_id=job_id)

    top_n = min(top_n, total_eligible)

    all_ids       = list(eligible.values_list("id", flat=True))
    shortlist_ids = all_ids[:top_n]
    reject_ids    = all_ids[top_n:]

    shortlisted_count = Application.objects.filter(id__in=shortlist_ids).update(
        status=Application.Status.SHORTLISTED
    )
    rejected_count = Application.objects.filter(id__in=reject_ids).update(
        status=Application.Status.REJECTED
    )

    messages.success(
        request,
        f"Auto-shortlist complete: {shortlisted_count} shortlisted, "
        f"{rejected_count} marked as rejected."
    )
    return redirect("view_applicants", job_id=job_id)


@login_required
def application_detail(request, application_id):
    company = _get_company(request)
    if not company:
        raise Http404

    application = get_object_or_404(
        Application.objects.select_related("candidate__user", "job__company", "resume"),
        id=application_id,
        job__company=company,
    )

    if request.method == "POST":
        old_status = application.status
        form = ApplicationStatusForm(request.POST, instance=application)
        if form.is_valid():
            updated = form.save()
            messages.success(request, "Application status updated.")

            if updated.status != old_status:
                _send_status_notification(updated)

            return redirect("application_detail", application_id=application.id)
    else:
        form = ApplicationStatusForm(instance=application)

    skills_list = [
        s.strip()
        for s in (application.candidate.skills or "").split(",")
        if s.strip()
    ]
    return render(request, "applications/application_detail.html", {
        "application": application,
        "form":        form,
        "skills_list": skills_list,
        # FIX #10: pass company so company_base.html navbar avatar renders correctly
        "company":     company,
    })


@login_required
def update_application_status(request, application_id):
    """
    Inline status update from the applicants table dropdown.
    E3: sends a notification email when the status changes.
    Only redirects — no render call — so no company context needed.
    """
    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    application = get_object_or_404(Application, id=application_id, job__company=company)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in dict(Application.Status.choices):
            old_status = application.status

            if new_status != old_status:
                application.status = new_status
                application.save(update_fields=["status"])
                messages.success(
                    request,
                    f"Status updated to '{application.get_status_display()}'."
                )
                _send_status_notification(application)

    return redirect(request.META.get("HTTP_REFERER", "view_applicants"))


# ─── Resume Manager (candidate) ─────────────────────────────────────────────

@login_required
def resume_manager(request):
    candidate = _get_candidate(request)
    if not candidate:
        return redirect("company_dashboard")

    resumes = candidate.resumes.all()

    if request.method == "POST":
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            resume = form.save(commit=False)
            resume.candidate = candidate
            if resume.is_default:
                candidate.resumes.update(is_default=False)
            resume.save()
            messages.success(request, "Resume uploaded successfully.")
            return redirect("resume_manager")
    else:
        form = ResumeUploadForm()

    return render(request, "applications/resume_manager.html", {
        "resumes": resumes,
        "form":    form,
    })


@login_required
def delete_resume(request, resume_id):
    candidate = _get_candidate(request)
    if not candidate:
        return redirect("company_dashboard")

    resume = get_object_or_404(Resume, id=resume_id, candidate=candidate)

    if request.method == "POST":
        resume.file.delete(save=False)
        resume.delete()
        messages.success(request, "Resume deleted.")
    return redirect("resume_manager")


@login_required
def set_default_resume(request, resume_id):
    candidate = _get_candidate(request)
    if not candidate:
        return redirect("company_dashboard")

    resume = get_object_or_404(Resume, id=resume_id, candidate=candidate)

    if request.method == "POST":
        candidate.resumes.update(is_default=False)
        resume.is_default = True
        resume.save(update_fields=["is_default"])
        label = resume.label or resume.filename
        messages.success(request, f'"{label}" set as default resume.')

    return redirect("resume_manager")


# ─── Application lists (candidate) ──────────────────────────────────────────

@login_required
def application_list(request):
    """
    Candidate's active applications —
    excludes withdrawn, rejected, and jobs whose deadline has passed.
    """
    candidate = _get_candidate(request)
    if not candidate:
        return redirect("company_dashboard")

    from django.db.models import Q
    applications = (
        Application.objects
        .filter(candidate=candidate)
        .exclude(status__in=[
            Application.Status.WITHDRAWN,
            Application.Status.REJECTED,
        ])
        .exclude(job__deadline__lt=date.today())
        .select_related("job__company", "resume")
        .order_by("-applied_at")
    )

    return render(request, "applications/application_list.html", {
        "applications": applications,
    })


@login_required
def old_application_list(request):
    """
    Candidate's old/inactive applications —
    withdrawn, rejected, OR job deadline has passed.

    FIX #3:
    Each application is annotated with:
        rank              — candidate's position among all non-withdrawn applicants
                            for that job (ordered by match_score desc, 1-indexed).
        total             — total non-withdrawn applicant count for that job.
        shortlisted_count — number of shortlisted applicants for that job.
        results_published — from job.results_published.
        ranked_list       — when results_published, a JSON-safe list of all
                            applicants ordered by score. The current candidate
                            uses their real name; all others are anonymized as
                            "Candidate #N" to preserve privacy.
                            Empty list when results are not yet published.

    To avoid N+1 queries (one per application), all per-job data is fetched
    in a single pass grouped by job_id.
    """
    import json as _json
    candidate = _get_candidate(request)
    if not candidate:
        return redirect("company_dashboard")

    from django.db.models import Q
    applications = (
        Application.objects
        .filter(candidate=candidate)
        .filter(
            Q(status__in=[
                Application.Status.WITHDRAWN,
                Application.Status.REJECTED,
            ]) |
            Q(job__deadline__lt=date.today())
        )
        .select_related("job__company", "resume")
        .order_by("-applied_at")
    )

    # ── Per-job data — one queryset per unique job ────────────────────────
    # Collect unique job ids from the candidate's old applications.
    job_ids = list(applications.values_list("job_id", flat=True).distinct())

    # For each job, fetch ALL non-withdrawn applicants ordered by match_score.
    # Store in a dict keyed by job_id so template annotation is O(1) lookup.
    job_data_map = {}  # job_id → dict

    for job_id in job_ids:
        ranked_qs = (
            Application.objects
            .filter(job_id=job_id)
            .exclude(status=Application.Status.WITHDRAWN)
            .select_related("candidate__user")
            .order_by("-match_score", "applied_at")
        )

        all_apps       = list(ranked_qs)
        total          = len(all_apps)
        shortlisted_count = sum(
            1 for a in all_apps if a.status == Application.Status.SHORTLISTED
        )

        # Find this candidate's rank (1-indexed position in ranked list)
        rank = None
        for idx, a in enumerate(all_apps, start=1):
            if a.candidate_id == candidate.pk:
                rank = idx
                break

        # Build the published ranked list.
        # Other candidates are anonymized as "Candidate #N" (by rank position)
        # so no personal data about other applicants leaks to this candidate.
        job_obj = Application.objects.filter(job_id=job_id).first().job if all_apps else None
        results_published = job_obj.results_published if job_obj else False

        if results_published:
            ranked_list = []
            for idx, a in enumerate(all_apps, start=1):
                is_self = (a.candidate_id == candidate.pk)
                name = (
                    a.candidate.user.get_full_name() or a.candidate.user.username
                    if is_self
                    else f"Candidate #{idx}"
                )
                ranked_list.append({
                    "rank":        idx,
                    "name":        name,
                    "score":       round(a.match_score or 0),
                    "status":      a.status,
                    "shortlisted": a.status == Application.Status.SHORTLISTED,
                    "is_self":     is_self,
                })
        else:
            ranked_list = []

        job_data_map[job_id] = {
            "rank":              rank,
            "total":             total,
            "shortlisted_count": shortlisted_count,
            "results_published": results_published,
            "ranked_list_json":  _json.dumps(ranked_list),
        }

    # ── Build app_data — one entry per application ────────────────────────
    app_data = []
    for app in applications:
        jd = job_data_map.get(app.job_id, {})
        app_data.append({
            "app":              app,
            "rank":             jd.get("rank"),
            "total":            jd.get("total", 0),
            "shortlisted_count": jd.get("shortlisted_count", 0),
            "results_published": jd.get("results_published", False),
            "ranked_list_json": jd.get("ranked_list_json", "[]"),
        })

    return render(request, "applications/old_application_list.html", {
        "app_data": app_data,
    })