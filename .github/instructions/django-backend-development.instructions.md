# Django & Backend Development Rules

## 1. Architecture & Project Structure
- **Framework Standards:** Use Django and Django REST Framework as the default backend stack for API services.
- **App Organization:** Keep business logic inside dedicated Django apps. Avoid putting large service logic into a single monolithic module.
- **Layering:** Keep `models.py`, `serializers.py`, `views.py`, `services.py`, and `urls.py` responsibilities separated and clear.
- **Configuration:** Use environment variables for secrets and configuration instead of hardcoded values.

## 2. API Design & Data Handling
- **RESTful Practices:** Follow REST conventions for endpoints, status codes, and JSON payload shapes.
- **Validation:** Validate request data at serializer and model layer boundaries. Prefer serializers for request/response transformation.
- **Transactions:** Use database transactions for multi-step writes that must be atomic.
- **Error Handling:** Catch service and validation failures and return structured, clear API errors with relevant HTTP status codes.

## 3. Database & Persistence
- **Schema Evolution:** Use Django migrations for all schema changes and avoid ad-hoc SQL in app code.
- **Query Efficiency:** Use select-related and prefetch-related patterns when needed to prevent N+1 query issues.
- **Indexes:** Add database indexes for commonly filtered or joined fields, especially on timestamps, foreign keys, and search-heavy fields.

## 4. Security & Reliability
- **Secrets Management:** Store OAuth credentials, API keys, and database credentials in environment variables or a secure secrets manager.
- **Least Privilege:** Use minimal required scopes and permissions for Gmail and other external integrations.
- **Authentication & Authorization:** Implement auth checks at the view or permission layer and never assume requests are trusted.
- **Logging & Monitoring:** Log key failures and background jobs with enough context for debugging without exposing secrets or sensitive user data.

## 5. Python & Code Quality
- **Type Safety:** Use type hints for service functions and complex modules where practical.
- **Linting & Formatting:** Keep code PEP8-compliant and formatted consistently with `black` or `ruff`.
- **Service Layer:** Move complex business logic into explicit service functions so views stay thin and easier to test.
- **Testing:** Add unit tests for domain logic, serializer validation, and API behavior. Prefer realistic integration tests for core flows.
