from django import forms
from .models import Application, Resume


class ApplyJobForm(forms.Form):
    """
    Candidate applies to a job.
    They can pick an existing resume OR upload a new one.
    """
    # Populated dynamically in the view with the candidate's existing resumes
    existing_resume = forms.ModelChoiceField(
        queryset=Resume.objects.none(),
        required=False,
        empty_label="— Upload a new resume instead —",
        label="Use a saved resume",
        widget=forms.Select()
    )
    new_resume = forms.FileField(
        required=False,
        label="Upload new resume",
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf"})
    )
    resume_label = forms.CharField(
        max_length=100,
        required=False,
        label="Label for new resume",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Software Engineer Resume"})
    )

    def __init__(self, candidate, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["existing_resume"].queryset = Resume.objects.filter(candidate=candidate)
        # Pre-select default resume if one exists
        default = Resume.objects.filter(candidate=candidate, is_default=True).first()
        if default:
            self.fields["existing_resume"].initial = default.pk

    def clean(self):
        cleaned = super().clean()
        existing = cleaned.get("existing_resume")
        new_file = cleaned.get("new_resume")
        if not existing and not new_file:
            raise forms.ValidationError("Please select a saved resume or upload a new one.")
        return cleaned


class ResumeUploadForm(forms.ModelForm):
    """Standalone resume upload from the candidate's profile / resume manager."""
    class Meta:
        model = Resume
        fields = ["file", "label", "is_default"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"accept": ".pdf"}),
            "label": forms.TextInput(attrs={"placeholder": "e.g. Backend Developer Resume"}),
        }
        labels = {
            "is_default": "Set as my default resume",
        }


class ApplicationStatusForm(forms.ModelForm):
    """Company updates application status + adds an internal note."""
    class Meta:
        model = Application
        fields = ["status", "company_note"]
        widgets = {
            "status": forms.Select(),
            "company_note": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Internal note about this candidate (not visible to them)..."
            }),
        }
