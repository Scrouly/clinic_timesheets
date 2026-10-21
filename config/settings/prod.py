"""Рабочие настройки. Секреты и адреса берутся только из окружения."""
from .base import *  # noqa: F401,F403
from .base import LOG_DIR, LOGGING, env

# Без значения по умолчанию: без ключа рабочее приложение не запустится.
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Защищённые cookie и редирект включаются, когда сайт работает по HTTPS.
_https = env.bool("DJANGO_HTTPS", default=False)
SESSION_COOKIE_SECURE = _https
CSRF_COOKIE_SECURE = _https
SECURE_SSL_REDIRECT = _https
SECURE_HSTS_SECONDS = 31536000 if _https else 0
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if _https else None
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Файл журнала с ротацией (по 5 МБ, 5 копий).
LOG_DIR.mkdir(exist_ok=True)
LOGGING["handlers"]["file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": LOG_DIR / "app.log",
    "maxBytes": 5 * 1024 * 1024,
    "backupCount": 5,
    "encoding": "utf-8",
    "formatter": "plain",
}
LOGGING["root"]["handlers"] = ["console", "file"]
