"""
screening/views.py

FIX #10:
    company_base.html navbar avatar uses {{ company }} to render the
    company logo or initials.  Views that extend company_base.html but
    don't pass 'company' in their render context cause the avatar to
    render blank.

    Affected views in this file:
        screening_dashboard      — added 'company': company to render context
        screening_result_detail  — added 'company': company to render context

    Views that only redirect (no render call) are unaffected:
        run_screening  — redirects to view_applicants after processing

FIX #15:
    screening/ranking.html existed but had no backing view or URL.
    Added ranking(request, job_id) view that fetches all ScreeningResults
    for a job ordered by similarity_score desc and renders ranking.html.
    Only the owning company can access it.
"""

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
    Only redirects — no render call — so no company context needed here.
    """
    company = _company_required(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    if request.method != "POST":
        return redirect("view_applicants", job_id=job.id)

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

        if not created:
            result.status = ScreeningResult.Status.PROCESSING
            result.save(update_fields=["status"])

        try:
            score_data = compute_match_score(app.resume.file, job)

            result.similarity_score     = score_data["score"]
            result.extracted_skills     = score_data.get("extracted_skills", "")
            result.matched_skills       = score_data.get("matched_skills", "")
            result.missing_skills       = score_data.get("missing_skills", "")
            result.summary              = score_data.get("summary", "")
            result.status               = ScreeningResult.Status.DONE
            result.error_message        = ""
            result.skill_score          = score_data.get("skill_score", 0)
            result.experience_score     = score_data.get("experience_score", 0)
            result.qualification_score  = score_data.get("qualification_score", 0)
            result.cosine_score         = score_data.get("cosine_score", 0)
            result.save()

            app.match_score = result.similarity_score
            app.score_notes = result.summary
            app.save(update_fields=["match_score", "score_notes"])

            processed += 1

        except Exception as e:
            result.status        = ScreeningResult.Status.FAILED
            result.error_message = str(e)
            result.save(update_fields=["status", "error_message"])
            failed += 1

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

    applications = (
        job.applications
           .select_related("candidate__user", "resume", "screening_result")
           .exclude(status="withdrawn")
           .order_by("-match_score", "-applied_at")
    )

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
        # FIX #10: pass company so company_base.html navbar avatar renders correctly
        "company":      company,
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
        # FIX #10: pass company so company_base.html navbar avatar renders correctly
        "company":     company,
    })


# ─── FIX #15: Candidate Ranking (per job) ────────────────────────────────────

@login_required
def ranking(request, job_id):
    """
    FIX #15: screening/ranking.html existed as an orphaned template with no
    backing view or URL registration.

    This view:
        - Guards to the owning company only.
        - Fetches all ScreeningResults for the job ordered by similarity_score
          desc (highest match first), excluding withdrawn applications.
        - Passes 'results', 'job', and 'company' to the template so the
          existing ranking.html design renders correctly without any changes.

    The ranking page is linked from the screening_dashboard and
    view_applicants pages via {% url 'ranking' job.id %}.
    """
    company = _company_required(request)
    if not company:
        return redirect("candidate_dashboard")

    job = get_object_or_404(Job, id=job_id, company=company)

    results = (
        ScreeningResult.objects
        .filter(
            application__job=job,
            status=ScreeningResult.Status.DONE,
        )
        .exclude(application__status="withdrawn")
        .select_related(
            "application__candidate__user",
            "application__job",
        )
        .order_by("-similarity_score", "-screened_at")
    )

    return render(request, "screening/ranking.html", {
        "job":     job,
        "results": results,
        "company": company,
    })