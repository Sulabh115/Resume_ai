from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from applications.models import Application
from jobs.models import Job
from .models import ScreeningResult

from .utils import compute_match_score


# ─── Helpers ────────────────────────────────────────────────────────────────

def _company_required(request):
    return getattr(request.user, "companyprofile", None)


# ─── Run Screening ──────────────────────────────────────────────────────────

@login_required
def run_screening(request, job_id):
    """
    Triggers AI screening for all unscreened applications on a job.
    Only accessible by the company that owns the job.
    Redirects back to the applicants page with a summary message.
    """
    company = _company_required(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    if request.method != "POST":
        return redirect("view_applicants", job_id=job.id)

    # Only screen applications that haven't been screened yet
    # (or re-screen all if ?force=1 is passed)
    force = request.GET.get("force") == "1"
    applications = job.applications.select_related("resume", "candidate__user")

    if not force:
        already_screened_ids = ScreeningResult.objects.filter(
            application__job=job
        ).values_list("application_id", flat=True)
        applications = applications.exclude(id__in=already_screened_ids)

    if not applications.exists():
        messages.info(request, "All applications have already been screened. Use 'Re-screen all' to force re-run.")
        return redirect("view_applicants", job_id=job.id)

    processed = 0
    failed = 0

    for app in applications:
        result, created = ScreeningResult.objects.get_or_create(
            application=app,
            defaults={"status": ScreeningResult.Status.PENDING}
        )

        # If re-screening an existing result, reset it to PROCESSING first
        if not created:
            result.status = ScreeningResult.Status.PROCESSING
            result.save(update_fields=["status"])

        try:
            score_data = compute_match_score(app.resume.file, job)

            result.similarity_score = score_data["score"]
            result.extracted_skills  = score_data.get("extracted_skills", "")
            result.matched_skills    = score_data.get("matched_skills", "")
            result.missing_skills    = score_data.get("missing_skills", "")
            result.summary           = score_data.get("summary", "")
            result.status            = ScreeningResult.Status.DONE
            result.error_message     = ""
            result.save()

            # Push score back to Application for dashboard sorting
            app.match_score = result.similarity_score
            app.score_notes = result.summary
            app.save(update_fields=["match_score", "score_notes"])

            processed += 1

        except Exception as e:
            result.status        = ScreeningResult.Status.FAILED
            result.error_message = str(e)
            result.save(update_fields=["status", "error_message"])
            failed += 1

    # Feedback message
    if failed and processed:
        messages.warning(
            request,
            f"Screening complete. {processed} succeeded, {failed} failed."
        )
    elif failed and not processed:
        messages.error(
            request,
            f"Screening failed for all {failed} application(s). Check resume files."
        )
    else:
        messages.success(
            request,
            f"Screening complete. {processed} application(s) scored successfully."
        )

    return redirect("view_applicants", job_id=job.id)


# ─── Screening Dashboard (per job) ──────────────────────────────────────────

@login_required
def screening_dashboard(request, job_id):
    """
    Full screening overview for a job — shows all results, scores,
    matched/missing skills, and lets the company re-run screening.
    """
    company = _company_required(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    # All applications with their screening result (if any)
    applications = (
        job.applications
           .select_related("candidate__user", "resume", "screening_result")
           .exclude(status="withdrawn")
           .order_by("-match_score", "-applied_at")
    )

    # Summary stats
    total    = applications.count()
    screened = ScreeningResult.objects.filter(
                    application__job=job,
                    status=ScreeningResult.Status.DONE
               ).count()
    pending  = total - screened
    strong   = ScreeningResult.objects.filter(
                    application__job=job,
                    status=ScreeningResult.Status.DONE,
                    similarity_score__gte=75
               ).count()

    return render(request, "screening/screening_dashboard.html", {
        "job":          job,
        "applications": applications,
        "total":        total,
        "screened":     screened,
        "pending":      pending,
        "strong":       strong,
    })


# ─── Single Screening Result ─────────────────────────────────────────────────

@login_required
def screening_result_detail(request, application_id):
    """
    Detailed view of one screening result — skill breakdown,
    score ring, summary. Accessible by the owning company only.
    """
    company = _company_required(request)
    if not company:
        return redirect("candidate_dashboard")

    application = get_object_or_404(
        Application.objects.select_related(
            "candidate__user", "job__company", "resume"
        ),
        id=application_id,
        job__company=company,
    )

    result = getattr(application, "screening_result", None)

    return render(request, "screening/screening_result_detail.html", {
        "application": application,
        "result":      result,
        "job":         application.job,
    })