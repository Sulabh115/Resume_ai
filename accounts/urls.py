from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    #home
    path("", views.index, name="index"), 

    # Auth
    path("login/",               views.user_login,          name="login"),
    path("logout/",              views.user_logout,         name="logout"),

    # Registration
    path("register/", views.register, name="register"),

    # Password reset
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("reset-password/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/login/"          # FIX #2: was "/accounts/login/" which 404s because
                                           # accounts URLs are mounted at "" (root), not "/accounts/".
                                           # The login URL is therefore /login/, not /accounts/login/.
        ),
        name="password_reset_confirm",
),
    # Dashboards  (no separate dashboard app needed — views live in accounts/views.py)
    path("dashboard/candidate/", views.candidate_dashboard,      name="candidate_dashboard"),
    path("dashboard/company/",   views.company_dashboard,        name="company_dashboard"),

    # Profile edit
    path("profile/edit/",         views.candidate_edit_profile, name="candidate_edit_profile"),
    path("profile/company/edit/", views.company_edit_profile,   name="company_edit_profile"),
    # path("account/delete/",       views.delete_company_account, name="delete_company_account"),
]