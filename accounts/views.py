"""
accounts/views.py

FIX #6 (company_edit_profile):
    The template company_edit_profile.html has TWO phone inputs:
        name="phone"    — in the Company Details section
        name="hr_phone" — in the Your Account Details section

    The view previously only read request.POST.get('phone', ''),
    which meant the hr_phone field was silently ignored.

    Fix: read both fields. hr_phone takes priority (it's the dedicated
    HR contact field); fall back to phone if hr_phone is empty.
    This matches the pattern used in CompanyRegistrationForm.save()
    which also reads hr_phone into company.phone.

FIX #8 (already present):
    company_edit_profile previously called company.save() and
    request.user.save() BEFORE the password validation block.
    If the user submitted a wrong current password, the profile
    fields were already written to the DB before the error returned.
    Fix: validate password first, then save everything together.

FIX #12 (candidate_edit_profile):
    The candidate.about field exists on the model (migration 0003)
    but was never read from POST data or saved in the view.
    Fix: read request.POST.get('about', '').strip() and assign it
    to candidate.about before the save() calls, mirroring every
    other candidate profile field.
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.conf import settings

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

    Role validation (fix for cross-role login confusion):
        The login form submits a hidden 'role' field (updated by the JS
        toggle to 'candidate' or 'company').  After successful auth, the
        view checks that the authenticated user's actual profile type
        matches the selected role.  If they don't match, the user is
        logged back out and shown a specific, friendly error message —
        rather than silently redirecting them to the wrong dashboard.

        This prevents the confusing situation where:
          · A company user logs in on the Candidate tab and sees
            a partially-rendered candidate UI
          · A candidate logs in on the HR tab and sees company UI

        If no role is submitted (e.g. direct POST from tests or the
        landing-page form), the check is skipped and the user is
        redirected by their actual profile type as before.
    """
    if request.user.is_authenticated:
        response = _redirect_by_role(request.user)
        if response:
            return response

    error     = None
    role_hint = 'candidate'  # default for pre-selecting the toggle on re-render

    if request.method == 'POST':
        email           = request.POST.get('email', '').strip()
        password        = request.POST.get('password', '')
        selected_role   = request.POST.get('role', '').strip()  # 'candidate' | 'company' | ''
        role_hint       = selected_role or 'candidate'

        if not email or not password:
            error = 'Please enter both email and password.'
        else:
            user = authenticate(request, email=email, password=password)

            if user is not None:
                actual_role = _get_user_role(user)

                # ── Role mismatch check ───────────────────────────────────
                # Only enforce when the form actually submitted a role value.
                # Skip silently if role was empty (API / direct POST).
                if selected_role and actual_role and selected_role != actual_role:
                    # Do NOT log the user in — just return a clear error.
                    if selected_role == 'candidate':
                        error = (
                            'These credentials belong to a company / HR account. '
                            'Please switch to the "HR / Recruiter" tab and sign in again.'
                        )
                        role_hint = 'candidate'   # keep the tab the user chose
                    else:
                        error = (
                            'These credentials belong to a candidate account. '
                            'Please switch to the "Candidate" tab and sign in again.'
                        )
                        role_hint = 'company'
                else:
                    # Credentials are valid and role matches (or no role was submitted)
                    login(request, user)
                    response = _redirect_by_role(user)
                    if response:
                        return response
                    # Authenticated but no profile attached
                    logout(request)
                    error = (
                        'Your account has no candidate or company profile. '
                        'Please register first or contact support.'
                    )
            else:
                error = 'Incorrect email or password.'

    return render(request, 'accounts/login.html', {
        'error':     error,
        'role_hint': role_hint,
    })


@login_required
def user_logout(request):
    logout(request)
    return redirect('login')


# ═══════════════════════════════════════════════════════════════
#  PASSWORD RESET
# ═══════════════════════════════════════════════════════════════

