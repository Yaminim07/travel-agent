# Backend: Django

This folder contains a placeholder Django project for the Travel Agent backend.

Run locally (using Poetry):

```bash
poetry install
poetry run python manage.py migrate
poetry run python manage.py runserver
```

Environment variables:
- `DJANGO_SECRET_KEY`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`
