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
- `FRONTEND_URL` (used to build password-reset links; defaults to `http://localhost:5173`)
- `DJANGO_EMAIL_BACKEND` (defaults to Django's console backend for local development)
- `DEFAULT_FROM_EMAIL`
- For SMTP delivery, set `DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and configure `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and either `EMAIL_USE_TLS=1` or `EMAIL_USE_SSL=1`.
