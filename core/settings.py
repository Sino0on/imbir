from pathlib import Path
from datetime import timedelta
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-in-production')

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*').split(',')

_csrf_raw = config("CSRF_TRUSTED_ORIGINS", default="")
CSRF_TRUSTED_ORIGINS = [o for o in _csrf_raw.split(",") if o.strip()]

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',

    'users',
    'doctors',
    'clinics',
    'services',
    'references',
    'appointments',
    'reviews',
    'profile',
    'doctor',
    'clinic',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Asia/Bishkek'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Imbir Medical Portal API',
    'DESCRIPTION': 'REST API медицинского портала Imbir — врачи, клиники, записи, отзывы.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/',
    'ENUM_NAME_OVERRIDES': {
        'FavoriteTargetTypeEnum': 'users.models.Favorite.TargetType',
        'ReviewTargetTypeEnum': 'reviews.models.Review.TargetType',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

CORS_ALLOW_ALL_ORIGINS = DEBUG

JAZZMIN_SETTINGS = {
    'site_title': 'Imbir Admin',
    'site_header': 'Imbir Medical',
    'site_brand': 'Imbir',
    'site_logo': None,
    'welcome_sign': 'Добро пожаловать в Imbir Medical Portal',
    'copyright': 'Imbir Medical Portal',
    'search_model': ['users.User', 'appointments.Appointment'],
    'user_avatar': None,

    'topmenu_links': [
        {'name': 'Сайт', 'url': '/', 'permissions': ['auth.view_user']},
        {'name': 'API Docs', 'url': '/api/docs/', 'new_window': True},
        {'model': 'users.User'},
    ],

    'usermenu_links': [
        {'name': 'API Docs', 'url': '/api/docs/', 'new_window': True},
        {'model': 'auth.user'},
    ],

    'show_sidebar': True,
    'navigation_expanded': True,

    'hide_apps': ['auth', 'token_blacklist'],
    'hide_models': [],

    'order_with_respect_to': [
        'users',
        'users.User',
        'users.DoctorProfile',
        'users.PatientProfile',
        'users.ClinicProfile',
        'users.ClinicBranch',
        'users.ClinicInvite',
        'users.DoctorClinicLink',
        'appointments',
        'reviews',
        'services',
    ],

    'icons': {
        'auth': 'fas fa-users-cog',
        'users.User': 'fas fa-user',
        'users.DoctorProfile': 'fas fa-user-md',
        'users.PatientProfile': 'fas fa-procedures',
        'users.ClinicProfile': 'fas fa-hospital',
        'users.ClinicBranch': 'fas fa-code-branch',
        'users.ClinicInvite': 'fas fa-envelope-open-text',
        'users.DoctorClinicLink': 'fas fa-link',
        'users.Favorite': 'fas fa-heart',
        'appointments.Appointment': 'fas fa-calendar-check',
        'reviews.Review': 'fas fa-star',
        'services.Service': 'fas fa-concierge-bell',
    },

    'default_icon_parents': 'fas fa-folder',
    'default_icon_children': 'fas fa-circle',

    'related_modal_active': True,
    'custom_css': None,
    'custom_js': None,
    'use_google_fonts_cdn': False,
    'show_ui_builder': False,

    'changeform_format': 'horizontal_tabs',
    'changeform_format_overrides': {
        'users.User': 'collapsible',
        'users.DoctorProfile': 'vertical_tabs',
        'users.ClinicProfile': 'vertical_tabs',
    },
}

JAZZMIN_UI_TWEAKS = {
    'navbar_small_text': False,
    'footer_small_text': False,
    'body_small_text': False,
    'brand_small_text': False,
    'brand_colour': 'navbar-success',
    'accent': 'accent-teal',
    'navbar': 'navbar-dark',
    'no_navbar_border': False,
    'navbar_fixed': True,
    'layout_boxed': False,
    'footer_fixed': False,
    'sidebar_fixed': True,
    'sidebar': 'sidebar-dark-teal',
    'sidebar_nav_small_text': False,
    'sidebar_disable_expand': False,
    'sidebar_nav_child_indent': True,
    'sidebar_nav_compact_style': False,
    'sidebar_nav_legacy_style': False,
    'sidebar_nav_flat_style': False,
    'theme': 'default',
    'dark_mode_theme': None,
    'button_classes': {
        'primary': 'btn-primary',
        'secondary': 'btn-secondary',
        'info': 'btn-info',
        'warning': 'btn-warning',
        'danger': 'btn-danger',
        'success': 'btn-success',
    },
}
