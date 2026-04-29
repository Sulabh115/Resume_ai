"""
jobs/views.py

FIX #16 (job_detail):
    The template job_detail.html used:
        {% if request.user.companyprofile == job.company %}

    This crashes with AttributeError for any candidate user because
    Django's ORM raises RelatedObjectDoesNotExist (a subclass of
    AttributeError) when accessing a reverse OneToOne that doesn't exist.

    Fix: compute a safe is_owner boolean in the view and pass it in
    context.  The template then uses {% if is_owner %} everywhere.

    is_owner is True only when:
        - the user is authenticated
        - the user has a CompanyProfile (DB query, avoids ORM cache bug)
        - that profile is the one that owns this job

FIX C2 (job_list — Fix #2, assumed done):
    job_list.html previously used:
        {% elif request.user.companyprofile == job.company %}
    which raises RelatedObjectDoesNotExist for any candidate or anonymous
    viewer, crashing the entire job board.

    Fix: compute user_company = _get_company(request) in job_list() and
    pass it in context.  The template then uses:
        {% elif user_company and user_company == job.company %}
    which is safe for all viewer types.

FIX E2 (send_shortlist_email — Fix #3):
    reply_to=[company.user.email] if company.user.email else None
    passes [''] (empty string in a list, not None) when the email field
    exists but is blank.  EmailMultiAlternatives then forwards the empty
    string to the SMTP server which rejects the message.

    Fix: also check .strip() so a blank string is treated as absent:
        reply_to=[company.user.email] if (company.user.email and
                  company.user.email.strip()) else None

FIXES vs previous:
  1. job_list:   passes has_resumes to template so Apply button
                 can warn candidates with no resume
  2. job_detail: replaces hasattr(user, "candidateprofile") with
                 CandidateProfile.objects.filter() — avoids ORM cache bug.
                 Also passes has_resumes to template.
  3. job_detail: imports CandidateProfile at top level instead of inline.
  4. create_job: no changes — skill resolution already correct.

FIX #3:
  old_jobs view previously built ranked_json as a bare list of
  {name, score, status} dicts.  The JS openModal() in old_jobs.html
  reads data.title, data.total, data.shortlisted, data.applicants —
  none of which existed.  ranked_json is now a dict with those four
  keys so the modal renders correctly.

FIX #6:
  old_jobs.html references job.avg_score_offset to set the SVG ring
  stroke-dashoffset.  The view annotates avg_score via Avg() but never
  computed avg_score_offset, so the ring always showed a full circle.
  avg_score_offset is now computed in the loop:
      offset = 94.2 * (1 - avg_score / 100)
  where 94.2 is the circumference of the r=15 SVG circle.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.db.models import Q, Count, Avg
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.models import CandidateProfile, CompanyProfile
from .models import Job, Skill
from .forms import JobForm, JobFilterForm
from applications.models import Application
import json


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_company(request):
    """Return CompanyProfile or None. Used as a guard in company-only views."""
    return CompanyProfile.objects.filter(user=request.user).first()


def _get_candidate(request):
    """Return CandidateProfile or None. DB query — avoids ORM cache bug."""
    if not request.user.is_authenticated:
        return None
    return CandidateProfile.objects.filter(user=request.user).first()


# ── Public views ─────────────────────────────────────────────────────────────

def job_list(request):
    """
    Browseable job board — visible to everyone, no login required.
    Supports search + filter via GET params.

    FIX C2: passes user_company in context so the template can safely
    check whether the viewer owns each job without hitting
    request.user.companyprofile directly (which raises for candidates
    and anonymous users).

    FIX: passes has_resumes to template so the Apply button can
    redirect candidates without a resume to the resume manager.
    """
    jobs = (
        Job.objects
        .filter(status=Job.Status.OPEN)
        .select_related("company")
        .prefetch_related("skills")
    )
    filter_form = JobFilterForm(request.GET or None)

    if filter_form.is_valid():
        q          = filter_form.cleaned_data.get("q")
        job_type   = filter_form.cleaned_data.get("job_type")
        experience = filter_form.cleaned_data.get("experience")
        location   = filter_form.cleaned_data.get("location")

        if q:
            jobs = jobs.filter(
                Q(title__icontains=q) |
                Q(company__company_name__icontains=q) |
                Q(skills__name__icontains=q) |
                Q(description__icontains=q)
            ).distinct()

        if job_type:
            jobs = jobs.filter(job_type=job_type)

        if experience:
            jobs = jobs.filter(experience_required__gte=int(experience))

        if location:
            jobs = jobs.filter(location__icontains=location)

    has_resumes = False
    candidate   = _get_candidate(request)
    if candidate:
        has_resumes = candidate.resumes.exists()

    # FIX C2: safe company check — never access request.user.companyprofile
    # directly in the template because it raises RelatedObjectDoesNotExist
    # for any non-company viewer.  Pass user_company (None for candidates /
    # anonymous users) so job_list.html can use:
    #   {% elif user_company and user_company == job.company %}
    user_company = _get_company(request) if request.user.is_authenticated else None

    return render(request, "jobs/job_list.html", {
        "jobs":         jobs,
        "filter_form":  filter_form,
        "total":        jobs.count(),
        "has_resumes":  has_resumes,
        "user_company": user_company,   # FIX C2
    })


def job_detail(request, job_id):
    """
    FIX #16: compute is_owner safely via a DB query rather than
    accessing request.user.companyprofile directly.

    Accessing a missing reverse OneToOne relation raises
    RelatedObjectDoesNotExist (subclass of AttributeError), which
    crashes the page for any candidate or anonymous user.

    is_owner is True iff:
        - the request user is authenticated
        - the user has a CompanyProfile in the DB
        - that CompanyProfile is the one that owns this job
    """
    job = get_object_or_404(
        Job.objects.select_related("company").prefetch_related("skills"),
        id=job_id
    )

    already_applied = False
    has_resumes     = False
    candidate       = _get_candidate(request)

    if candidate:
        already_applied = job.applications.filter(candidate=candidate).exists()
        has_resumes     = candidate.resumes.exists()

    # ── FIX #16: safe ownership check ────────────────────────────────────
    # Never use request.user.companyprofile — that raises for non-company users.
    # Use the _get_company helper which does a filtered DB lookup instead.
    is_owner = False
    if request.user.is_authenticated:
        viewer_company = _get_company(request)
        if viewer_company is not None:
            is_owner = (viewer_company.pk == job.company.pk)

    def clean_lines(text):
        return [
            line.strip().lstrip("•-*").strip()
            for line in (text or "").splitlines()
            if line.strip()
        ]

    responsibilities_list = clean_lines(job.responsibilities)
    requirements_list     = clean_lines(job.requirements)

    return render(request, "jobs/job_detail.html", {
        "job":                   job,
        "already_applied":       already_applied,
        "has_resumes":           has_resumes,
        "is_owner":              is_owner,
        "responsibilities_list": responsibilities_list,
        "requirements_list":     requirements_list,
    })


# ── Company-only views ───────────────────────────────────────────────────────

@login_required
def create_job(request):
    """
    HR creates a new job posting.
    Uses commit=False so we can attach the company before saving,
    then manually resolve skills (because M2M needs the PK to exist first).

    REPOST FIX:
        GET ?repost=<job_id> pre-populates the form from an existing job so
        HR can quickly re-list an expired posting without retyping everything.

        Fields carried over:  title, description, requirements,
                              responsibilities, experience_required,
                              qualification_required, location, job_type,
                              salary_min, salary_max, salary_currency, skills.

        Fields intentionally reset:
            deadline → blank   (old deadline is in the past, must set a new one)
            status   → OPEN    (new posting should be live immediately)
            results_published / shortlist_email_sent → False (new job, no history)

        The source job is looked up with company= guard so one company cannot
        repost another company's job.
    """
    company = _get_company(request)
    if not company:
        messages.error(request, "Only company accounts can post jobs.")
        return redirect("candidate_dashboard")

    repost_job = None

    if request.method == "POST":
        repost_id = request.POST.get("repost") or request.GET.get("repost")
        form = JobForm(request.POST)
        if form.is_valid():
            job         = form.save(commit=False)
            job.company = company
            job.save()

            raw_skills = form.cleaned_data.get("skills_input", "")
            skill_names = [s.strip() for s in raw_skills.split(",") if s.strip()]
            skill_objs  = []
            for name in skill_names:
                obj, _ = Skill.objects.get_or_create(
                    name__iexact=name, defaults={"name": name.title()}
                )
                skill_objs.append(obj)
            job.skills.set(skill_objs)

            messages.success(request, f'"{job.title}" posted successfully.')
            return redirect("job_detail", job_id=job.id)
        return render(request, "jobs/create_job.html", {
            "form":      form,
            "editing":   False,
            "company":   company,
            "is_repost": repost_id is not None,
        })
    else:
        # ── Repost: pre-populate form from an existing job ────────────────
        repost_id  = request.GET.get("repost")

        if repost_id:
            try:
                repost_job = Job.objects.get(id=int(repost_id), company=company)
            except (Job.DoesNotExist, ValueError, TypeError):
                repost_job = None

        if repost_job:
            initial = {
                "title":                  f"{repost_job.title}",
                "description":            repost_job.description,
                "requirements":           repost_job.requirements,
                "responsibilities":       repost_job.responsibilities,
                "experience_required":    repost_job.experience_required,
                "qualification_required": repost_job.qualification_required,
                "location":               repost_job.location,
                "job_type":               repost_job.job_type,
                "salary_min":             repost_job.salary_min,
                "salary_max":             repost_job.salary_max,
                "salary_currency":        repost_job.salary_currency,
                "status":                 Job.Status.OPEN,
                "deadline":               None,
                "skills_input":           ", ".join(
                                              repost_job.skills.values_list("name", flat=True)
                                          ),
            }
            form = JobForm(initial=initial)
            messages.info(
                request,
                f'Reposting "{repost_job.title}". '
                f'Update the deadline and make any other changes before publishing.'
            )
        else:
            form = JobForm()

    return render(request, "jobs/create_job.html", {
        "form":       form,
        "editing":    False,
        "company":    company,
        "is_repost":  repost_job is not None,
    })


@login_required
def edit_job(request, job_id):
    """HR edits an existing job. Only the owning company can edit."""
    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    if request.method == "POST":
        form = JobForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, "Job updated successfully.")
            return redirect("job_detail", job_id=job.id)
    else:
        form = JobForm(instance=job)

    return render(request, "jobs/create_job.html", {
        "form":    form,
        "job":     job,
        "editing": True,
        "company": company,
    })


@login_required
def delete_job(request, job_id):
    """
    HR deletes a job posting.
    GET → confirmation page.
    POST → delete and redirect to company dashboard.
    """
    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    if request.method == "POST":
        title = job.title
        job.delete()
        messages.success(request, f'"{title}" has been deleted.')
        return redirect("company_dashboard")

    # FIX #10: pass company so company_base.html navbar avatar renders correctly
    return render(request, "jobs/delete_job_confirm.html", {"job": job, "company": company})


@login_required
def toggle_job_status(request, job_id):
    """
    Quick open ↔ closed toggle (POST only).
    Redirects back to wherever the request came from.
    """
    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    if request.method == "POST":
        if job.status == Job.Status.OPEN:
            job.status = Job.Status.CLOSED
            messages.info(request, f'"{job.title}" closed.')
        elif job.status == Job.Status.CLOSED:
            job.status = Job.Status.OPEN
            messages.success(request, f'"{job.title}" is now open.')
        else:
            # Draft → Open
            job.status = Job.Status.OPEN
            messages.success(request, f'"{job.title}" published.')
        job.save(update_fields=["status"])

    return redirect(request.META.get("HTTP_REFERER", "company_dashboard"))


@login_required
def company_job_list(request):
    """
    Active jobs only — open or draft, deadline not yet past.
    Annotated with applicant_count and avg_score.
    """
    company = _get_company(request)
    if not company:
        return redirect('candidate_dashboard')

    today = timezone.now().date()

    jobs = (
        Job.objects
        .filter(company=company)
        .filter(Q(status=Job.Status.OPEN) | Q(status=Job.Status.DRAFT))
        .filter(Q(deadline__gte=today) | Q(deadline__isnull=True))
        .annotate(
            applicant_count=Count('applications', distinct=True),
            avg_score=Avg('applications__match_score'),
        )
        .order_by('-created_at')
    )

    return render(request, 'jobs/company_job_list.html', {
        'company': company,
        'jobs':    jobs,
    })


@login_required
def old_jobs(request):
    """
    Expired jobs — deadline passed OR status is closed.
    Shows ranked applicants for results modal (as JSON per job).

    FIX #3:
        ranked_json was previously a bare list of {name, score, status} dicts.
        openModal() in old_jobs.html reads:
            data.title        — job title for modal heading
            data.total        — total applicant count for stats strip
            data.shortlisted  — shortlisted count for stats strip
            data.applicants   — the ranked list array

        ranked_json is now a dict containing all four keys so the modal
        renders correctly.  When results are not yet published, an empty
        stub dict is stored so openModal() always receives a valid object.
    """
    company = _get_company(request)
    if not company:
        return redirect('candidate_dashboard')

    today = timezone.now().date()

    jobs = (
        Job.objects
        .filter(company=company)
        .filter(
            Q(status=Job.Status.CLOSED) |
            Q(deadline__lt=today, status=Job.Status.OPEN)
        )
        .annotate(
            applicant_count=Count('applications', distinct=True),
            shortlisted_count=Count(
                'applications',
                filter=Q(applications__status='shortlisted'),
                distinct=True,
            ),
            rejected_count=Count(
                'applications',
                filter=Q(applications__status='rejected'),
                distinct=True,
            ),
            avg_score=Avg('applications__match_score'),
        )
        .order_by('-deadline')
    )

    jobs_data = []
    for job in jobs:

        # FIX #6: compute avg_score_offset for the SVG ring in old_jobs.html.
        if job.avg_score is not None:
            job.avg_score_offset = round(94.2 * (1 - job.avg_score / 100), 1)
        else:
            job.avg_score_offset = 94.2

        if job.results_published:
            applicants_qs = (
                Application.objects
                .filter(job=job)
                .exclude(status='withdrawn')
                .select_related('candidate__user')
                .order_by('-match_score')
            )

            ranked = []
            for app in applicants_qs:
                u = app.candidate.user
                ranked.append({
                    'name':        u.get_full_name() or u.username,
                    'score':       round(app.match_score or 0),
                    'status':      app.status,
                    'shortlisted': app.status == 'shortlisted',
                })

            total_count       = len(ranked)
            shortlisted_count = sum(1 for a in ranked if a['shortlisted'])

            ranked_json = json.dumps({
                'title':       job.title,
                'total':       total_count,
                'shortlisted': shortlisted_count,
                'applicants':  ranked,
            })

        else:
            ranked_json = json.dumps({
                'title':       job.title,
                'total':       0,
                'shortlisted': 0,
                'applicants':  [],
            })

        jobs_data.append({
            'job':         job,
            'ranked_json': ranked_json,
        })

    return render(request, 'jobs/old_jobs.html', {
        'company':   company,
        'jobs_data': jobs_data,
    })


@login_required
def to_shortlist(request):
    """
    Jobs where results are published but the interview email hasn't been sent.
    Each item carries its shortlisted Application queryset for display.
    """
    company = _get_company(request)
    if not company:
        return redirect('candidate_dashboard')

    jobs = (
        Job.objects
        .filter(company=company, results_published=True, shortlist_email_sent=False)
        .annotate(applicant_count=Count('applications', distinct=True))
        .order_by('-deadline')
    )

    job_data = []
    for job in jobs:
        shortlisted = (
            Application.objects
            .filter(job=job, status='shortlisted')
            .select_related('candidate__user')
            .order_by('-match_score')
        )
        job_data.append({
            'job':         job,
            'shortlisted': shortlisted,
        })

    return render(request, 'jobs/to_shortlist.html', {
        'company':  company,
        'job_data': job_data,
        'total':    len(job_data),
    })


@login_required
def send_shortlist_email(request, job_id):
    """
    POST handler — send interview invitation emails to all shortlisted
    candidates for a job.

    FIX E2 (Fix #3):
        reply_to=[company.user.email] if company.user.email else None
        was passing [''] (empty string in a list) when the HR account's
        email field exists but is blank.  EmailMultiAlternatives then
        forwards '' as a Reply-To header value and some SMTP servers
        reject the message.

        Fix: guard with .strip() so a whitespace-only or empty email is
        treated identically to None:
            reply_to = [company.user.email] if (
                company.user.email and company.user.email.strip()
            ) else None

    Other improvements:
      - Per-recipient try/except so individual failures don't abort batch.
      - EmailMultiAlternatives sends plain-text + HTML in one message.
      - Tracks sent_count, no_email_count, and error_count separately.
      - Sets job.shortlist_email_sent = True only when at least one
        email succeeded.
    """
    if request.method != 'POST':
        return redirect('to_shortlist')

    company = _get_company(request)
    if not company:
        return redirect('candidate_dashboard')

    job = get_object_or_404(Job, id=job_id, company=company)

    interview_date     = request.POST.get('interview_date',     '')
    interview_time     = request.POST.get('interview_time',     '')
    interview_duration = request.POST.get('interview_duration', '1 hour')
    interview_location = request.POST.get('interview_location', '')
    interview_notes    = request.POST.get('interview_notes',    '')

    shortlisted = (
        Application.objects
        .filter(job=job, status='shortlisted')
        .select_related('candidate__user')
        .order_by('-match_score')
    )

    email_ctx_base = {
        'job':                job,
        'company':            company,
        'interview_date':     interview_date,
        'interview_time':     interview_time,
        'interview_duration': interview_duration,
        'interview_location': interview_location,
        'interview_notes':    interview_notes,
    }

    sent_count     = 0
    no_email_count = 0
    error_count    = 0

    for app in shortlisted:
        u     = app.candidate.user
        name  = u.get_full_name() or u.username
        email = u.email

        if not email:
            no_email_count += 1
            continue

        subject = f"You've been shortlisted — {job.title} at {company.company_name}"

        notes_line = f"\nNotes: {interview_notes}" if interview_notes.strip() else ""
        text_body = (
            f"Dear {name},\n\n"
            f"We are writing to inform you that you have been shortlisted for an interview "
            f"for the {job.title} position at {company.company_name}.\n\n"
            f"Your application has successfully passed our initial screening phase, and we "
            f"would like to invite you to discuss your qualifications further.\n\n"
            f"Interview Details:\n"
            f"Date:     {interview_date}\n"
            f"Time:     {interview_time}\n"
            f"Duration: {interview_duration}\n"
            f"Location: {interview_location}"
            f"{notes_line}\n\n"
            f"Please reply directly to this email at your earliest convenience to confirm "
            f"whether this schedule works for you.\n\n"
            f"Please note: Being shortlisted for an interview means you are moving forward "
            f"in our process, but is not an offer of employment.\n\n"
            f"Best regards,\n"
            f"The Hiring Team at {company.company_name}"
        )

        html_body = render_to_string(
            'jobs/email/shortlist_interview.html',
            {**email_ctx_base, 'candidate_name': name},
        )

        # FIX E2: guard against blank email string being passed as reply_to.
        # An empty string in the reply_to list causes SMTP rejection on many
        # providers.  Only include reply_to when the address is non-empty
        # after stripping whitespace.
        hr_email = company.user.email
        reply_to = [hr_email] if (hr_email and hr_email.strip()) else None

        try:
            msg = EmailMultiAlternatives(
                subject    = subject,
                body       = text_body,
                from_email = settings.DEFAULT_FROM_EMAIL,
                to         = [email],
                reply_to   = reply_to,
            )
            msg.attach_alternative(html_body, 'text/html')
            msg.send(fail_silently=False)
            sent_count += 1

        except Exception:
            error_count += 1

    if sent_count > 0:
        job.shortlist_email_sent = True
        job.save(update_fields=['shortlist_email_sent'])

    parts = []

    if sent_count:
        parts.append(
            f"Interview invitation sent to {sent_count} "
            f"candidate{'s' if sent_count != 1 else ''}."
        )
    if no_email_count:
        parts.append(
            f"{no_email_count} skipped — no email address on account."
        )
    if error_count:
        parts.append(
            f"{error_count} failed to send — check your email settings."
        )

    if sent_count > 0:
        messages.success(request, " ".join(parts))
    elif no_email_count and not error_count:
        messages.warning(
            request,
            f"No emails sent — none of the {no_email_count} shortlisted "
            f"candidate{'s have' if no_email_count != 1 else ' has'} "
            f"an email address on their account."
        )
    else:
        messages.error(
            request,
            "No emails could be sent. " + " ".join(parts)
        )

    return redirect('to_shortlist')


# ── FIX #2: Publish Results ──────────────────────────────────────────────────

@login_required
def publish_results(request, job_id):
    """
    POST only. Sets job.results_published = True and saves.

    Once results are published:
      - Candidates can see their rank and score on old_application_list (#3).
      - The job appears in the "To Shortlist" queue for interview emails.
      - The Publish Results button in view_applicants sidebar becomes disabled.

    Only the owning company can publish results for a job.
    Redirects back to view_applicants after saving.
    """
    if request.method != "POST":
        return redirect("view_applicants", job_id=job_id)

    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    if not job.results_published:
        job.results_published = True
        job.save(update_fields=["results_published"])
        messages.success(
            request,
            f'Results for "{job.title}" have been published. '
            f'Candidates can now see their ranking.'
        )
    else:
        messages.info(request, "Results have already been published for this job.")

    return redirect("view_applicants", job_id=job_id)
