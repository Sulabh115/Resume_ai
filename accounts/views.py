"""
accounts/views.py
═══════════════════════════════════════════════════════════════════════════════
  AUTH & PROFILE VIEWS FOR THE ACCOUNTS APP
───────────────────────────────────────────────────────────────────────────────
  CURRENT VIEWS (accounts app):
    register                → /accounts/register/
    user_login              → /accounts/login/
    user_logout             → /accounts/logout/
    forgot_password         → /accounts/forgot-password/
    candidate_dashboard     → /accounts/dashboard/candidate/
    company_dashboard       → /accounts/dashboard/company/
    candidate_edit_profile  → /accounts/profile/edit/
    company_edit_profile    → /accounts/profile/company/edit/
    delete_company_account  → /accounts/account/delete/

  FUTURE APPS — views will be added in their own apps/views.py:
    jobs app         → job_list, job_detail, create_job, company_job_list,
                        edit_job, delete_job, old_jobs
    applications app → apply_job, withdraw_application, view_applicants,
                        resume_manager, candidate_applications
    screening app    → run_screening, screening_results, to_shortlist
═══════════════════════════════════════════════════════════════════════════════
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count

from .models import CandidateProfile, CompanyProfile
from .forms import CandidateRegistrationForm, CompanyRegistrationForm, ForgotPasswordForm

# ── Imported here so dashboards can query across apps.
#    These imports will work once the jobs and applications apps are created.
#    If you haven't created those apps yet, comment these out temporarily
#    and uncomment them once you do.
from applications.models import Application
from jobs.models import Job


# ═══════════════════════════════════════════════════════════════
#  REGISTRATION
# ═══════════════════════════════════════════════════════════════

def register(request):
    """
    Single registration page for both candidate and company.
    Role is determined by a hidden <input name="role"> in the form.
    On failure, re-renders the combined page with errors so JS can
    auto-switch to the correct tab.
    """
    candidate_form = CandidateRegistrationForm()
    company_form   = CompanyRegistrationForm()

    if request.method == "POST":
        role = request.POST.get("role")

        if role == "candidate":
            candidate_form = CandidateRegistrationForm(request.POST)
            if candidate_form.is_valid():
                candidate_form.save()
                messages.success(request, "Account created! Please sign in.")
                return redirect("login")

        elif role == "company":
            company_form = CompanyRegistrationForm(request.POST)
            if company_form.is_valid():
                company_form.save()
                messages.success(request, "Company account created! Please sign in.")
                return redirect("login")

    return render(request, "accounts/register.html", {
        "candidate_form": candidate_form,
        "company_form":   company_form,
    })


# ═══════════════════════════════════════════════════════════════
#  AUTHENTICATION
# ═══════════════════════════════════════════════════════════════

def user_login(request):
    """
    Authenticates by username + password.
    Redirects to the correct dashboard based on profile type.
    If the user has neither profile (e.g. superuser), goes to /admin/.
    """
    # Already logged in — redirect to correct dashboard
    if request.user.is_authenticated:
        if hasattr(request.user, "candidateprofile"):
            return redirect("candidate_dashboard")
        if hasattr(request.user, "companyprofile"):
            return redirect("company_dashboard")
        return redirect("/admin/")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            if hasattr(user, "candidateprofile"):
                return redirect("candidate_dashboard")
            if hasattr(user, "companyprofile"):
                return redirect("company_dashboard")
            return redirect("/admin/")

        return render(request, "accounts/login.html", {
            "error": "Incorrect username or password."
        })

    return render(request, "accounts/login.html")


@login_required
def user_logout(request):
    logout(request)
    return redirect("login")


# ═══════════════════════════════════════════════════════════════
#  PASSWORD RESET
# ═══════════════════════════════════════════════════════════════

def forgot_password(request):
    """
    Step 1: collect email and show success screen.

    EMAIL SENDING — uncomment the block below once you configure
    Django email settings (EMAIL_BACKEND, EMAIL_HOST, etc.)
    The reset link uses Django's built-in token + uidb64 system and
    lands on the password_reset_confirm URL (already wired in urls.py).
    """
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]

            # ── EMAIL SENDING (implement when ready) ───────────────────
            # from django.contrib.auth.models import User
            # from django.contrib.auth.tokens import default_token_generator
            # from django.utils.http import urlsafe_base64_encode
            # from django.utils.encoding import force_bytes
            # from django.urls import reverse
            # from django.core.mail import send_mail
            #
            # try:
            #     user = User.objects.get(email=email)
            #     uid   = urlsafe_base64_encode(force_bytes(user.pk))
            #     token = default_token_generator.make_token(user)
            #     reset_url = request.build_absolute_uri(
            #         reverse("password_reset_confirm",
            #                 kwargs={"uidb64": uid, "token": token})
            #     )
            #     send_mail(
            #         subject="Reset your ResumeAI password",
            #         message=f"Click here to reset your password:\n{reset_url}",
            #         from_email=settings.DEFAULT_FROM_EMAIL,
            #         recipient_list=[email],
            #         fail_silently=False,
            #     )
            # except User.DoesNotExist:
            #     pass  # Never reveal whether the email is registered
            # ────────────────────────────────────────────────────────────

            return render(request, "accounts/forgot_password.html", {
                "form":             form,
                "email_sent":       True,
                "submitted_email":  email,
                "steps": [
                    "Open your email inbox.",
                    "Look for an email from ResumeAI.",
                    "Click the reset link — it's valid for 24 hours.",
                    "Choose a new password and sign in.",
                ],
            })

        return render(request, "accounts/forgot_password.html", {"form": form})

    return render(request, "accounts/forgot_password.html", {
        "form": ForgotPasswordForm()
    })


# ═══════════════════════════════════════════════════════════════
#  DASHBOARDS
# ═══════════════════════════════════════════════════════════════

@login_required
def candidate_dashboard(request):
    candidate = getattr(request.user, "candidateprofile", None)
    if not candidate:
        return redirect("company_dashboard")

    applications = (
        Application.objects
        .filter(candidate=candidate)
        .select_related("job__company", "resume")
        .order_by("-applied_at")
    )

    # Stats — match exact status strings defined in Application.Status choices
    total       = applications.count()
    pending     = applications.filter(status=Application.Status.PENDING).count()
    shortlisted = applications.filter(status=Application.Status.SHORTLISTED).count()
    offered     = applications.filter(status=Application.Status.HIRED).count()

    recent_applications = applications[:5]

    recent_jobs = (
        Job.objects
        .filter(status="open")
        .prefetch_related("skills")
        .order_by("-created_at")[:6]
    )

    return render(request, "accounts/candidate_dashboard.html", {
        "candidate":            candidate,
        "total":                total,
        "pending":              pending,
        "shortlisted":          shortlisted,
        "offered":              offered,
        "recent_applications":  recent_applications,
        "recent_jobs":          recent_jobs,
        "has_resumes":          candidate.resumes.exists(),
    })


@login_required
def company_dashboard(request):
    company = getattr(request.user, "companyprofile", None)
    if not company:
        return redirect("candidate_dashboard")

    jobs = (
        Job.objects
        .filter(company=company)
        .order_by("-created_at")
    )

    total_jobs   = jobs.count()
    open_jobs    = jobs.filter(status="open").count()
    closed_jobs  = jobs.filter(status="closed").count()
    draft_jobs   = jobs.filter(status="draft").count()

    all_apps = Application.objects.filter(job__company=company)

    total_applicants = all_apps.exclude(
        status=Application.Status.WITHDRAWN
    ).count()

    pending_review = all_apps.filter(
        status=Application.Status.PENDING
    ).count()

    recent_applicants = (
        all_apps
        .exclude(status=Application.Status.WITHDRAWN)
        .select_related("candidate__user", "job", "resume")
        .order_by("-applied_at")[:8]
    )

    # Annotate open jobs with applicant count for the sidebar list
    active_jobs = (
        jobs.filter(status="open")
        .annotate(application_count=Count("applications"))
    )

    return render(request, "accounts/company_dashboard.html", {
        "company":           company,
        "total_jobs":        total_jobs,
        "open_jobs":         open_jobs,
        "closed_jobs":       closed_jobs,
        "draft_jobs":        draft_jobs,
        "total_applicants":  total_applicants,
        "pending_review":    pending_review,
        "recent_applicants": recent_applicants,
        "active_jobs":       active_jobs,
    })


# ═══════════════════════════════════════════════════════════════
#  PROFILE EDITING
# ═══════════════════════════════════════════════════════════════

@login_required
def candidate_edit_profile(request):
    candidate = getattr(request.user, "candidateprofile", None)
    if not candidate:
        return redirect("company_dashboard")

    if request.method == "POST":
        request.user.first_name = request.POST.get("first_name", "").strip()
        request.user.last_name  = request.POST.get("last_name", "").strip()
        request.user.email      = request.POST.get("email", "").strip()
        request.user.save(update_fields=["first_name", "last_name", "email"])

        candidate.phone      = request.POST.get("phone", "").strip()
        candidate.skills     = request.POST.get("skills", "").strip()
        candidate.experience = int(request.POST.get("experience") or 0)
        candidate.education  = request.POST.get("education", "").strip()
        candidate.save()

        # Password change — only triggered if any password field is filled
        curr_pw = request.POST.get("current_password", "")
        new_pw  = request.POST.get("new_password", "")
        conf_pw = request.POST.get("confirm_password", "")

        if curr_pw or new_pw:
            if not request.user.check_password(curr_pw):
                messages.error(request, "Current password is incorrect.")
                return render(request, "accounts/candidate_edit_profile.html", {
                    "candidate":      candidate,
                    "password_error": "Current password is incorrect.",
                })
            if new_pw != conf_pw:
                messages.error(request, "New passwords do not match.")
                return render(request, "accounts/candidate_edit_profile.html", {
                    "candidate":      candidate,
                    "password_error": "New passwords do not match.",
                })
            if len(new_pw) < 8:
                messages.error(request, "Password must be at least 8 characters.")
                return render(request, "accounts/candidate_edit_profile.html", {
                    "candidate":      candidate,
                    "password_error": "Min. 8 characters required.",
                })
            request.user.set_password(new_pw)
            request.user.save()
            update_session_auth_hash(request, request.user)  # keep session alive

        messages.success(request, "Profile updated successfully.")
        return redirect("candidate_dashboard")

    return render(request, "accounts/candidate_edit_profile.html", {
        "candidate": candidate,
    })


@login_required
def company_edit_profile(request):
    company = getattr(request.user, "companyprofile", None)
    if not company:
        return redirect("candidate_dashboard")

    def _stats():
        """Helper — returns fresh stats dict for re-renders on error."""
        return {
            "total_jobs":       company.jobs.count(),
            "open_jobs":        company.jobs.filter(status="open").count(),
            "total_applicants": Application.objects.filter(job__company=company).count(),
            "total_hired":      Application.objects.filter(
                                    job__company=company,
                                    status=Application.Status.HIRED
                                ).count(),
        }

    if request.method == "POST":
        request.user.first_name = request.POST.get("first_name", "").strip()
        request.user.last_name  = request.POST.get("last_name", "").strip()
        request.user.email      = request.POST.get("email", "").strip()
        request.user.save(update_fields=["first_name", "last_name", "email"])

        company.company_name = request.POST.get("company_name", "").strip()
        company.description  = request.POST.get("description", "").strip()
        company.location     = request.POST.get("location", "").strip()
        company.website      = request.POST.get("website", "").strip()
        company.phone        = request.POST.get("hr_phone", "").strip()
        company.save()

        curr_pw = request.POST.get("current_password", "")
        new_pw  = request.POST.get("new_password", "")
        conf_pw = request.POST.get("confirm_password", "")

        if curr_pw or new_pw:
            if not request.user.check_password(curr_pw):
                messages.error(request, "Current password is incorrect.")
                return render(request, "accounts/company_edit_profile.html", {
                    "company": company, **_stats(),
                    "password_error": "Current password is incorrect.",
                })
            if new_pw != conf_pw:
                messages.error(request, "New passwords do not match.")
                return render(request, "accounts/company_edit_profile.html", {
                    "company": company, **_stats(),
                    "password_error": "New passwords do not match.",
                })
            if len(new_pw) < 8:
                messages.error(request, "Password must be at least 8 characters.")
                return render(request, "accounts/company_edit_profile.html", {
                    "company": company, **_stats(),
                    "password_error": "Min. 8 characters required.",
                })
            request.user.set_password(new_pw)
            request.user.save()
            update_session_auth_hash(request, request.user)

        messages.success(request, "Company profile updated successfully.")
        return redirect("company_dashboard")

    return render(request, "accounts/company_edit_profile.html", {
        "company": company,
        **_stats(),
    })


# ═══════════════════════════════════════════════════════════════
#  ACCOUNT DELETION
# ═══════════════════════════════════════════════════════════════

@login_required
def delete_company_account(request):
    """
    Deletes the company account and all related data via CASCADE.
    Only accepts POST to prevent accidental GET-triggered deletion.
    The confirmation dialog is handled in the template with JS confirm().

    TODO (future): before deleting, also clean up:
      - any uploaded media files (logos, resumes) from MEDIA_ROOT
      - send a goodbye/confirmation email to the user
    """
    company = getattr(request.user, "companyprofile", None)
    if not company:
        return redirect("candidate_dashboard")

    if request.method == "POST":
        request.user.delete()  # CASCADE deletes CompanyProfile + Jobs + Applications
        messages.success(request, "Your account has been permanently deleted.")
        return redirect("login")

    # GET request — redirect back rather than showing a blank page
    return redirect("company_edit_profile")