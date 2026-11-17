import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('DJANGO_DEBUG', os.getenv('DEBUG', '1')) == '1'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', os.getenv('SECRET_KEY', 'development-only-productstat-do-not-deploy'))
if not DEBUG and (SECRET_KEY.lower().startswith(('development-','replace','change','example','default','your-secret','django-insecure')) or len(SECRET_KEY) < 40):
    raise ImproperlyConfigured('Production SECRET_KEY must be a unique secret of at least 40 characters.')
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver')).split(',')
CSRF_TRUSTED_ORIGINS = os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:8001')).split(',')
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','rest_framework','drf_spectacular','commerce']
MIDDLEWARE = ['commerce.middleware.RequestContextMiddleware','django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','commerce.middleware.APICSRFMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':os.getenv('PGDATABASE',os.getenv('POSTGRES_DB','productstat')),'USER':os.getenv('PGUSER',os.getenv('POSTGRES_USER','productstat')),'PASSWORD':os.getenv('PGPASSWORD',os.getenv('POSTGRES_PASSWORD','')),'HOST':os.getenv('PGHOST',os.getenv('POSTGRES_HOST','127.0.0.1')),'PORT':os.getenv('PGPORT',os.getenv('POSTGRES_PORT','55433')),'CONN_MAX_AGE':60}}
AUTH_USER_MODEL = 'commerce.User'
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/private-media/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(BASE_DIR / 'private_media')))
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
REST_FRAMEWORK = {'DEFAULT_AUTHENTICATION_CLASSES':['rest_framework.authentication.SessionAuthentication'],'DEFAULT_PERMISSION_CLASSES':['rest_framework.permissions.AllowAny'],'DEFAULT_SCHEMA_CLASS':'drf_spectacular.openapi.AutoSchema','DEFAULT_THROTTLE_CLASSES':['rest_framework.throttling.AnonRateThrottle','rest_framework.throttling.UserRateThrottle'],'DEFAULT_THROTTLE_RATES':{'anon':'300/hour','user':'3000/hour','login':'10/min','checkout':'20/min'},'EXCEPTION_HANDLER':'commerce.exceptions.exception_handler'}
SPECTACULAR_SETTINGS = {'TITLE':'ProductStat Commerce API','VERSION':'1.0.0','DESCRIPTION':'Single-company commerce operations and trustworthy product analytics.'}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REDIRECT_EXEMPT = [r'^api/v1/health/$',r'^health/$']
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')
PUBLIC_BASE_URL = os.getenv('PUBLIC_APP_URL',os.getenv('PUBLIC_BASE_URL','http://localhost:3000')).rstrip('/')
PRODUCTSTAT_DEMO = os.getenv('PRODUCTSTAT_DEMO','0') == '1'
SSLCOMMERZ_STORE_ID = os.getenv('SSLCOMMERZ_STORE_ID','')
SSLCOMMERZ_STORE_PASSWORD = os.getenv('SSLCOMMERZ_STORE_PASSWORD','')
SSLCOMMERZ_SANDBOX = os.getenv('SSLCOMMERZ_SANDBOX','1') == '1'
SSLCOMMERZ_LIVE_APPROVED = os.getenv('SSLCOMMERZ_LIVE_APPROVED','0') == '1'
if not SSLCOMMERZ_SANDBOX and not SSLCOMMERZ_LIVE_APPROVED:
    raise ImproperlyConfigured('Live payment collection requires SSLCOMMERZ_LIVE_APPROVED=1 after the documented live-payment gate.')
CELERY_BROKER_URL = os.getenv('REDIS_URL','redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
_reporting_redis = urlsplit(CELERY_BROKER_URL)
REPORTING_REDIS_URL = os.getenv('REPORTING_REDIS_URL',urlunsplit((_reporting_redis.scheme,_reporting_redis.netloc,'/1',_reporting_redis.query,_reporting_redis.fragment)))
CACHES = {
    'default': {'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'productstat-throttles'},
    'reporting': {'BACKEND':'django.core.cache.backends.redis.RedisCache','LOCATION':REPORTING_REDIS_URL,'KEY_PREFIX':'productstat-reporting-v1','TIMEOUT':30,'OPTIONS':{'socket_connect_timeout':0.5,'socket_timeout':0.5}},
}
CELERY_TASK_ALWAYS_EAGER = os.getenv('CELERY_TASK_ALWAYS_EAGER','0') == '1'
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BEAT_SCHEDULE = {'expire-reservations':{'task':'commerce.tasks.expire_reservations','schedule':60.0},'send-outbox':{'task':'commerce.tasks.deliver_outbox','schedule':30.0}}
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND','django.core.mail.backends.console.EmailBackend')
if PRODUCTSTAT_DEMO:
    EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL','orders@productstat.local')
EMAIL_HOST = os.getenv('EMAIL_HOST','')
EMAIL_PORT = int(os.getenv('EMAIL_PORT','587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER','')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD','')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS','1') == '1'
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
LOGGING = {'version':1,'disable_existing_loggers':False,'handlers':{'console':{'class':'logging.StreamHandler'},'null':{'class':'logging.NullHandler'}},'root':{'handlers':['console'],'level':os.getenv('LOG_LEVEL','INFO')},'loggers':{'django.server':{'handlers':['null'],'propagate':False}}}
