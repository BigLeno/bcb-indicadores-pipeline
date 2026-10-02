"""Configuração da API, toda lida de variáveis de ambiente."""

import os

from django.core.exceptions import ImproperlyConfigured


def _env(nome: str, padrao: str | None = None) -> str:
    valor = os.environ.get(nome, padrao)
    if valor is None:
        raise ImproperlyConfigured(f"variável de ambiente obrigatória não definida: {nome}")
    return valor


SECRET_KEY = _env("DJANGO_SECRET_KEY")
DEBUG = _env("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in _env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")]

# Sem admin, auth nem sessions: a API é pública, somente leitura e sem estado.
INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "indicadores",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,  # templates do Swagger UI (drf-spectacular)
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": _env("API_DB_HOST", "localhost"),
        "PORT": _env("API_DB_PORT", "5432"),
        "NAME": _env("API_DB_NAME"),
        "USER": _env("API_DB_USER"),
        "PASSWORD": _env("API_DB_PASSWORD"),
        # Os models apontam para tabelas sem schema; o search_path resolve marts e staging.
        "OPTIONS": {"options": "-c search_path=marts,staging"},
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Sem autenticação: não importa django.contrib.auth nem exige tabelas de usuário.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    # Só JSON; a exploração interativa fica no Swagger UI (/api/docs/).
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "indicadores.pagination.Paginacao",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Limite por IP; o contador fica no cache local de cada worker do gunicorn.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": _env("API_THROTTLE_ANON", "120/min")},
}

SPECTACULAR_SETTINGS = {
    "TITLE": "BCB Indicadores API",
    "DESCRIPTION": (
        "Indicadores econômicos da API SGS do Banco Central do Brasil, "
        "carregados pelo pipeline bcb-indicadores. Somente leitura. "
        "Valores decimais vêm como string, para preservar o valor exato."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": _env("DJANGO_LOG_LEVEL", "INFO")},
}