def forgot_password(request):
    """
    Password reset — step 1.

    Collects the user's email, generates a secure uid+token pair using
    Django's built-in token generator, builds the reset URL, and sends
    a plain-text + HTML email via EmailMultiAlternatives.

    Security: the success screen is always shown even when no account
    exists for the submitted email — this prevents user enumeration.

    Token lifetime is controlled by PASSWORD_RESET_TIMEOUT in settings
    (Django default: 259200 s = 3 days).  The template shows "24 hours"
    as a conservative user-facing message; adjust both if needed.
    """
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']

            # Wrapped in try/except so a misconfigured email backend never
            # shows an error page — the success screen is always shown.
            try:
                user = User.objects.get(email=email)

                # Build uid + token using Django's built-in token generator.
                # The token is single-use and expires after PASSWORD_RESET_TIMEOUT.
                uid   = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)

                # Build the full absolute reset URL so it works in any
                # environment without hardcoding the domain.
                from django.urls import reverse
                reset_path = reverse(
                    'password_reset_confirm',
                    kwargs={'uidb64': uid, 'token': token},
                )
                reset_url = request.build_absolute_uri(reset_path)

                name = user.get_full_name() or user.username

                # ── Plain-text body ───────────────────────────────────────
                text_body = (
                    f"Hi {name},\n\n"
                    f"We received a request to reset the password for your "
                    f"YogyataRank account.\n\n"
                    f"Click the link below to choose a new password:\n"
                    f"{reset_url}\n\n"
                    f"This link is valid for 24 hours. If you did not request "
                    f"a password reset, you can safely ignore this email — "
                    f"your password will not change.\n\n"
                    f"— The YogyataRank team"
                )

                # ── HTML body — rendered from a dedicated template ────────
                html_body = render_to_string(
                    'accounts/email/password_reset.html',
                    {
                        'name':      name,
                        'reset_url': reset_url,
                        'username':  user.username,
                    },
                )

                # ── Send plain-text + HTML via EmailMultiAlternatives ─────
                msg = EmailMultiAlternatives(
                    subject    = 'Reset your YogyataRank password',
                    body       = text_body,
                    from_email = settings.DEFAULT_FROM_EMAIL,
                    to         = [email],
                )
                msg.attach_alternative(html_body, 'text/html')
                msg.send(fail_silently=False)

            except User.DoesNotExist:
                pass   # Never reveal whether the email is registered

            except Exception:
                pass   # SMTP / backend error — silently fall through

            # Always show the success screen regardless of outcome.
            return render(request, 'accounts/forgot_password.html', {
                'form':            form,
                'email_sent':      True,
                'submitted_email': email,
                'steps': [
                    'Open your email inbox.',
                    'Look for an email from YogyataRank.',
                    "Click the reset link — it's valid for 24 hours.",
                    'Choose a new password and sign in.',
                ],
            })

        # Form invalid — re-render with errors
        return render(request, 'accounts/forgot_password.html', {'form': form})

    # GET — show the blank form
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

    today = timezone.now().date()
    active_jobs = (
        jobs
        .filter(status=Job.Status.OPEN)
        .filter(Q(deadline__gte=today) | Q(deadline__isnull=True))
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

        # FIX #12: read and save the about/summary field.
        # The field was added to the model in migration 0003 but was
        # never wired up in the view — so edits were silently discarded.
        candidate.about = request.POST.get('about', '').strip()

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

        # ── FIX #8: collect all field values into local variables first ──
        first_name   = request.POST.get('first_name',   '').strip()
        last_name    = request.POST.get('last_name',    '').strip()
        email        = request.POST.get('email',        '').strip()
        company_name = request.POST.get('company_name', '').strip()
        description  = request.POST.get('description',  '').strip()
        location     = request.POST.get('location',     '').strip()
        website_raw  = request.POST.get('website',      '').strip()
        website      = website_raw if website_raw else None

        # ── Logo upload handling ─────────────────────────────────────────────
        if 'logo' in request.FILES:
            if company.logo:
                company.logo.delete(save=False)
            company.logo = request.FILES['logo']
        elif request.POST.get('logo_clear') == 'on':
            if company.logo:
                company.logo.delete(save=False)
            company.logo = None

        # ── FIX #6: read both phone field names from the template ────────
        hr_phone      = request.POST.get('hr_phone', '').strip()
        company_phone = request.POST.get('phone',    '').strip()
        phone         = hr_phone if hr_phone else company_phone

        curr_pw = request.POST.get('current_password', '')
        new_pw  = request.POST.get('new_password',     '')
        conf_pw = request.POST.get('confirm_password', '')

        # ── Password validation — runs BEFORE any DB write ───────────────
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

        # ── All validation passed — now write to DB ───────────────────────
        request.user.first_name = first_name
        request.user.last_name  = last_name
        request.user.email      = email
        request.user.save(update_fields=['first_name', 'last_name', 'email'])

        company.company_name = company_name
        company.description  = description
        company.location     = location
        company.phone        = phone
        company.website      = website
        company.save()

        # ── Apply password change if requested ────────────────────────────
        if curr_pw or new_pw:
            request.user.set_password(new_pw)
            request.user.save()
            update_session_auth_hash(request, request.user)

        messages.success(request, 'Company profile updated successfully.')
        return redirect('company_dashboard')

    return render(request, 'accounts/company_edit_profile.html', {
        'company': company,
        **_stats(),
    })