"""
applications/views.py

FIXES vs original:
  1. resume.filename()  → resume.filename   (it's a @property, not a method)
  2. render path        → "applications/resume_manager.html"
     (file was named resume_manage.html — rename the file to resume_manager.html)
  3. Application.Status.WITHDRAWN now valid after model update
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404

from .models import Application, Resume
from .forms import ApplyJobForm, ResumeUploadForm, ApplicationStatusForm
from jobs.models import Job


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_candidate(request):
    return getattr(request.user, "candidateprofile", None)


def _get_company(request):
    return getattr(request.user, "companyprofile", None)


# ─── Candidate: Apply ───────────────────────────────────────────────────────

@login_required
def apply_job(request, job_id):
    candidate = _get_candidate(request)
    if not candidate:
        messages.error(request, "Only candidate accounts can apply for jobs.")
        return redirect("company_dashboard")

    job = get_object_or_404(Job, id=job_id, status=Job.Status.OPEN)

    # Prevent duplicates
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
        # WITHDRAWN now valid on the model
        application.status = Application.Status.WITHDRAWN
        application.save(update_fields=["status"])
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
           .exclude(status=Application.Status.WITHDRAWN)   # WITHDRAWN now valid
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
        form = ApplicationStatusForm(request.POST, instance=application)
        if form.is_valid():
            form.save()
            messages.success(request, "Application status updated.")
            return redirect("application_detail", application_id=application.id)
    else:
        form = ApplicationStatusForm(instance=application)

    return render(request, "applications/application_detail.html", {
        "application": application,
        "form":        form,
    })


@login_required
def update_application_status(request, application_id):
    company = _get_company(request)
    if not company:
        return redirect("candidate_dashboard")

    application = get_object_or_404(Application, id=application_id, job__company=company)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in dict(Application.Status.choices):
            application.status = new_status
            application.save(update_fields=["status"])
            messages.success(request, f"Status updated to '{application.get_status_display()}'.")

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

    # NOTE: template file must be named "resume_manager.html"
    #       (was mistakenly named "resume_manage.html" in the repo — rename it)
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
        # FIX: resume.filename is a @property — was incorrectly called as resume.filename()
        label = resume.label or resume.filename
        messages.success(request, f'"{label}" set as default resume.')

    return redirect("resume_manager")