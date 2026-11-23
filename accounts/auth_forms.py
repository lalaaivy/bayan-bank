from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model

from .models import Role


User = get_user_model()


class BayanAuthenticationForm(AuthenticationForm):
    """
    Standard Django authentication form with inactive-client detection.

    An inactive client is identified only when the submitted password
    is correct. This does not activate the account or authenticate the
    inactive user.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.inactive_client = False

    def clean(self):
        try:
            return super().clean()

        except forms.ValidationError:
            username = self.cleaned_data.get("username")
            password = self.cleaned_data.get("password")

            if username and password:
                user = User.objects.filter(
                    username__iexact=username
                ).select_related("role").first()

                if (
                    user
                    and not user.is_active
                    and user.check_password(password)
                    and user.role.name == Role.CLIENT
                ):
                    self.inactive_client = True

            raise