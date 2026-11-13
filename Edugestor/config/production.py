import os
from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403

DEBUG = False
PUBLIC_HOST = os.environ.get('PUBLIC_HOST', '')
ORIGIN_SHARED_SECRET = os.environ.get('ORIGIN_SHARED_SECRET', '')
if not PUBLIC_HOST.endswith('.workers.dev') or '/' in PUBLIC_HOST or len(ORIGIN_SHARED_SECRET) < 32:
    raise ImproperlyConfigured('Configura PUBLIC_HOST y un secreto de origen de al menos 32 caracteres.')
if not os.environ.get('DJANGO_SECRET_KEY') or not os.environ.get('POSTGRES_DB'):
    raise ImproperlyConfigured('Se requieren una clave Django privada y PostgreSQL.')
ALLOWED_HOSTS = [PUBLIC_HOST]
CSRF_TRUSTED_ORIGINS = ['https://' + PUBLIC_HOST]
ORIGIN_REQUIRE_WORKER = True
MIDDLEWARE = ['colegio.proxy.OrigenWorkerMiddleware',
              'django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
              *[m for m in MIDDLEWARE if m != 'django.middleware.security.SecurityMiddleware']]  # noqa: F405
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SECURE_HSTS_SECONDS = 31536000
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
DATA_UPLOAD_MAX_MEMORY_SIZE = 55 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
# No exponer sesiones, cuerpos HTTP, prompts o claves en trazas de producción.
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'handlers': {'null': {'class': 'logging.NullHandler'}},
           'loggers': {'django.request': {'handlers': ['null'], 'propagate': False},
                       'httpx': {'handlers': ['null'], 'propagate': False},
                       'httpcore': {'handlers': ['null'], 'propagate': False}}}
