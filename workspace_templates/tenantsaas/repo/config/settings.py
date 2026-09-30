"""Django settings for the tenantsaas billing platform."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-a-real-secret")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "tenants",
    "projects",
    "billing",
    "api",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    # Resolves the current tenant from the X-Api-Key header and stashes it in a
    # ContextVar for the request's duration. See tenants/middleware.py.
    "tenants.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = []


def _database_from_env() -> dict:
    """Build the DATABASES entry from DATABASE_URL.

    Falls back to localhost so that running the suite outside the container (with a
    port-forwarded database) also works.
    """
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres"):
        # postgresql://user:password@host:port/name
        without_scheme = url.split("://", 1)[1]
        credentials, _, location = without_scheme.partition("@")
        user, _, password = credentials.partition(":")
        host_port, _, name = location.partition("/")
        host, _, port = host_port.partition(":")
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": name or "tenantsaas",
            "USER": user or "postgres",
            "PASSWORD": password or "postgres",
            "HOST": host or "db",
            "PORT": port or "5432",
        }
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "tenantsaas"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }


DATABASES = {"default": _database_from_env()}

# RDS deployment metadata. Amazon RDS is a managed service and cannot run locally,
# so it is emulated: the database is a plain Postgres container, while the
# operational artifacts a real RDS deployment carries live here and in
# config/rds-parameter-group.json.
RDS = {
    "instance_identifier": os.environ.get("RDS_INSTANCE_IDENTIFIER", "tenantsaas-prod-1"),
    "parameter_group": os.environ.get("RDS_PARAMETER_GROUP", "tenantsaas-pg16-custom"),
    "iam_auth_enabled": os.environ.get("RDS_IAM_AUTH_ENABLED", "true") == "true",
    "read_replica_endpoint": os.environ.get("RDS_READ_REPLICA_ENDPOINT", ""),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
USE_I18N = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
