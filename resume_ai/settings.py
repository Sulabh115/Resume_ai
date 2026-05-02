from pathlib import Path
import os
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))


# ── Security ──────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("SECRET_KEY")

# ── Local vs Production Settings ──────────────────────────────────────────

# -- LOCAL DEVELOPMENT --
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=['127.0.0.1', 'localhost'])

# -- cPanel PRODUCTION (Uncomment when deploying) --
# DEBUG = False
# ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']


# ── Application definition ────────────────────────────────────────────────

AUTHENTICATION_BACKENDS = [
    'accounts.backends.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Tailwind CSS integration
    'tailwind',
    'theme',
    'django_browser_reload',

    # Custom apps
    'accounts',
    'applications',
    'jobs',
    'screening',
]

# django-tailwind settings
TAILWIND_APP_NAME = 'theme'
INTERNAL_IPS = ['127.0.0.1']
NPM_BIN_PATH = '/usr/local/bin/npm'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_browser_reload.middleware.BrowserReloadMiddleware',
]

ROOT_URLCONF = 'resume_ai.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'jobs.context_processors.to_shortlist_count',
                'applications.context_processors.active_applications_count',
            ],
        },
    },
]

WSGI_APPLICATION = 'resume_ai.wsgi.application'


# ── Database ──────────────────────────────────────────────────────────────

# -- LOCAL DEVELOPMENT (SQLite) --
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# -- cPanel PRODUCTION (MySQL - Uncomment and fill details when deploying) --
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': 'your_cpanel_db_name',
#         'USER': 'your_cpanel_db_user',
#         'PASSWORD': 'your_db_password',
#         'HOST': 'localhost',
#         'PORT': '3306',
#     }
# }


# ── Session configuration ─────────────────────────────────────────────────
#
# FIX #14: explicitly set SESSION_ENGINE to the DB backend.
#
# Why this matters:
#   SESSION_COOKIE_AGE  — maximum age of the session cookie in seconds.
#   SESSION_SAVE_EVERY_REQUEST — resets the expiry timer on every request
#                                (implements idle timeout, not absolute TTL).
#   SESSION_EXPIRE_AT_BROWSER_CLOSE — also expire when the browser closes.
#
# These three settings only work correctly when the session engine stores
# expiry metadata server-side.  The DB backend does this.  The cookie
# backend (django.contrib.sessions.backends.signed_cookies) ignores
# SESSION_SAVE_EVERY_REQUEST entirely, so idle timeout would silently
# not work if the engine were ever switched to cookies.
#
# The django_session table is created by `python manage.py migrate`
# via the django.contrib.sessions migration — already present.
#
SESSION_ENGINE              = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE          = 3600    # 1 hour idle timeout (seconds)
SESSION_SAVE_EVERY_REQUEST  = True    # reset timer on every request
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # also expire on browser close


# ══════════════════════════════════════════════════════════════════════════
# EMAIL CONFIGURATION  (E4)
# ══════════════════════════════════════════════════════════════════════════
#
# Three backends are supported, selected via EMAIL_BACKEND_TYPE in .env:
#
#   console  (default — development)
#            Emails are printed to stdout. No SMTP setup needed.
#            This is the zero-config option for local development.
#
#   smtp     (production)
#            Sends real emails via any SMTP provider.
#            Requires EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD.
#            Works with Gmail, SendGrid, Mailgun, AWS SES, Postmark, etc.
#
#   file     (CI / automated testing)
#            Writes each email as a .eml file under EMAIL_FILE_PATH.
#            Useful for integration tests that need to inspect email content
#            without a real SMTP server.
#
# ── Quick-start .env snippets ─────────────────────────────────────────────
#
# Development (nothing extra needed — console is the default):
#   DEBUG=True
#   EMAIL_BACKEND_TYPE=console
#
# Gmail / Google Workspace:
#   EMAIL_BACKEND_TYPE=smtp
#   EMAIL_HOST=smtp.gmail.com
#   EMAIL_PORT=587
#   EMAIL_USE_TLS=True
#   EMAIL_USE_SSL=False
#   EMAIL_HOST_USER=you@gmail.com
#   EMAIL_HOST_PASSWORD=abcd efgh ijkl mnop    # 16-char App Password
#   DEFAULT_FROM_EMAIL=YogyataRank <you@gmail.com>
#
#   IMPORTANT: Gmail requires an App Password, not your account password.
#   Generate one at https://myaccount.google.com/apppasswords
#   (2-Step Verification must be enabled on your Google account first.)
#
# SendGrid:
#   EMAIL_BACKEND_TYPE=smtp
#   EMAIL_HOST=smtp.sendgrid.net
#   EMAIL_PORT=587
#   EMAIL_USE_TLS=True
#   EMAIL_USE_SSL=False
#   EMAIL_HOST_USER=apikey
#   EMAIL_HOST_PASSWORD=SG.xxxxxxxxxxxxxxxxxxxx
#   DEFAULT_FROM_EMAIL=YogyataRank <noreply@yourdomain.com>
#
# Mailgun:
#   EMAIL_BACKEND_TYPE=smtp
#   EMAIL_HOST=smtp.mailgun.org
#   EMAIL_PORT=587
#   EMAIL_USE_TLS=True
#   EMAIL_USE_SSL=False
#   EMAIL_HOST_USER=postmaster@mg.yourdomain.com
#   EMAIL_HOST_PASSWORD=your-mailgun-smtp-password
#   DEFAULT_FROM_EMAIL=YogyataRank <noreply@yourdomain.com>
#
# AWS SES (SMTP interface):
#   EMAIL_BACKEND_TYPE=smtp
#   EMAIL_HOST=email-smtp.<region>.amazonaws.com
#   EMAIL_PORT=587
#   EMAIL_USE_TLS=True
#   EMAIL_USE_SSL=False
#   EMAIL_HOST_USER=AKIA...          # SES SMTP username (not IAM key)
#   EMAIL_HOST_PASSWORD=...          # SES SMTP password
#   DEFAULT_FROM_EMAIL=YogyataRank <noreply@yourdomain.com>
#
# File backend (CI / integration testing):
#   EMAIL_BACKEND_TYPE=file
#   EMAIL_FILE_PATH=/tmp/YogyataRank-emails
#
# ── TLS vs SSL ────────────────────────────────────────────────────────────
#
#   EMAIL_USE_TLS=True  + port 587  →  STARTTLS (recommended for all providers)
#   EMAIL_USE_SSL=True  + port 465  →  Implicit SSL (legacy, avoid if possible)
#
#   Never set both EMAIL_USE_TLS and EMAIL_USE_SSL to True simultaneously —
#   Django raises ImproperlyConfigured if you do.
#   For all modern providers, TLS on port 587 is the correct choice.
#
# ── Connection timeout ────────────────────────────────────────────────────
#
#   EMAIL_TIMEOUT sets how many seconds Django waits for the SMTP server
#   before raising an exception. Without this, a slow or unreachable
#   SMTP server can hang a web request indefinitely.
#   Default: 10 seconds. Lower to 5 if email latency is affecting page load.
#
# ═════════════════════════════════════════════════════════════════════════

