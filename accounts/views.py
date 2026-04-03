"""
accounts/views.py
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count

from .models import CandidateProfile, CompanyProfile
from .forms import CandidateRegistrationForm, CompanyRegistrationForm, ForgotPasswordForm

from applications.models import Application
from jobs.models import Job


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def _get_user_role(user):
    """
    Check the DB directly — never rely on hasattr() which caches misses
    on the user object and causes 'no profile' false negatives.
    Returns 'candidate', 'company', or None.
    """
    if CandidateProfile.objects.filter(user=user).exists():
        return 'candidate'
    if CompanyProfile.objects.filter(user=user).exists():
        return 'company'
    return None


def _redirect_by_role(user):
    """
    Return the correct redirect response for a user.
    Returns None if the user has no profile.
    """
    role = _get_user_role(user)
    if role == 'candidate':
        return redirect('candidate_dashboard')
    if role == 'company':
        return redirect('company_dashboard')
    return None


# ═══════════════════════════════════════════════════════════════
#  LANDING
# ═══════════════════════════════════════════════════════════════

def index(request):
    if request.user.is_authenticated:
        response = _redirect_by_role(request.user)
        if response:
            return response
    return render(request, 'accounts/index.html')


# ═══════════════════════════════════════════════════════════════
#  REGISTRATION
# ═══════════════════════════════════════════════════════════════

def register(request):
    """
    Single registration page for both candidate and company.
    Role is determined by a hidden <input name="role"> in the form.
    Handles multipart/form-data for profile_picture / logo uploads.
    """
    candidate_form = CandidateRegistrationForm()
    company_form   = CompanyRegistrationForm()

    if request.method == 'POST':
        role = request.POST.get('role')

        if role == 'candidate':
            candidate_form = CandidateRegistrationForm(request.POST)
            if candidate_form.is_valid():
                user = candidate_form.save()
                pic = request.FILES.get('profile_picture')
                if pic:
                    profile = CandidateProfile.objects.get(user=user)
                    profile.profile_picture = pic
                    profile.save(update_fields=['profile_picture'])
                messages.success(request, 'Account created! Please sign in.')
                return redirect('login')

        elif role == 'company':
            company_form = CompanyRegistrationForm(request.POST)
            if company_form.is_valid():
                user = company_form.save()
                logo = request.FILES.get('logo')
                if logo:
                    profile = CompanyProfile.objects.get(user=user)
                    profile.logo = logo
                    profile.save(update_fields=['logo'])
                messages.success(request, 'Company account created! Please sign in.')
                return redirect('login')

    return render(request, 'accounts/register.html', {
        'candidate_form': candidate_form,
        'company_form':   company_form,
    })


# ═══════════════════════════════════════════════════════════════
#  AUTHENTICATION
# ═══════════════════════════════════════════════════════════════

def user_login(request):
    """
    Authenticates by username + password.
    Uses DB query (not hasattr) to detect profile type — avoids
    the Django ORM cache bug where hasattr returns False on a fresh
    user object even when the profile exists.
    """
    if request.user.is_authenticated:
        response = _redirect_by_role(request.user)
        if response:
            return response

    error = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            error = 'Please enter both username and password.'
        else:
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                response = _redirect_by_role(user)
                if response:
                    return response
                # User authenticated but has no profile
                logout(request)
                error = (
                    'Your account has no candidate or company profile. '
                    'Please register first or contact support.'
                )
            else:
                error = 'Incorrect username or password.'

    return render(request, 'accounts/login.html', {'error': error})


@login_required
def user_logout(request):
    logout(request)
    return redirect('login')


# ═══════════════════════════════════════════════════════════════
#  PASSWORD RESET
# ═══════════════════════════════════════════════════════════════

def forgot_password(request):
    """
    Step 1 — collect email and show success screen.
    Email sending is stubbed; uncomment once email backend is configured.
    """
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']


            # EMAIL SENDING — uncomment when ready:

            # from django.contrib.auth.models import User
            # from django.contrib.auth.tokens import default_token_generator
            # from django.utils.http import urlsafe_base64_encode
            # from django.utils.encoding import force_bytes
            # from django.urls import reverse
            # from django.core.mail import send_mail

            # try:
            #     user = User.objects.get(email=email)
            #     uid   = urlsafe_base64_encode(force_bytes(user.pk))
            #     token = default_token_generator.make_token(user)
            #     reset_url = request.build_absolute_uri(
            #         reverse('password_reset_confirm',
            #                 kwargs={'uidb64': uid, 'token': token})
            #     )
            #     send_mail(
            #         subject='Reset your ResumeAI password',
            #         message=f'Click here to reset your password:\n{reset_url}',
            #         from_email=settings.DEFAULT_FROM_EMAIL,
            #         recipient_list=[email],
            #         fail_silently=False,
            #     )
            # except User.DoesNotExist:
            #     pass  # Never reveal whether the email is registered

            return render(request, 'accounts/forgot_password.html', {
                'form':            form,
                'email_sent':      True,
                'submitted_email': email,
                'steps': [
                    'Open your email inbox.',
                    'Look for an email from ResumeAI.',
                    'Click the reset link — it\'s valid for 24 hours.',
                    'Choose a new password and sign in.',
                ],
            })

        return render(request, 'accounts/forgot_password.html', {'form': form})

    return render(request, 'accounts/forgot_password.html', {
        'form': ForgotPasswordForm()
    })


# ═══════════════════════════════════════════════════════════════
#  DASHBOARDS
# ═══════════════════════════════════════════════════════════════

@login_required
def candidate_dashboard(request):
    candidate = CandidateProfile.objects.filter(user=request.user).first()
    if not candidate:
        return redirect('company_dashboard')

    applications = (
        Application.objects
        .filter(candidate=candidate)
        .select_related('job__company', 'resume')
        .order_by('-applied_at')
    )

    total       = applications.count()
    pending     = applications.filter(status=Application.Status.PENDING).count()
    shortlisted = applications.filter(status=Application.Status.SHORTLISTED).count()
    offered     = applications.filter(status=Application.Status.HIRED).count()

    recent_applications = (
        applications
        .exclude(status=Application.Status.WITHDRAWN)
        [:5]
    )

    recent_jobs = (
        Job.objects
        .filter(status=Job.Status.OPEN)
        .prefetch_related('skills')
        .order_by('-created_at')[:6]
    )

    skills_list = [
        s.strip()
        for s in (candidate.skills or '').split(',')
        if s.strip()
    ]

    education_list = [
        line.strip()
        for line in (candidate.education or '').splitlines()
        if line.strip()
    ]

    return render(request, 'accounts/candidate_dashboard.html', {
        'candidate':           candidate,
        'total':               total,
        'pending':             pending,
        'shortlisted':         shortlisted,
        'offered':             offered,
        'recent_applications': recent_applications,
        'recent_jobs':         recent_jobs,
        'has_resumes':         candidate.resumes.exists(),
        'skills_list':         skills_list,
        'education_list':      education_list,
    })


@login_required
def company_dashboard(request):
    company = CompanyProfile.objects.filter(user=request.user).first()
    if not company:
        return redirect('candidate_dashboard')

    jobs = (
        Job.objects
        .filter(company=company)
        .order_by('-created_at')
    )

    total_jobs  = jobs.count()
    open_jobs   = jobs.filter(status=Job.Status.OPEN).count()
    closed_jobs = jobs.filter(status=Job.Status.CLOSED).count()
    draft_jobs  = jobs.filter(status=Job.Status.DRAFT).count()

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
        .select_related('candidate__user', 'job', 'resume')
        .order_by('-applied_at')[:8]
    )

    active_jobs = (
        jobs.filter(status=Job.Status.OPEN)
        .annotate(app_count=Count('applications'))
    )

    return render(request, 'accounts/company_dashboard.html', {
        'company':           company,
        'total_jobs':        total_jobs,
        'open_jobs':         open_jobs,
        'closed_jobs':       closed_jobs,
        'draft_jobs':        draft_jobs,
        'total_applicants':  total_applicants,
        'pending_review':    pending_review,
        'recent_applicants': recent_applicants,
        'active_jobs':       active_jobs,
    })


# ═══════════════════════════════════════════════════════════════
#  PROFILE EDITING
# ═══════════════════════════════════════════════════════════════

@login_required
def candidate_edit_profile(request):
    candidate = CandidateProfile.objects.filter(user=request.user).first()
    if not candidate:
        return redirect('company_dashboard')

    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', '').strip()
        request.user.last_name  = request.POST.get('last_name',  '').strip()
        request.user.email      = request.POST.get('email',      '').strip()

        candidate.phone     = request.POST.get('phone',     '').strip()
        candidate.skills    = request.POST.get('skills',    '').strip()
        candidate.education = request.POST.get('education', '').strip()

        raw_exp = request.POST.get('experience', '0').strip()
        candidate.experience = int(raw_exp) if raw_exp.isdigit() else 0

        if 'profile_picture' in request.FILES:
            if candidate.profile_picture:
                candidate.profile_picture.delete(save=False)
            candidate.profile_picture = request.FILES['profile_picture']
        elif request.POST.get('profile_picture_clear') == 'on':
            if candidate.profile_picture:
                candidate.profile_picture.delete(save=False)
            candidate.profile_picture = None

        # ── Password validation FIRST, before any save ──────────────────
        curr_pw = request.POST.get('current_password', '')
        new_pw  = request.POST.get('new_password',     '')
        conf_pw = request.POST.get('confirm_password', '')

        if curr_pw or new_pw:
            error_ctx = {'candidate': candidate}
            if not request.user.check_password(curr_pw):
                return render(request, 'accounts/candidate_edit_profile.html', {
                    **error_ctx,
                    'password_error': 'Current password is incorrect.',
                })
            if new_pw != conf_pw:
                return render(request, 'accounts/candidate_edit_profile.html', {
                    **error_ctx,
                    'password_error': 'New passwords do not match.',
                })
            if len(new_pw) < 8:
                return render(request, 'accounts/candidate_edit_profile.html', {
                    **error_ctx,
                    'password_error': 'Password must be at least 8 characters.',
                })
            # All good — save everything then change password
            request.user.save(update_fields=['first_name', 'last_name', 'email'])
            candidate.save()
            request.user.set_password(new_pw)
            request.user.save()
            update_session_auth_hash(request, request.user)
        else:
            # No password change — just save profile
            request.user.save(update_fields=['first_name', 'last_name', 'email'])
            candidate.save()

        messages.success(request, 'Profile updated successfully.')
        return redirect('candidate_dashboard')
    return render(request, 'accounts/candidate_edit_profile.html', {
        'candidate': candidate,
    })


@login_required
def company_edit_profile(request):
    company = CompanyProfile.objects.filter(user=request.user).first()
    if not company:
        return redirect('candidate_dashboard')

    def _stats():
        return {
            'total_jobs':       company.jobs.count(),
            'open_jobs':        company.jobs.filter(status=Job.Status.OPEN).count(),
            'total_applicants': Application.objects.filter(job__company=company).count(),
            'total_hired':      Application.objects.filter(
                                    job__company=company,
                                    status=Application.Status.HIRED,
                                ).count(),
        }

    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', '').strip()
        request.user.last_name  = request.POST.get('last_name',  '').strip()
        request.user.email      = request.POST.get('email',      '').strip()
        request.user.save(update_fields=['first_name', 'last_name', 'email'])

        company.company_name = request.POST.get('company_name', '').strip()
        company.description  = request.POST.get('description',  '').strip()
        company.location     = request.POST.get('location',     '').strip()
        company.phone        = request.POST.get('phone',     '').strip()
        website = request.POST.get('website', '').strip()
        company.website = website if website else None
        company.save()

        curr_pw = request.POST.get('current_password', '')
        new_pw  = request.POST.get('new_password',     '')
        conf_pw = request.POST.get('confirm_password', '')

        if curr_pw or new_pw:
            error_ctx = {'company': company, **_stats()}
            if not request.user.check_password(curr_pw):
                return render(request, 'accounts/company_edit_profile.html', {
                    **error_ctx,
                    'password_error': 'Current password is incorrect.',
                })
            if new_pw != conf_pw:
                return render(request, 'accounts/company_edit_profile.html', {
                    **error_ctx,
                    'password_error': 'New passwords do not match.',
                })
            if len(new_pw) < 8:
                return render(request, 'accounts/company_edit_profile.html', {
                    **error_ctx,
                    'password_error': 'Min. 8 characters required.',
                })
            request.user.set_password(new_pw)
            request.user.save()
            update_session_auth_hash(request, request.user)

        messages.success(request, 'Company profile updated successfully.')
        return redirect('company_dashboard')

    return render(request, 'accounts/company_edit_profile.html', {
        'company': company,
        **_stats(),
    })