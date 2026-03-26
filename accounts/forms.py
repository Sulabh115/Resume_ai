from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import CandidateProfile, CompanyProfile


class CandidateRegistrationForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "John"})
    )
    last_name = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Doe"})
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "john@example.com"})
    )
    # Optional profile fields — saved to CandidateProfile after user creation
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "+977 98XXXXXXXX"})
    )
    skills = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Python, Django, React..."})
    )
    experience = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"placeholder": "0"})
    )
    education = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"placeholder": "BSc Computer Science...", "rows": 2})
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save()
            # Create CandidateProfile with optional fields
            CandidateProfile.objects.create(
                user=user,
                phone=self.cleaned_data.get("phone") or "",
                skills=self.cleaned_data.get("skills") or "",
                experience=self.cleaned_data.get("experience") or 0,
                education=self.cleaned_data.get("education") or "",
            )
        return user


class CompanyRegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "hr@acme.com"})
    )
    # ── New: HR's own phone number ────────────────────────────────────────
    hr_phone = forms.CharField(
        max_length=20,
        required=False,
        label="Your Phone",
        widget=forms.TextInput(attrs={"placeholder": "+977 98XXXXXXXX"})
    )
    company_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "Acme Corporation"})
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={"placeholder": "Tell candidates about your company...", "rows": 3})
    )
    website = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={"placeholder": "https://acme.com"})
    )
    location = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Kathmandu, NP"})
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save()
            CompanyProfile.objects.create(
                user=user,
                company_name=self.cleaned_data["company_name"],
                description=self.cleaned_data.get("description", ""),
                website=self.cleaned_data.get("website") or None,
                location=self.cleaned_data.get("location") or None,
                # phone is saved here from hr_phone field
                phone=self.cleaned_data.get("hr_phone") or "",
            )
        return user
    
class ForgotPasswordForm(forms.Form):
    """Sends a password reset link to the provided email."""
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"placeholder": "Enter your registered email"})
    )

    def clean_email(self):
        email = self.cleaned_data["email"]
        if not User.objects.filter(email=email).exists():
            raise forms.ValidationError("No account found with this email address.")
        return email