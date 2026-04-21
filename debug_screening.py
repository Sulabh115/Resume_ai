import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'resume_ai.settings')
django.setup()

from applications.models import Application
from screening.models import ScreeningResult

# Check the latest screening results
results = ScreeningResult.objects.all().order_by('-id')[:5]

print(f"{'App ID':<10} | {'Status':<15} | {'Error Message'}")
print("-" * 60)
for r in results:
    print(f"{r.application.id:<10} | {r.status:<15} | {r.error_message}")
