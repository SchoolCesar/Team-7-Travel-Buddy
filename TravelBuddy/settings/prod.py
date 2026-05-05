from .base import *
import os
from decouple import config

DEBUG = False

# Render provides RENDER_EXTERNAL_HOSTNAME
ALLOWED_HOSTS = [
    config('RENDER_EXTERNAL_HOSTNAME', default='localhost'),
    'localhost',
    '127.0.0.1',
]

# Add any additional ALLOWED_HOSTS from .env
additional_hosts = config('ALLOWED_HOSTS', default='')
if additional_hosts:
    ALLOWED_HOSTS.extend(additional_hosts.split(','))

# Security settings for production
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

