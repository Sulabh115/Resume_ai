from accounts.models import CandidateProfile, CompanyProfile
from .models import Application
from datetime import date

def active_applications_count(request):
    """
    Returns the count of active applications for the logged-in candidate
    and provides the candidate/company profile objects globally.
    """
    context = {}
    if not request.user.is_authenticated:
        return context
    
    # ── Profiles ──────────────────────────────────────────────────────────
    # Provision 'candidate' and 'company' globally for the navbar avatars
    candidate = CandidateProfile.objects.filter(user=request.user).first()
    company = CompanyProfile.objects.filter(user=request.user).first()
    
    context['candidate'] = candidate
    context['company'] = company

    # ── Active Application Count (for bubble) ─────────────────────────────
    if candidate:
        today = date.today()
        count = (
            Application.objects
            .filter(candidate=candidate)
            .exclude(status__in=[
                Application.Status.WITHDRAWN,
                Application.Status.REJECTED,
            ])
            .exclude(job__deadline__lt=today)
            .count()
        )
        context['active_app_count'] = count
    
    return context