_email_backend_type = env('EMAIL_BACKEND_TYPE', default='console')

if _email_backend_type == 'smtp':
    # ── SMTP backend ──────────────────────────────────────────────────────
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

    # Outgoing mail server hostname
    EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')

    # Port — 587 for STARTTLS (recommended), 465 for implicit SSL
    EMAIL_PORT = env.int('EMAIL_PORT', default=587)

    # STARTTLS — upgrades a plain connection to encrypted mid-session.
    # Use with port 587. Mutually exclusive with EMAIL_USE_SSL.
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)

    # Implicit SSL — connection is encrypted from the start.
    # Use with port 465. Mutually exclusive with EMAIL_USE_TLS.
    EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)

    # SMTP authentication credentials
    EMAIL_HOST_USER     = env('EMAIL_HOST_USER',     default='')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')

    # Seconds to wait for SMTP server response before timing out.
    # Prevents a slow or dead SMTP server from hanging web requests.
    EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=10)

elif _email_backend_type == 'file':
    # ── File backend — development / CI ──────────────────────────────────
    # Each email is written as a separate file under EMAIL_FILE_PATH.
    # Files can be opened in any email client or inspected as plain text.
    EMAIL_BACKEND   = 'django.core.mail.backends.filebased.EmailBackend'
    EMAIL_FILE_PATH = env('EMAIL_FILE_PATH', default=str(BASE_DIR / 'sent-emails'))

else:
    # ── Console backend — default for local development ───────────────────
    # Prints the complete email (headers + plain text + HTML) to the Django
    # dev server console. Zero configuration required.
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


# ── Sender address ────────────────────────────────────────────────────────
#
# The From: header on all outgoing emails sent by YogyataRank:
#   - Password reset emails        (accounts/views.py forgot_password)
#   - Shortlist interview emails   (jobs/views.py send_shortlist_email)
#   - Application status emails    (applications/views.py _send_status_notification)
#
# Format: "Display Name <address@domain.com>"
# Must match (or be an authorised sender for) your SMTP account.
# Mismatched From addresses are the most common cause of spam-folder delivery.
#
DEFAULT_FROM_EMAIL = env(
    'DEFAULT_FROM_EMAIL',
    default='YogyataRank <noreply@YogyataRank.local>',
)

# Address used for Django admin error emails (500 errors sent to ADMINS).
# Set to the same value as DEFAULT_FROM_EMAIL unless you want a separate
# address for server-error alerts.
SERVER_EMAIL = env('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)


# ── Password reset token lifetime ────────────────────────────────────────
#
# How long the reset link in the forgot-password email remains valid.
#
# Django default: 259200 seconds (3 days).
# YogyataRank default: 86400 seconds (24 hours) — matches the "valid for
# 24 hours" message shown in forgot_password.html and the email template.
#
# If you change this value, update the user-facing copy in:
#   templates/accounts/forgot_password.html  (the steps list)
#   templates/accounts/email/password_reset.html  (expiry warning box)
#
PASSWORD_RESET_TIMEOUT = env.int('PASSWORD_RESET_TIMEOUT', default=86400)

# ── Password validation ───────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ── Internationalisation ──────────────────────────────────────────────────

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# ── Static files ──────────────────────────────────────────────────────────

# -- LOCAL DEVELOPMENT --
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# -- cPanel PRODUCTION (Uncomment when deploying) --
# STATIC_URL = '/static/'
# Replace 'your_username' with your actual cPanel username
# STATIC_ROOT = '/home/your_username/public_html/static'


# ── Media files ───────────────────────────────────────────────────────────

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ── Default primary key field type ───────────────────────────────────────

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
