from django import forms
from .models import Job, Skill


# In jobs/forms.py — add qualification_required to JobForm fields

# Find your existing fields list in JobForm and add "qualification_required":

class JobForm(forms.ModelForm):
    """
    Form for creating / editing a Job posting.
    Skills are entered as a comma-separated string and resolved to
    Skill instances on save (get_or_create pattern).
    """

    # Skill input: comma-separated plain text (e.g. "Python, Django, REST")
    skills_input = forms.CharField(
        required=False,
        label="Required Skills",
        widget=forms.TextInput(attrs={
            "placeholder": "e.g. Python, Django, PostgreSQL, Docker",
            "id": "skills_input",
        }),
        help_text="Separate skills with commas"
    )

    class Meta:
        model = Job
        fields = [
            "title",
            "description",
            "requirements",
            "responsibilities",
            "experience_required",
            "qualification_required",   # ← new
            "location",
            "job_type",
            "salary_min",
            "salary_max",
            "salary_currency",
            "deadline",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "placeholder": "e.g. Senior Django Developer"
            }),
            "description": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Describe the role, team, and what makes this opportunity exciting..."
            }),
            "requirements": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "• Bachelor's degree in CS or related field\n• 3+ years Django experience\n• Strong SQL skills"
            }),
            "responsibilities": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "• Design and build scalable REST APIs\n• Collaborate with the frontend team\n• Conduct code reviews"
            }),
            "experience_required": forms.NumberInput(attrs={
                "placeholder": "2", "min": 0
            }),
            "qualification_required": forms.Select(),   # ← new
            "location": forms.TextInput(attrs={
                "placeholder": "Kathmandu, NP  or  Remote"
            }),
            "salary_min": forms.NumberInput(attrs={
                "placeholder": "50000"
            }),
            "salary_max": forms.NumberInput(attrs={
                "placeholder": "80000"
            }),
            "salary_currency": forms.TextInput(attrs={
                "placeholder": "NPR"
            }),
            "deadline": forms.DateInput(attrs={
                "type": "date"
            }),
            "job_type": forms.Select(),
            "status": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate skills_input when editing an existing instance
        if self.instance.pk:
            self.fields["skills_input"].initial = ", ".join(
                self.instance.skills.values_list("name", flat=True)
            )

    def save(self, commit=True):
        job = super().save(commit=commit)
        if commit:
            # Resolve skills from comma-separated input
            raw = self.cleaned_data.get("skills_input", "")
            skill_names = [s.strip() for s in raw.split(",") if s.strip()]
            skill_objs = []
            for name in skill_names:
                obj, _ = Skill.objects.get_or_create(name__iexact=name, defaults={"name": name.title()})
                skill_objs.append(obj)
            job.skills.set(skill_objs)
        return job


class JobFilterForm(forms.Form):
    """Lightweight search/filter form for the job listing page."""

    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(attrs={"placeholder": "Job title, company, or skill..."})
    )
    job_type = forms.ChoiceField(
        required=False,
        choices=[("", "All Types")] + list(Job.JobType.choices)
    )
    experience = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Any Experience"),
            ("0", "Fresher (0 yrs)"),
            ("1", "1+ years"),
            ("3", "3+ years"),
            ("5", "5+ years"),
        ]
    )
    location = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Location..."})
    )