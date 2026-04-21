from accounts.models import CandidateProfile
from .models import Application
from datetime import date

def active_applications_count(request):
    context = {}
    if not request.user.is_authenticated:
        return context

    from django.db.models import Q as _Q

    # Single query to get candidate profile (most common case to check)
    candidate = CandidateProfile.objects.filter(user=request.user).first()
    context['candidate'] = candidate

    if candidate:
        # Only fetch company if the user is also a candidate (edge case: skip it,
        # a user has exactly one role). No need to query CompanyProfile for candidates.
        context['company'] = None

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
    else:
        # User has no candidate profile — check if company
        from accounts.models import CompanyProfile
        company = CompanyProfile.objects.filter(user=request.user).first()
        context['company'] = company
        # active_app_count not needed for companies

    return context
