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
            user = User.objects.get(email__iexact=identifier)
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # FIX: was filtering by `username` (None when email login is used),
            # which returned no results and caused AttributeError on check_password.
            # Must filter by `identifier` instead.
            user = User.objects.filter(email__iexact=identifier).order_by('id').first()
            if user is None:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None