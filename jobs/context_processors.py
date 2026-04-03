from accounts.models import CompanyProfile
from jobs.models import Job
 
def to_shortlist_count(request):
    if not request.user.is_authenticated:
        return {}
    try:
        company = CompanyProfile.objects.get(user=request.user)
        count = Job.objects.filter(
            company=company,
            results_published=True,
            shortlist_email_sent=False,
        ).count()
        return {'to_shortlist_count': count}
    except CompanyProfile.DoesNotExist:
        return {}
 
 