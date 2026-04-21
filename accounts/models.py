from django.contrib.auth.models import User
from django.db import models


class CandidateProfile(models.Model):
    user            = models.OneToOneField(User, on_delete=models.CASCADE)
    phone           = models.CharField(max_length=20, blank=True)
    about           = models.TextField(blank=True)
    education       = models.TextField(blank=True)
    experience      = models.IntegerField(default=0)
    skills          = models.TextField(blank=True)
    profile_picture = models.ImageField(
                        upload_to='profile_pictures/',
                        blank=True,
                        null=True,
                      )

    def __str__(self):
        return self.user.username

    @property
    def avatar_url(self):
        """Returns the profile picture URL, or a DiceBear initials fallback."""
        if self.profile_picture:
            return self.profile_picture.url
        seed = self.user.get_full_name() or self.user.username
        return f"https://api.dicebear.com/7.x/initials/svg?seed={seed}&backgroundColor=b6e0fe&textColor=1e40af"


class CompanyProfile(models.Model):
    user         = models.OneToOneField(User, on_delete=models.CASCADE)
    phone           = models.CharField(max_length=20, blank=True)
    company_name = models.CharField(max_length=255)
    description  = models.TextField()
    website      = models.URLField(blank=True, null=True)
    location     = models.CharField(max_length=255, blank=True, null=True)
    logo         = models.ImageField(upload_to='company_logos/', blank=True, null=True)

    def __str__(self):
        return self.company_name

    @property
    def avatar_url(self):
        """Returns the company logo URL, or a DiceBear initials fallback."""
        if self.logo:
            return self.logo.url
        seed = self.company_name or self.user.username
        return f"https://api.dicebear.com/7.x/initials/svg?seed={seed}&backgroundColor=0f766e&textColor=ccfbf1"