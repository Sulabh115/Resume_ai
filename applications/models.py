from django.db import models


class Resume(models.Model):
    candidate   = models.ForeignKey(
                    'accounts.CandidateProfile',
                    on_delete=models.CASCADE,
                    related_name="resumes",
                  )
    file        = models.FileField(upload_to="resumes/")
    label       = models.CharField(
                    max_length=100, blank=True,
                    help_text="Optional label, e.g. 'Software Engineer Resume v2'",
                  )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_default  = models.BooleanField(default=False)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Resume of {self.candidate.user.username}"

    def save(self, *args, **kwargs):
        # Auto-set default if this is the candidate's first resume
        if not self.pk and not Resume.objects.filter(candidate=self.candidate).exists():
            self.is_default = True
        super().save(*args, **kwargs)

    @property
    def filename(self):
        """Last path segment of the stored file — no parentheses needed."""
        return self.file.name.split("/")[-1]


class Application(models.Model):

    class Status(models.TextChoices):
        PENDING     = "pending",     "Pending Review"
        REVIEWED    = "reviewed",    "Reviewed"
        SHORTLISTED = "shortlisted", "Shortlisted"
        REJECTED    = "rejected",    "Rejected"
        HIRED       = "hired",       "Hired"
        WITHDRAWN   = "withdrawn",   "Withdrawn"   # ← was missing, caused 3 view crashes

    candidate    = models.ForeignKey(
                     'accounts.CandidateProfile',
                     on_delete=models.CASCADE,
                     related_name="applications",
                   )
    job          = models.ForeignKey(
                     'jobs.Job',
                     on_delete=models.CASCADE,
                     related_name="applications",
                   )
    resume       = models.ForeignKey(
                     Resume,
                     on_delete=models.SET_NULL,
                     null=True,
                     related_name="applications",
                   )
    match_score   = models.FloatField(default=0)
    status        = models.CharField(
                      max_length=20,
                      choices=Status.choices,
                      default=Status.PENDING,
                    )
    company_note  = models.TextField(blank=True)
    score_notes   = models.TextField(blank=True)
    status_note   = models.TextField(blank=True, help_text="Internal note visible to company only")
    applied_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["candidate", "job"], name="unique_application")
        ]
        ordering = ["-match_score", "-applied_at"]

    def __str__(self):
        return f"{self.candidate.user.username} → {self.job.title}"

    # ── Score helpers ─────────────────────────────────────────────────────

    @property
    def score_color(self):
        """
        Returns 'green', 'yellow', or 'red' for use in template badge/bar classes.
        Was missing — caused AttributeError on company dashboard.
        """
        if self.match_score >= 75:
            return "green"
        elif self.match_score >= 45:
            return "yellow"
        return "red"

    @property
    def status_color(self):
        return {
            "pending":     "blue",
            "reviewed":    "yellow",
            "shortlisted": "green",
            "rejected":    "red",
            "hired":       "emerald",
            "withdrawn":   "slate",
        }.get(self.status, "slate")