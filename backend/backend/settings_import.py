# Temporary settings override for OFFLINE data import only.
# The project's backend.settings.py sets DATABASES['default']['OPTIONS']['init_command']
# which is a MySQL/PostgreSQL-only option and is NOT accepted by Django 4.2's sqlite3
# backend (raises TypeError: Connection() got an unexpected keyword argument 'init_command').
# This override removes the invalid OPTIONS so the offline import command can connect.
# It does NOT modify the project's real settings.py.
from backend.settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATABASES['default']['NAME'],
        'OPTIONS': {},  # WAL/busy_timeout already applied to the db file on prior runs; not needed here
    }
}
