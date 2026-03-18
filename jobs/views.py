from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import Job
from .forms import JobForm, JobFilterForm


# ─── Helpers ────────────────────────────────────────────────────────────────

def _company_required(request):
    """Return the CompanyProfile or None. Used as a guard."""
    return getattr(request.user, "companyprofile", None)


# ─── Public views ───────────────────────────────────────────────────────────

def job_list(request):
    """Browseable job board — visible to everyone."""
    jobs = Job.objects.filter(status=Job.Status.OPEN).select_related("company")
    filter_form = JobFilterForm(request.GET)

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
        "jobs": jobs,
        "filter_form": filter_form,
        "total": jobs.count(),
    })


def job_detail(request, job_id):
    """Full job detail page."""
    job = get_object_or_404(Job, id=job_id)

    # Check if current user has already applied
    already_applied = False
    if request.user.is_authenticated and hasattr(request.user, "candidateprofile"):
        already_applied = job.applications.filter(
            candidate=request.user.candidateprofile
        ).exists()

    return render(request, "jobs/job_detail.html", {
        "job": job,
        "already_applied": already_applied,
    })


# ─── Company-only views ─────────────────────────────────────────────────────

@login_required
def create_job(request):
    company = _company_required(request)
    if not company:
        messages.error(request, "Only company accounts can post jobs.")
        return redirect("candidate_dashboard")

    if request.method == "POST":
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.company = company
            job.save()
            form.save_m2m()   # handles M2M via the custom save override
            form.save(commit=True)  # runs the skills resolution
            messages.success(request, f'"{job.title}" posted successfully.')
            return redirect("job_detail", job_id=job.id)
    else:
        form = JobForm()

    return render(request, "jobs/create_job.html", {"form": form, "editing": False})


@login_required
def edit_job(request, job_id):
    company = _company_required(request)
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
        "form": form,
        "job": job,
        "editing": True,
    })


@login_required
def delete_job(request, job_id):
    company = _company_required(request)
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
    """Quick open ↔ closed toggle from the dashboard."""
    company = _company_required(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    if request.method == "POST":
        if job.status == Job.Status.OPEN:
            job.status = Job.Status.CLOSED
            messages.info(request, f'"{job.title}" is now closed.')
        else:
            job.status = Job.Status.OPEN
            messages.success(request, f'"{job.title}" is now open.')
        job.save(update_fields=["status"])

    return redirect(request.META.get("HTTP_REFERER", "company_dashboard"))


@login_required
def company_job_list(request):
    """Company's own job management view (all statuses)."""
    company = _company_required(request)
    if not company:
        return redirect("candidate_dashboard")

    jobs = company.jobs.prefetch_related("skills", "applications").order_by("-created_at")
    return render(request, "jobs/company_job_list.html", {"jobs": jobs, "company": company})