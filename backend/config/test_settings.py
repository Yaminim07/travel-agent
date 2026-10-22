"""Local test settings: run the suite on SQLite without a Postgres server.

    python3 manage.py test core --settings=config.test_settings
"""
from .settings import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
