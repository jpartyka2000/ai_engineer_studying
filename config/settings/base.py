"""
Django base settings for AI Interview Prep project.

Common settings shared across all environments.
"""

from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize django-environ
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

# Read .env file if it exists
environ.Env.read_env(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production")

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "django_extensions",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.subjects",
    "apps.questions",
    "apps.exam",
    "apps.lightning",
    "apps.qanda",
    "apps.visuals",
    "apps.coding",
    "apps.argument",
    "apps.readiness",
    "apps.equations",
    "apps.systemdesign",
    "apps.workspace",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"

# Anthropic Claude API
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
CLAUDE_MODEL = "claude-opus-4-5-20251101"

# OpenAI API
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_MODEL = env("OPENAI_MODEL", default="gpt-5.2")

# Default LLM provider for question generation: "claude" or "openai"
LLM_PROVIDER = env("LLM_PROVIDER", default="claude")

# ---------------------------------------------------------------------------
# Workspace mode ("Work With Existing Codebase")
# ---------------------------------------------------------------------------
# Exercise workspaces are real directories on disk that the user works in with
# their own terminal, editor and browser. WORKSPACE_ROOT defaults inside the
# project (and is gitignored) so the app never writes outside the project
# directory; set the env var to relocate it, e.g. ~/ai-prep-workspaces.
WORKSPACE_ROOT = Path(env("WORKSPACE_ROOT", default=str(BASE_DIR / "workspaces"))).expanduser()
WORKSPACE_TEMPLATE_ROOT = BASE_DIR / "workspace_templates"

# Rubric calibration state: blind grading packets, the hand-filled scoresheet and
# the accumulating human-versus-system corpus. Inside the project because the
# hand-assigned letters are source material -- they are the only record of what a
# human thought, and the regression corpus that defends against grading drift.
WORKSPACE_CALIBRATION_ROOT = BASE_DIR / "calibration"

# Finished workspaces are MOVED here rather than deleted, so a mid-exercise
# mistake never destroys work. Bare "origin" repos emulating GitHub live here.
WORKSPACE_ARCHIVE_DIRNAME = ".archive"
WORKSPACE_ORIGINS_DIRNAME = ".origins"

# A directory is only ever deleted if it carries this sentinel file, proving
# this app created it. See apps/workspace/services/paths.py.
WORKSPACE_SENTINEL_FILENAME = ".ai-prep-workspace"

# Time box: 20 minutes minimum, 60 maximum. Enforced by model validators too.
WORKSPACE_MIN_TIME_LIMIT_SECONDS = 20 * 60
WORKSPACE_MAX_TIME_LIMIT_SECONDS = 60 * 60
# A submit fired at T-2s whose capture takes 6s must not be rejected.
WORKSPACE_SUBMIT_GRACE_SECONDS = 30
WORKSPACE_HEARTBEAT_INTERVAL_SECONDS = 15
# Environment probing shells out to docker and git, so the report is cached
# briefly; the Re-check button bypasses it.
WORKSPACE_DOCTOR_CACHE_SECONDS = 10

# Prompt budget for grading. Budgeted in characters (~3.5 chars/token) rather
# than tokens so no tokenizer dependency is needed.
WORKSPACE_MAX_DIFF_CHARS = 200_000
WORKSPACE_MAX_FILE_DIFF_CHARS = 20_000

# Host ports for per-exercise containers. Deliberately clear of the study app's
# own Postgres (5432) and Redis (6379); in-container addressing is unchanged.
WORKSPACE_PORT_RANGE = (55000, 55999)
WORKSPACE_RESERVED_PORTS = [5432, 6379, 8000, 27017]

# Subprocess timeouts (seconds). Every external command gets one.
WORKSPACE_GIT_TIMEOUT_SECONDS = 30
WORKSPACE_SCAFFOLD_TIMEOUT_SECONDS = 180
WORKSPACE_COMPOSE_UP_TIMEOUT_SECONDS = 300
WORKSPACE_COMPOSE_DOWN_TIMEOUT_SECONDS = 120
WORKSPACE_CHECK_TIMEOUT_SECONDS = 600

# Read-only file browser limits.
WORKSPACE_TREE_MAX_ENTRIES = 2000
WORKSPACE_FILE_PREVIEW_MAX_BYTES = 256_000

# Destructive cleanup is off unless explicitly enabled, so a stray invocation
# (e.g. from CI) cannot wipe archived work.
WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP = env.bool("WORKSPACE_ALLOW_DESTRUCTIVE_CLEANUP", default=False)
WORKSPACE_ARCHIVE_RETENTION_DAYS = 7
WORKSPACE_STALE_PREPARE_HOURS = 2

# Celery Configuration
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Fail fast when the broker is down instead of blocking the web request.
# By default Celery retries a lost connection 20 times at one-second intervals, so
# a `.delay()` with Redis stopped would hang a page load for 20+ seconds before the
# caller could fall back. Callers are expected to handle the exception.
CELERY_TASK_PUBLISH_RETRY = False
CELERY_BROKER_CONNECTION_TIMEOUT = 2
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = False
CELERY_BROKER_TRANSPORT_OPTIONS = {"max_retries": 0}
CELERY_RESULT_BACKEND_ALWAYS_RETRY = False
CELERY_REDIS_RETRY_ON_TIMEOUT = False

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
