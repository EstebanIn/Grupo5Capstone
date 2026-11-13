"""Perfil HTTPS para acceso temporal desde un computador mediante Cloudflare Tunnel."""
import os
import re
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403

PUBLIC_HOST = os.environ.get('TUNEL_PUBLIC_HOST', '')
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com', PUBLIC_HOST):
    raise ImproperlyConfigured('Configura el hostname exacto del túnel temporal.')
if len(SECRET_KEY)<60:
    raise ImproperlyConfigured('El acceso remoto requiere una clave Django privada de al menos 60 caracteres.')
if IA_PROVEEDOR not in ('gemini','qwen'):  # noqa: F405
    raise ImproperlyConfigured('Selecciona Gemini o Qwen para el acceso remoto.')
DEBUG = False
ALLOWED_HOSTS = [PUBLIC_HOST, 'localhost', '127.0.0.1', 'app', 'testserver']
CSRF_TRUSTED_ORIGINS = ['https://' + PUBLIC_HOST]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = False
SECURE_SSL_HOST = PUBLIC_HOST
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_HSTS_SECONDS = 3600
STATIC_ROOT = Path(os.environ.get('DJANGO_STATIC_ROOT', str(BASE_DIR / 'staticfiles')))  # noqa: F405
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'}}


class SinCachePrivada:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        if not request.path.startswith('/static/'):
            respuesta['Cache-Control'] = 'private, no-store, max-age=0'
            respuesta['Pragma'] = 'no-cache'
        return respuesta


MIDDLEWARE = ['django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', 'config.tunnel.SinCachePrivada',
    *[m for m in MIDDLEWARE if m != 'django.middleware.security.SecurityMiddleware']]  # noqa: F405
LOGGING = {'version': 1, 'disable_existing_loggers': False,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    'loggers': {nombre: {'handlers': ['null'], 'propagate': False}
                for nombre in ('django.request', 'httpx', 'httpcore')}}
