from django.db import models
from accounts.models import CompanyProfile


class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Job(models.Model):

    class JobType(models.TextChoices):
        FULL_TIME  = "full_time",  "Full-time"
        PART_TIME  = "part_time",  "Part-time"
        CONTRACT   = "contract",   "Contract"
        INTERNSHIP = "internship", "Internship"
        REMOTE     = "remote",     "Remote"
        HYBRID     = "hybrid",     "Hybrid"

    class Status(models.TextChoices):
        OPEN   = "open",   "Open"
        CLOSED = "closed", "Closed"
        DRAFT  = "draft",  "Draft"

    # ── New: qualification level choices ──────────────────────────────────
    class QualificationLevel(models.TextChoices):
        ANY        = "",           "Any / Not specified"
        DIPLOMA    = "diploma",    "Diploma"
        BACHELOR   = "bachelor",   "Bachelor's Degree"
        MASTER     = "master",     "Master's Degree"
        PHD        = "phd",        "PhD / Doctorate"

    company          = models.ForeignKey(
                         CompanyProfile,
                         on_delete=models.CASCADE,
                         related_name="jobs"
                       )
    title            = models.CharField(max_length=255)
    description      = models.TextField()
    requirements     = models.TextField(blank=True, help_text="Detailed role requirements")
    responsibilities = models.TextField(blank=True, help_text="Key responsibilities")

    experience_required    = models.IntegerField(
                               default=0,
                               help_text="Minimum years of experience required"
                             )

    # ── New field ──────────────────────────────────────────────────────────
    qualification_required = models.CharField(
                               max_length=20,
                               choices=QualificationLevel.choices,
                               default=QualificationLevel.ANY,
                               blank=True,
                               help_text="Minimum qualification level required"
                             )

    skills           = models.ManyToManyField(Skill, blank=True)
    location         = models.CharField(max_length=255, blank=True)
    job_type         = models.CharField(
                         max_length=20,
                         choices=JobType.choices,
                         default=JobType.FULL_TIME
                       )

    salary_min       = models.PositiveIntegerField(null=True, blank=True)
    salary_max       = models.PositiveIntegerField(null=True, blank=True)
    salary_currency  = models.CharField(max_length=10, default="NPR")

    status           = models.CharField(
                         max_length=10,
                         choices=Status.choices,
                         default=Status.OPEN
                       )
    deadline         = models.DateField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} @ {self.company.company_name}"

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    @property
    def application_count(self):
        return self.applications.count()

    @property
    def salary_display(self):
        if self.salary_min and self.salary_max:
            return f"{self.salary_currency} {self.salary_min:,} – {self.salary_max:,}"
        if self.salary_min:
            return f"{self.salary_currency} {self.salary_min:,}+"
        return "Not disclosed"