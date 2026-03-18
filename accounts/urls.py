from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path("login/",              views.user_login,         name="login"),
    path("logout/",             views.user_logout,        name="logout"),
    path("register/candidate/", views.candidate_register, name="candidate_register"),
    path("register/company/",   views.company_register,   name="company_register"),
    path("forgot-password/",    views.forgot_password,    name="forgot_password"),

    # Django built-in password reset confirm (handles token validation + new password form)
    path(
        "reset-password/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/accounts/login/"
        ),
        name="password_reset_confirm",
    ),

    # # Dashboards
    path("dashboard/candidate/", views.candidate_dashboard, name="candidate_dashboard"),
    path("dashboard/company/",   views.company_dashboard,   name="company_dashboard"),
]