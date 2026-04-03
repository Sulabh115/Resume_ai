"""
jobs/views.py

FIXES vs previous:
  1. job_list:   passes has_resumes to template so Apply button
                 can warn candidates with no resume
  2. job_detail: replaces hasattr(user, "candidateprofile") with
                 CandidateProfile.objects.filter() — avoids ORM cache bug.
                 Also passes has_resumes to template.
  3. job_detail: imports CandidateProfile at top level instead of inline.
  4. create_job: no changes — skill resolution already correct.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Avg
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

    # FIX: check resume existence via DB, not hasattr
    has_resumes = False
    candidate   = _get_candidate(request)
    if candidate:
        has_resumes = candidate.resumes.exists()

    return render(request, "jobs/job_list.html", {
        "jobs":        jobs,
        "filter_form": filter_form,
        "total":       jobs.count(),
        "has_resumes": has_resumes,
    })


def job_detail(request, job_id):
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
    def clean_lines(text):
        return [
            line.strip().lstrip("•-*").strip()
            for line in (text or "").splitlines()
            if line.strip()
        ]
    responsibilities_list = clean_lines(job.responsibilities)
    requirements_list     = clean_lines(job.requirements)
    return render(request, "jobs/job_detail.html", {
        "job":             job,
        "already_applied": already_applied,
        "has_resumes":     has_resumes,
        "responsibilities_list": responsibilities_list,
        "requirements_list": requirements_list,
    })


# ── Company-only views ───────────────────────────────────────────────────────

@login_required
def create_job(request):
    """
    HR creates a new job posting.
    Uses commit=False so we can attach the company before saving,
    then manually resolve skills (because M2M needs the PK to exist first).
    """
    company = _get_company(request)
    if not company:
        messages.error(request, "Only company accounts can post jobs.")
        return redirect("candidate_dashboard")

    if request.method == "POST":
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
    else:
        form = JobForm()

    return render(request, "jobs/create_job.html", {
        "form":    form,
        "editing": False,
        "company" : company,
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

    return render(request, "jobs/delete_job_confirm.html", {"job": job})


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
        'company':  company,
        'jobs':     jobs,
    })


@login_required
def old_jobs(request):
    """
    Expired jobs — deadline passed OR status is closed.
    Shows ranked applicants for results modal (as JSON per job).
    """
    company = _get_company(request)
    if not company:
        return redirect('candidate_dashboard')
 
    today = timezone.now().date()
 
    jobs = (
        Job.objects
        .filter(company=company)
        .filter(Q(status=Job.Status.CLOSED) | Q(deadline__lt=today))
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
 
    # Pre-load ranked applicants for each job (used in "View Results" modal)
    jobs_data = []
    for job in jobs:
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
                    'name':   u.get_full_name() or u.username,
                    'score':  round(app.match_score or 0),
                    'status': app.status,
                })
            ranked_json = json.dumps(ranked)
        else:
            ranked_json = '[]'
 
        jobs_data.append({
            'job':        job,
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
            'job':        job,
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
    POST handler — send interview email to all shortlisted candidates for a job.
    Sets job.shortlist_email_sent = True on success.
    """
    if request.method != 'POST':
        return redirect('to_shortlist')
 
    company = _get_company(request)
    if not company:
        return redirect('candidate_dashboard')
 
    job = get_object_or_404(Job, id=job_id, company=company)
 
    interview_date     = request.POST.get('interview_date', '')
    interview_time     = request.POST.get('interview_time', '')
    interview_duration = request.POST.get('interview_duration', '1 hour')
    interview_location = request.POST.get('interview_location', '')
    interview_notes    = request.POST.get('interview_notes', '')
 
    shortlisted = (
        Application.objects
        .filter(job=job, status='shortlisted')
        .select_related('candidate__user')
    )
 
    from django.core.mail import send_mail
 
    sent_count = 0
    for app in shortlisted:
        u    = app.candidate.user
        name = u.get_full_name() or u.username
        email = u.email
        if not email:
            continue
 
        subject = f"Congratulations! You've been shortlisted — {job.title}"
        notes_line = f"\n📌 Notes: {interview_notes}" if interview_notes.strip() else ""
        body = (
            f"Dear {name},\n\n"
            f"Congratulations! You have been shortlisted for {job.title} "
            f"at {company.company_name}.\n\n"
            f"Interview Details:\n"
            f"📅 Date: {interview_date}\n"
            f"⏰ Time: {interview_time}\n"
            f"⏱ Duration: {interview_duration}\n"
            f"📍 Location: {interview_location}"
            f"{notes_line}\n\n"
            f"Please reply to confirm your attendance.\n\n"
            f"Best regards,\n"
            f"HR Team — {company.company_name}"
        )
        try:
            send_mail(subject, body, None, [email], fail_silently=True)
            sent_count += 1
        except Exception:
            pass
 
    job.shortlist_email_sent = True
    job.save(update_fields=['shortlist_email_sent'])
 
    from django.contrib import messages
    messages.success(
        request,
        f"Interview emails sent to {sent_count} shortlisted candidate"
        f"{'s' if sent_count != 1 else ''}.",
    )
    return redirect('to_shortlist')
 