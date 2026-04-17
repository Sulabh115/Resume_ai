from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User

class EmailBackend(ModelBackend):
    """
    Custom Authentication Backend that allows users to log in using 
    their email address instead of their username.
    """
    def authenticate(self, request, email=None, username=None, password=None, **kwargs):
        # Accept 'email' directly or fallback to 'username'
        identifier = email or username
        if not identifier:
            return None
        try:
            # Check if there's a user with this email
            user = User.objects.get(email__iexact=identifier)
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # If multiple users have the same email, we'll try to log into the first one.
            # This is a fallback measure; ideal databases have unique emails.
            user = User.objects.filter(email__iexact=username).order_by('id').first()

        # If we found a user and the password matches
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
            
        return None
