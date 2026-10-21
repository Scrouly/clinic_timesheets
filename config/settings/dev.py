"""Настройки для разработки на своём компьютере."""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-insecure-key-do-not-use-in-production")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
