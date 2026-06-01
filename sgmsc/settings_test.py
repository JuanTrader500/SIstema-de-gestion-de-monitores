from sgmsc.settings import *  # noqa: F401, F403

SECRET_KEY = "django-insecure-clave-solo-para-tests-no-usar-en-produccion"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"