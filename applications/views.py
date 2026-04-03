"""
applications/views.py

E3 — Status change notification emails:
    When a company updates an application status via either:
        - update_application_status  (inline dropdown in applicants table)
        - application_detail         (full status form on detail page)

    …the candidate receives an email notifying them of the change.

    The email:
        - Is only sent when the status actually changes (not on same-status saves)
        - Uses EmailMultiAlternatives (plain-text + HTML)
        - Has a per-status message:
              pending     → "Your application is under review"
              reviewed    → "Your application has been reviewed"
              shortlisted → Congratulations message
              rejected    → Thank you for applying message
              hired       → Offer details will follow message
              withdrawn   → Confirmation of withdrawal (candidate-initiated)
        - Is sent fire-and-forget (try/except) — a broken email backend
          never blocks the status update from saving
        - HTML body rendered from applications/email/status_change.html
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.http import Http404
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

# Per-status copy shown in the email body.
# Keys match Application.Status values exactly.
_STATUS_MESSAGES = {
    Application.Status.PENDING: {
        "subject_suffix": "is under review",
        "headline":       "Your application is under review",
        "body":           (
            "Thank you for your patience. Our team is currently reviewing "
            "your application and will be in touch with an update soon."
        ),
        "color":  "#fcd34d",   # amber — mirrors .badge-pending
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
        "color":  "#a5b4fc",   # indigo — mirrors .badge-reviewed
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
        "color":  "#6ee7b7",   # emerald — mirrors .badge-shortlisted
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
        "color":  "#fca5a5",   # red — mirrors .badge-rejected
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
        "color":  "#34d399",   # bright emerald — mirrors .badge-hired
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
        "color":  "#d1d5db",   # slate — mirrors .badge-withdrawn
        "border": "rgba(156,163,175,0.38)",
        "bg":     "rgba(156,163,175,0.15)",
    },
}


def _send_status_notification(application):
    """
    Send a status-change notification email to the candidate.

    Called after application.status has been updated and saved.
    Silently swallows all exceptions so a broken email backend
    never prevents the status update from completing.

    Args:
        application: Application instance with the NEW status already saved.
    """
    candidate_user = application.candidate.user
    email          = candidate_user.email

    if not email:
        return   # nothing to send to

    copy    = _STATUS_MESSAGES.get(application.status)
    if not copy:
        return   # unknown status — skip

    name    = candidate_user.get_full_name() or candidate_user.username
    company = application.job.company
    subject = f"{application.job.title} at {company.company_name} {copy['subject_suffix']}"

    # ── Plain-text body ───────────────────────────────────────────────────
    text_body = (
        f"Hi {name},\n\n"
        f"{copy['headline']}\n\n"
        f"Job:     {application.job.title}\n"
        f"Company: {company.company_name}\n"
        f"Status:  {application.get_status_display()}\n\n"
        f"{copy['body']}\n\n"
        f"— The hirepath team"
    )

    # ── HTML body — rendered from dedicated template ──────────────────────
    html_body = render_to_string(
        "applications/email/status_change.html",
        {
            "name":        name,
            "application": application,
            "job":         application.job,
            "company":     company,
            "copy":        copy,
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
        pass   # never block the status save because of email failure


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
        # E3: notify candidate of withdrawal confirmation
        _send_status_notification(application)
        messages.info(request, f'Application to "{job_title}" withdrawn.')
        return redirect("candidate_dashboard")

    return render(request, "applications/withdraw_confirm.html", {"application": application})


# ─── Company: View applicants ───────────────────────────────────────────────

@login_required
def view_applicants(request, job_id):
    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)
    applications = (
        job.applications
           .select_related("candidate__user", "resume")
           .exclude(status=Application.Status.WITHDRAWN)
           .order_by("-match_score", "-applied_at")
    )

    status_filter = request.GET.get("status", "")
    if status_filter:
        applications = applications.filter(status=status_filter)

    return render(request, "applications/view_applicants.html", {
        "job":            job,
        "applications":   applications,
        "status_choices": Application.Status.choices,
        "status_filter":  status_filter,
        "total":          job.applications.exclude(status=Application.Status.WITHDRAWN).count(),
    })


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

            # E3: send notification only when the status actually changed
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
    })


@login_required
def update_application_status(request, application_id):
    """
    Inline status update from the applicants table dropdown.
    E3: sends a notification email when the status changes.
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
                # E3: notify candidate — only fires when status actually changed
                _send_status_notification(application)
            # If same status selected, skip save and notification silently

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
    """
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

    return render(request, "applications/old_application_list.html", {
        "applications": applications,
    })