"""
jobs/views.py
═══════════════════════════════════════════════════════════════════════════════
JOBS APP — COMPLETE

  Public views (no login required):
    job_list    → /jobs/
    job_detail  → /jobs/<id>/

  Company-only views (login + companyprofile required):
    create_job        → /jobs/create/
    edit_job          → /jobs/<id>/edit/
    delete_job        → /jobs/<id>/delete/
    toggle_job_status → /jobs/<id>/toggle/
    company_job_list  → /jobs/manage/

REMINDER — Step 3 (applications app):
  job_detail uses `already_applied` — this works once Application model exists.
  No changes needed here; it's already guarded with hasattr().

REMINDER — Step 4 (screening app):
  run_screening is in screening/views.py, not here.
  The screening dashboard link in company_job_list will work once
  screening URLs are wired.
═══════════════════════════════════════════════════════════════════════════════
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count

from .models import Job
from .forms import JobForm, JobFilterForm


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_company(request):
    """Return CompanyProfile or None. Used as a guard in company-only views."""
    return getattr(request.user, "companyprofile", None)


# ── Public views ─────────────────────────────────────────────────────────────

def job_list(request):
    """
    Browseable job board — visible to everyone, no login required.
    Supports search + filter via GET params.
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

    return render(request, "jobs/job_list.html", {
        "jobs":        jobs,
        "filter_form": filter_form,
        "total":       jobs.count(),
    })


def job_detail(request, job_id):
    """
    Full job detail page — visible to everyone.
    Shows Apply button for logged-in candidates, Edit for owning company.
    """
    job = get_object_or_404(Job.objects.select_related("company").prefetch_related("skills"), id=job_id)

    already_applied = False
    if request.user.is_authenticated and hasattr(request.user, "candidateprofile"):
        # REMINDER — Step 3: this query works once applications app exists
        already_applied = job.applications.filter(
            candidate=request.user.candidateprofile
        ).exists()

    return render(request, "jobs/job_detail.html", {
        "job":            job,
        "already_applied": already_applied,
    })


# ── Company-only views ───────────────────────────────────────────────────────

# @login_required
def create_job(request):
    """
    HR creates a new job posting.

    BUG FIX: Previous version called form.save() twice —
      job.save() then form.save(commit=True) — causing duplicate saves.
    Correct pattern: save(commit=False) → set company → save() → save_m2m()
    """
    company = _get_company(request)
    if not company:
        messages.error(request, "Only company accounts can post jobs.")
        return redirect("candidate_dashboard")

    if request.method == "POST":
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)   # build instance, don't hit DB yet
            job.company = company           # attach company before saving
            job.save()                      # save to DB exactly once
            # Manually resolve skills from skills_input (normally done in JobForm.save())
            # We replicate the logic here because we used commit=False above
            raw_skills = form.cleaned_data.get("skills_input", "")
            from .models import Skill
            skill_names = [s.strip() for s in raw_skills.split(",") if s.strip()]
            skill_objs = []
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
    })


# @login_required
def edit_job(request, job_id):
    """HR edits an existing job. Only the owning company can edit."""
    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    if request.method == "POST":
        form = JobForm(request.POST, instance=job)
        if form.is_valid():
            form.save()   # JobForm.save() handles skills resolution correctly
            messages.success(request, "Job updated successfully.")
            return redirect("job_detail", job_id=job.id)
    else:
        form = JobForm(instance=job)

    return render(request, "jobs/create_job.html", {
        "form":    form,
        "job":     job,
        "editing": True,
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
    Quick open ↔ closed toggle.
    POST only — called from buttons in company_job_list and company_dashboard.
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


# @login_required
def company_job_list(request):
    """
    Company's full job management page — all statuses, with applicant counts.

    REMINDER — Step 3 (applications app):
      application_count annotation works once applications app is created.
      The Count("applications") below will return 0 until then — no crash.
    """
    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    jobs = (
        company.jobs
        .prefetch_related("skills")
        .annotate(application_count=Count("applications"))
        .order_by("-created_at")
    )

    # Split by status for the tab counts in the template
    open_count   = jobs.filter(status=Job.Status.OPEN).count()
    draft_count  = jobs.filter(status=Job.Status.DRAFT).count()
    closed_count = jobs.filter(status=Job.Status.CLOSED).count()

    return render(request, "jobs/company_job_list.html", {
        "jobs":         jobs,
        "company":      company,
        "open_count":   open_count,
        "draft_count":  draft_count,
        "closed_count": closed_count,
    })