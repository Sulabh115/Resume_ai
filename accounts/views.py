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

def candidate_register(request):
    if request.method == "POST":
        form = CandidateRegistrationForm(request.POST)
        if form.is_valid():
            form.save()  # Creates User + CandidateProfile via form.save()
            messages.success(request, "Account created! Please sign in.")
            return redirect("login")
    else:
        form = CandidateRegistrationForm()
    return render(request, "accounts/candidate_register.html", {"form": form})


def company_register(request):
    if request.method == "POST":
        form = CompanyRegistrationForm(request.POST)
        if form.is_valid():
            form.save()  # Creates User + CompanyProfile via form.save()
            messages.success(request, "Company account created! Please sign in.")
            return redirect("login")
    else:
        form = CompanyRegistrationForm()
    return render(request, "accounts/company_register.html", {"form": form})


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
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            user = User.objects.get(email=email)

            # Generate token + uid
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            # Build reset URL
            reset_url = request.build_absolute_uri(
                f"/accounts/reset-password/{uid}/{token}/"
            )

            # Send email
            send_mail(
                subject="Password Reset — ResumeAI",
                message=f"Hi {user.username},\n\nClick the link below to reset your password:\n\n{reset_url}\n\nThis link expires in 30 minutes.\n\nIf you didn't request this, you can safely ignore this email.",
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@resumeai.com"),
                recipient_list=[email],
            )
            messages.success(request, f"A reset link has been sent to {email}.")
            return redirect("forgot_password")
        # Form invalid — re-render with errors
        return render(request, "accounts/forgot_password.html", {"form": form})

    form = ForgotPasswordForm()
    return render(request, "accounts/forgot_password.html", {"form": form})


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