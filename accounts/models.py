from django.contrib.auth.models import User
from django.db import models

class CandidateProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20)
    education = models.TextField()
    experience = models.IntegerField()
    skills = models.TextField()
    # resume = models.FileField(upload_to="resumes/")

    def __str__(self):
        return self.user.username
    
class CompanyProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    company_name = models.CharField(max_length=255)
    description = models.TextField()
    website = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    def __str__(self):
        return self.company_name