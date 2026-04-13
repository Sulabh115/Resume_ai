import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'resume_ai.settings')
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from jobs.models import Job, Skill as JobSkill
from applications.models import Application
from accounts.models import CandidateProfile, CompanyProfile, User
from screening.utils import compute_match_score

# Create mock data
try:
    c_user, _ = User.objects.get_or_create(username='test_company', email='company@test.com')
    company, _ = CompanyProfile.objects.get_or_create(user=c_user, company_name='Acme Corp')
    
    cand_user, _ = User.objects.get_or_create(username='test_candidate', email='candidate@test.com')
    candidate, _ = CandidateProfile.objects.get_or_create(user=cand_user)
    
    job, _ = Job.objects.get_or_create(
        company=company,
        title='Software Engineer',
        description='We need a Python developer who knows Django.',
        requirements='3+ years of experience with Python and Django. Bachelor degree required.',
        experience_required=3,
        qualification_required='bachelor',
        status='open'
    )
    s1, _ = JobSkill.objects.get_or_create(name='Python')
    s2, _ = JobSkill.objects.get_or_create(name='Django')
    job.skills.set([s1, s2])


    import fitz # PyMuPDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 50), "John Doe\nExperienced Software Engineer.\nI have 4 years of experience using Python and Django.\nQualification: Bachelor in Computer Science.")
    pdf_path = os.path.abspath("test_resume.pdf")
    doc.save(pdf_path)
    doc.close()
    
    class MockResume:
        path = pdf_path
        
    resume_file = MockResume()
    
    print("Running screening...")
    result = compute_match_score(resume_file, job)
    print("Screening successful:")
    for k, v in result.items():
        print(f"  {k}: {v}")

except Exception as e:
    import traceback
    traceback.print_exc()
