from django.db import models
from applications.models import Application


class ScreeningResult(models.Model):

    class Status(models.TextChoices):
        PENDING    = "pending",    "Pending"
        PROCESSING = "processing", "Processing"
        DONE       = "done",       "Done"
        FAILED     = "failed",     "Failed"

    application      = models.OneToOneField(
                         Application,
                         on_delete=models.CASCADE,
                         related_name="screening_result"
                       )

    # Core composite score
    similarity_score = models.FloatField(
                         default=0,
                         help_text="Cosine similarity score between resume and job description (0–100)"
                       )

    # ── #9: Individual component scores ──────────────────────────────────
    skill_score          = models.FloatField(default=0, help_text="Skill match component score (0–100)")
    experience_score     = models.FloatField(default=0, help_text="Experience match component score (0–100)")
    qualification_score  = models.FloatField(default=0, help_text="Qualification match component score (0–100)")
    cosine_score         = models.FloatField(default=0, help_text="Raw cosine similarity component score (0–100)")

    # Skill analysis — stored as comma-separated strings for simplicity
    extracted_skills = models.TextField(
                         blank=True,
                         help_text="Skills extracted from the candidate's resume"
                       )
    matched_skills   = models.TextField(
                         blank=True,
                         help_text="Skills that matched the job requirements"
                       )
    missing_skills   = models.TextField(
                         blank=True,
                         help_text="Required job skills not found in the resume"
                       )

    # Human-readable AI summary
    summary          = models.TextField(
                         blank=True,
                         help_text="AI-generated summary of the candidate's fit"
                       )

    # Processing metadata
    status           = models.CharField(
                         max_length=12,
                         choices=Status.choices,
                         default=Status.PENDING
                       )
    error_message    = models.TextField(
                         blank=True,
                         help_text="Error detail if screening failed"
                       )
    screened_at      = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-screened_at"]

    def __str__(self):
        return f"Screening for {self.application} — {self.similarity_score:.0f}%"

    # ── Convenience helpers ───────────────────────────────────────────────

    def extracted_skills_list(self):
        return [s.strip() for s in self.extracted_skills.split(",") if s.strip()]

    def matched_skills_list(self):
        return [s.strip() for s in self.matched_skills.split(",") if s.strip()]

    def missing_skills_list(self):
        return [s.strip() for s in self.missing_skills.split(",") if s.strip()]

    @property
    def score_band(self):
        """Returns 'green', 'yellow', or 'red' for screening UI CSS (score-* classes)."""
        if self.similarity_score >= 70:
            return "green"
        elif self.similarity_score >= 45:
            return "yellow"
        return "red"

    @property
    def score_label(self):
        if self.similarity_score >= 70:
            return "Strong Match"
        elif self.similarity_score >= 45:
            return "Moderate Match"
        return "Weak Match"

    @property
    def match_percentage(self):
        """What % of required skills were matched."""
        matched = len(self.matched_skills_list())
        missing = len(self.missing_skills_list())
        total = matched + missing
        if total == 0:
            return 100
        return round((matched / total) * 100)