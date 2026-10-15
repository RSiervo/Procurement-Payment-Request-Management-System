import sys
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    EMAIL_PORT=(int, 587),
    EMAIL_USE_TLS=(bool, True),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
if env.bool("ALLOW_LAN_HOSTS", default=False):
    # Development on an office network: accept this machine's current IP addresses
    # (not its hostname), so a DHCP address change only needs a restart, not an edit.
    import socket

    ALLOWED_HOSTS += socket.gethostbyname_ex(socket.gethostname())[2]
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.messages",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "apps.core",
    "apps.users",
    "apps.workflows",
    "apps.requests",
    "apps.approvals",
    "apps.notifications",
    "apps.audit",
    "apps.reports",
    "apps.automation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.audit.middleware.RequestContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"

# Active Directory sign-in (optional). Tried first; local accounts still work after it.
AUTH_LDAP_SERVER_URI = env("AUTH_LDAP_SERVER_URI", default="")
AUTH_LDAP_BIND_DN = env("AUTH_LDAP_BIND_DN", default="")
AUTH_LDAP_BIND_PASSWORD = env("AUTH_LDAP_BIND_PASSWORD", default="")
AUTH_LDAP_VERIFY_CERT = env.bool("AUTH_LDAP_VERIFY_CERT", default=True)
AUTH_LDAP_CA_CERT_FILE = env("AUTH_LDAP_CA_CERT_FILE", default="")


def _semicolon_list(name):
    return [item.strip() for item in env(name, default="").split(";") if item.strip()]


# Distinguished names contain commas, so lists here are separated by semicolons.
AUTH_LDAP_USER_SEARCH_BASES = _semicolon_list("AUTH_LDAP_USER_SEARCH_BASES")
# People anywhere beneath an OU with one of these names become portal administrators.
AUTH_LDAP_ADMIN_OUS = _semicolon_list("AUTH_LDAP_ADMIN_OUS")
# Further role mappings, e.g. FINANCE=BILLING AND COLLECTION|ACCOUNTING;OPS=OPERATIONS EXCELLENCE
AUTH_LDAP_ROLE_OUS = {
    code.strip().upper(): [ou.strip() for ou in ous.split("|") if ou.strip()]
    for code, _, ous in (item.partition("=") for item in _semicolon_list("AUTH_LDAP_ROLE_OUS"))
}

AUTHENTICATION_BACKENDS = [
    "apps.users.directory.ActiveDirectoryBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

if "test" in sys.argv[1:2]:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only; never used outside tests
    AUTH_LDAP_SERVER_URI = ""  # tests never contact the real directory

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="Asia/Manila")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded files are never served directly; they go through authenticated views.
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- Sessions, cookies, transport -------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = [FRONTEND_URL]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30

# --- API ---------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"login": "10/min", "verify": "30/min", "password_reset": "5/hour", "password_reset_confirm": "20/hour"},
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
}

# An emailed password-reset link works for one hour.
PASSWORD_RESET_TIMEOUT = 60 * 60

# --- Email -------------------------------------------------------------------
EMAIL_HOST = env("EMAIL_HOST", default="")
if env.bool("EMAIL_DISABLED", default=False):
    # For test copies of the portal: never talk to the mail server, whatever .env says.
    EMAIL_HOST = ""
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
EMAIL_TIMEOUT = 5
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Procurement Portal <no-reply@localhost>")
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST
    else "django.core.mail.backends.console.EmailBackend"
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
