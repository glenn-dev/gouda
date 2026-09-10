"""Minimal Django settings for the Gouda persistence foundation."""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent



def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must be provided through the environment")
    return value


SECRET_KEY = _required_environment("DJANGO_SECRET_KEY")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
# Defense in depth for the supported numeric-loopback local launcher. Host
# validation does not replace the launcher's bind enforcement or authenticate.
ALLOWED_HOSTS = ["127.0.0.1", "[::1]"]
USE_X_FORWARDED_HOST = False
SECURE_PROXY_SSL_HEADER = None
DEFAULT_EXCEPTION_REPORTER_FILTER = "gouda.safe_http_logging.ClassificationExceptionReporterFilter"
DEFAULT_EXCEPTION_REPORTER = "gouda.safe_http_logging.ClassificationExceptionReporter"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"safe_http": {"()": "gouda.safe_http_logging.SafeHttpLogFilter"}},
    "handlers": {
        "safe_console": {
            "class": "logging.StreamHandler", "filters": ["safe_http"],
        },
    },
    "loggers": {
        "django": {"handlers": ["safe_console"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["safe_console"], "level": "INFO", "propagate": False},
    },
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "rest_framework",
    "gouda.ledger",
]

MIDDLEWARE: list[str] = []
ROOT_URLCONF = "config.urls"
TEMPLATES: list[dict[str, object]] = []
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "gouda"),
        "USER": os.environ.get("POSTGRES_USER", "gouda"),
        "PASSWORD": _required_environment("POSTGRES_PASSWORD"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

# PostgreSQL emits SQL and failing-row DETAIL independently of Python logging.
# Apply before the first query, on every private connection (including host
# development and reconnects). A role unable to set these fails to connect.
if DATABASES["default"]["NAME"] == "gouda_private":
    DATABASES["default"]["OPTIONS"] = {"options": " ".join(
        "-c " + setting for setting in (
            "log_min_messages=panic", "log_min_error_statement=panic",
            "log_statement=none", "log_duration=off", "log_min_duration_statement=-1",
            "log_min_duration_sample=-1", "log_transaction_sample_rate=0",
            "log_parameter_max_length=0", "log_parameter_max_length_on_error=0",
        )
    )}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
}
