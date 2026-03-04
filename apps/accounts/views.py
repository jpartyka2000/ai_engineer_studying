"""Views for the accounts app."""

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, RegistrationForm


@require_http_methods(["GET", "POST"])
def register_view(request):
    """Handle user registration."""
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, _("Account created successfully! Welcome!"))
            return redirect("home")
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, _("Welcome back!"))
                # Redirect to next URL if provided, otherwise home
                next_url = request.GET.get("next", "home")
                return redirect(next_url)
            else:
                messages.error(request, _("Invalid username or password."))
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """Handle user logout."""
    if request.method == "POST":
        logout(request)
        messages.info(request, _("You have been logged out."))
        return redirect("home")
    return render(request, "accounts/logout.html")


@login_required
def profile_view(request):
    """Display user profile/dashboard with study statistics."""
    from apps.core.services.dashboard_service import get_dashboard_service

    service = get_dashboard_service()

    context = {
        "summary": service.get_dashboard_summary(request.user),
        "subject_breakdown": service.get_subject_breakdown(request.user),
        "recent_activity": service.get_recent_activity(request.user, limit=10),
        "weakest_subjects": service.get_weakest_subjects(request.user, limit=3),
        "strongest_subjects": service.get_strongest_subjects(request.user, limit=3),
    }

    return render(request, "accounts/profile.html", context)
