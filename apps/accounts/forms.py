"""Forms for the accounts app."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class RegistrationForm(UserCreationForm):
    """Form for user registration with email."""

    email = forms.EmailField(
        required=True,
        help_text=_("Required. Enter a valid email address."),
        widget=forms.EmailInput(
            attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500",
                "placeholder": "Email address",
            }
        ),
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Add Tailwind classes to all fields
        for field_name, field in self.fields.items():
            field.widget.attrs.update(
                {
                    "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500",
                }
            )
        self.fields["username"].widget.attrs["placeholder"] = "Username"
        self.fields["password1"].widget.attrs["placeholder"] = "Password"
        self.fields["password2"].widget.attrs["placeholder"] = "Confirm password"

    def save(self, commit: bool = True) -> User:
        """Save the user with email."""
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    """Form for user login."""

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500",
                "placeholder": "Username",
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500",
                "placeholder": "Password",
            }
        )
    )
