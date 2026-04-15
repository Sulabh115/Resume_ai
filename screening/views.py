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

FIX #15:
    screening/ranking.html existed but had no backing view or URL.
    Added ranking(request, job_id) view.

S2 — run_screening null-resume guard:
    Application.resume is SET_NULL, so it can be None after a resume is
    deleted.  Previously the loop hit app.resume.file → AttributeError,
    which was silently caught, the ScreeningResult was marked FAILED, but
    no error_message was set so HR had no idea why.

    Fix: at the TOP of the loop, before touching app.resume.file, check
    whether app.resume is None.  If so, record a clear error_message,
    mark the result FAILED, and continue to the next application.

S3 — run_screening file-existence guard:
    Even when app.resume is not None, the physical PDF may have been moved
    or wiped from disk (e.g. storage migration, manual cleanup).
    fitz.open(missing_path) raises FileNotFoundError, which was caught
    silently just like S2.

    Fix: after confirming app.resume is not None, check
    os.path.exists(app.resume.file.path) before calling
    compute_match_score().  If the file is absent, mark FAILED with an
    informative error_message and continue.
"""

import os

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
    Triggers AI screening for all unscreened (or all, when force=1)
    applications on a job.  Only accessible by the company that owns the job.

    S2 guard: skips applications whose resume FK is None (deleted resume).
    S3 guard: skips applications where the PDF file is missing from disk.

    Both produce a FAILED ScreeningResult with a descriptive error_message
    instead of the previous silent failure.
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
        messages.info(
            request,
            "All applications have already been screened. "
            "Use 'Re-screen all' to force re-run."
        )
        return redirect("view_applicants", job_id=job.id)

    processed = 0
    failed    = 0

    for app in applications:
        result, created = ScreeningResult.objects.get_or_create(
            application=app,
            defaults={"status": ScreeningResult.Status.PENDING}
        )

        if not created:
            result.status = ScreeningResult.Status.PROCESSING
            result.save(update_fields=["status"])

        # ── S2: resume FK may be None when the Resume row was deleted ──────
        if app.resume is None:
            result.status        = ScreeningResult.Status.FAILED
            result.error_message = (
                "Resume is missing — the resume record was deleted after "
                "this application was submitted. The candidate must re-apply "
                "with a new resume, or HR can upload one on their behalf."
            )
            result.save(update_fields=["status", "error_message"])
            failed += 1
            continue

        # ── S3: physical PDF file may be absent from disk ──────────────────
        try:
            pdf_path = app.resume.file.path
        except Exception:
            pdf_path = None

        if not pdf_path or not os.path.exists(pdf_path):
            result.status        = ScreeningResult.Status.FAILED
            result.error_message = (
                f"Resume PDF not found on disk "
                f"(expected path: {pdf_path or 'unknown'}). "
                f"The file may have been moved or deleted during a storage "
                f"migration. Restore the file and re-run screening."
            )
            result.save(update_fields=["status", "error_message"])
            failed += 1
            continue

        # ── Normal screening path ──────────────────────────────────────────
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
            f"Screening complete. {processed} succeeded, {failed} failed. "
            f"Open the Screening Dashboard to see error details for failed applications."
        )
    elif failed and not processed:
        messages.error(
            request,
            f"Screening failed for all {failed} application(s). "
            f"Check the Screening Dashboard for error details "
            f"(missing resumes or PDF files are the most common cause)."
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
        "company":     company,
    })


# ─── FIX #15: Candidate Ranking (per job) ────────────────────────────────────

@login_required
def ranking(request, job_id):
    """
    Shows all ScreeningResults for a job ordered by similarity_score desc.
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