from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings

from .models import CandidateProfile, CompanyProfile
from .forms import CandidateRegistrationForm, CompanyRegistrationForm, ForgotPasswordForm


# ---------- Registration Views ----------
def register(request):
    candidate_form = CandidateRegistrationForm()
    company_form   = CompanyRegistrationForm()

    if request.method == "POST":
        role = request.POST.get("role")  # hidden input in each form

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
# ---------- Authentication ----------

def user_login(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            if hasattr(user, "candidateprofile"):
                return redirect("job_list")
            elif hasattr(user, "companyprofile"):
                return redirect("company_job_list")
            return redirect("/")
        else:
            return render(request, "accounts/login.html", {"error": "Invalid username or password."})
    return render(request, "accounts/login.html")


@login_required
def user_logout(request):
    logout(request)
    return redirect("login")


# ---------- Forgot Password ----------

def forgot_password(request):
    """
    Step 1 of password reset — collect email.
    EMAIL SENDING: currently just sets email_sent=True.
    When you're ready to send emails, uncomment the send_reset_email() block.
    """
    from .forms import ForgotPasswordForm

    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]

            # ── EMAIL SENDING (implement later) ────────────────────────
            # from django.contrib.auth.tokens import default_token_generator
            # from django.utils.http import urlsafe_base64_encode
            # from django.utils.encoding import force_bytes
            # from django.core.mail import send_mail
            # from django.contrib.auth.models import User
            #
            # try:
            #     user = User.objects.get(email=email)
            #     uid   = urlsafe_base64_encode(force_bytes(user.pk))
            #     token = default_token_generator.make_token(user)
            #     reset_url = request.build_absolute_uri(
            #         reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
            #     )
            #     send_mail(
            #         subject="Reset your ResumeAI password",
            #         message=f"Click here to reset your password:\n{reset_url}",
            #         from_email="noreply@resumeai.com",
            #         recipient_list=[email],
            #         fail_silently=False,
            #     )
            # except User.DoesNotExist:
            #     pass  # Don't reveal whether email is registered
            # ────────────────────────────────────────────────────────────

            return render(request, "accounts/forgot_password.html", {
                "form": form,
                "email_sent": True,
                "submitted_email": email,
                "steps": [
                    "Open your email inbox.",
                    "Look for an email from ResumeAI.",
                    "Click the reset link inside — it's valid for 24 hours.",
                    "Choose a new password and sign in.",
                ],
            })
        # Form invalid — re-render with errors
        return render(request, "accounts/forgot_password.html", {"form": form})

    return render(request, "accounts/forgot_password.html", {
        "form": ForgotPasswordForm()
    })

# ---------- Dashboards ----------

# @login_required
# def candidate_dashboard(request):
#     candidate = request.user.candidateprofile
#     applications = candidate.applications.all()
#     return render(request, "accounts/candidate_dashboard.html", {"applications": applications})


# @login_required
# def company_dashboard(request):
#     company = request.user.companyprofile
#     jobs = company.jobs.all()
#     return render(request, "accounts/company_dashboard.html", {"jobs": jobs})

# from django.shortcuts import render, redirect
# from django.contrib.auth.decorators import login_required

from applications.models import Application
from jobs.models import Job


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

    # ── Stats ──────────────────────────────────────────────────────────────
    total       = applications.count()
    pending     = applications.filter(status="pending").count()
    shortlisted = applications.filter(status="shortlist").count()
    interviews  = applications.filter(status="interview").count()
    offered     = applications.filter(status="offered").count()
    rejected    = applications.filter(status="rejected").count()

    # ── Recent applications (latest 5) ─────────────────────────────────────
    recent_applications = applications[:5]

    # ── Recent jobs to browse (latest 6 open jobs) ────────────────────────
    recent_jobs = (
        Job.objects
        .filter(status="open")
        .prefetch_related("skills")
        .order_by("-created_at")[:6]
    )

    return render(request, "accounts/candidate_dashboard.html", {
        "candidate":           candidate,
        "total":               total,
        "pending":             pending,
        "shortlisted":         shortlisted,
        "interviews":          interviews,
        "offered":             offered,
        "rejected":            rejected,
        "recent_applications": recent_applications,
        "recent_jobs":         recent_jobs,
        "has_resumes":         candidate.resumes.exists(),
    })


@login_required
def company_dashboard(request):
    company = getattr(request.user, "companyprofile", None)
    if not company:
        return redirect("candidate_dashboard")

    jobs = (
        Job.objects
        .filter(company=company)
        .prefetch_related("skills")
        .order_by("-created_at")
    )

    # ── Stats ──────────────────────────────────────────────────────────────
    total_jobs    = jobs.count()
    open_jobs     = jobs.filter(status="open").count()
    closed_jobs   = jobs.filter(status="closed").count()
    draft_jobs    = jobs.filter(status="draft").count()

    total_applicants = Application.objects.filter(
        job__company=company
    ).exclude(status="withdrawn").count()

    pending_review = Application.objects.filter(
        job__company=company,
        status="pending"
    ).count()

    # ── Recent applicants across all jobs (latest 6) ──────────────────────
    recent_applicants = (
        Application.objects
        .filter(job__company=company)
        .exclude(status="withdrawn")
        .select_related("candidate__user", "job", "resume")
        .order_by("-applied_at")[:6]
    )

    # ── Active job listings (open only) ───────────────────────────────────
    active_jobs = jobs.filter(status="open")

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
@login_required
def candidate_edit_profile(request):
    candidate = getattr(request.user, "candidateprofile", None)
    if not candidate:
        return redirect("company_dashboard")
    if request.method == "POST":
        request.user.first_name = request.POST.get("first_name", "")
        request.user.last_name  = request.POST.get("last_name", "")
        request.user.email      = request.POST.get("email", "")
        request.user.save(update_fields=["first_name", "last_name", "email"])
        candidate.phone      = request.POST.get("phone", "")
        candidate.skills     = request.POST.get("skills", "")
        candidate.experience = int(request.POST.get("experience") or 0)
        candidate.education  = request.POST.get("education", "")
        candidate.save()
        messages.success(request, "Profile updated.")
        return redirect("candidate_dashboard")
    return render(request, "accounts/candidate_edit_profile.html", {"candidate": candidate})