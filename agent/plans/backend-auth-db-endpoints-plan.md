# Travel Agent v1 Backend Auth, DB, and API Plan

## 1. Auth strategy

### Goal
Use Google OAuth2 login and JWT-based auth for API requests.

### Flow
1. Frontend calls `POST /api/auth/google/connect`.
2. Backend returns the Google OAuth URL.
3. User signs in with Google.
4. Google redirects to `GET /api/auth/google/callback`.
5. Backend exchanges the code for Google tokens.
6. Backend creates or updates the user and Google account record.
7. Backend issues JWT access token and refresh token.
8. Frontend redirects to `/dashboard`.
9. Frontend stores the JWT and sends it on all authenticated API requests via `Authorization: Bearer <token>`.
10. Logout calls `POST /api/auth/logout` to clear token state.

### Auth endpoints
- `POST /api/auth/google/connect`
- `GET /api/auth/google/callback`
- `POST /api/auth/logout`

### Security decisions
- Use Gmail read-only scope only: `https://www.googleapis.com/auth/gmail.readonly`
- Encrypt access/refresh tokens before storing in DB
- Use JWT access tokens with short expiry (example: 15–30 minutes)
- Use refresh token flow for reissuing access tokens
- Keep authentication backend-driven; frontend receives redirect after login

## 2. Database structure

### Core tables

#### `users`
Fields:
- `id` (PK)
- `email`
- `name`
- `created_at`
- `updated_at`

#### `google_accounts`
Fields:
- `id` (PK)
- `user_id` (FK -> users.id)
- `provider` (default = google)
- `google_user_id`
- `email`
- `access_token` (encrypted)
- `refresh_token` (encrypted)
- `token_expiry`
- `is_connected`
- `created_at`
- `updated_at`

#### `processed_emails`
This is the dedupe table for Gmail sync.
Fields:
- `id` (PK)
- `user_id` (FK -> users.id)
- `google_account_id` (FK -> google_accounts.id)
- `gmail_message_id` (unique)
- `thread_id`
- `status` (`processed`, `failed`, `skipped`)
- `processed_at`
- `error_message` (nullable)
- `created_at`

#### `trips`
Fields:
- `id` (PK)
- `user_id` (FK -> users.id)
- `google_account_id` (FK -> google_accounts.id)
- `title`
- `location`
- `start_date`
- `end_date`
- `status` (`upcoming`, `completed`, `cancelled`, `deleted`)
- `created_at`
- `updated_at`

#### `bookings`
Fields:
- `id` (PK)
- `trip_id` (FK -> trips.id)
- `gmail_message_id` (nullable, store source reference)
- `booking_type` (`flight`, `hotel`, `train`, `bus`)
- `provider_name`
- `confirmation_number`
- `origin`
- `destination`
- `departure_at`
- `arrival_at`
- `check_in_at`
- `check_out_at`
- `currency`
- `total_amount`
- `status`
- `confidence_score`
- `raw_extracted_data` (JSONB)
- `created_at`
- `updated_at`

#### `extraction_jobs`
Fields:
- `id` (PK)
- `user_id` (FK -> users.id)
- `gmail_message_id`
- `status` (`queued`, `running`, `success`, `failed`)
- `job_type` (`gmail_sync`, `llm_extract`, `retry`)
- `model_name`
- `prompt_version`
- `result_payload` (JSONB)
- `error_message` (nullable)
- `created_at`
- `completed_at`

### Notes
- Do not store full raw Gmail messages in v1 by default.
- Use `processed_emails` as the dedupe layer.
- Keep `raw_extracted_data` in JSONB for provider-specific details and future flexibility.

## 3. Important indexes for v1

These are the first indexes worth adding:
- `trips(user_id, start_date)`
- `bookings(trip_id)`
- `bookings(booking_type, departure_at)`
- `processed_emails(gmail_message_id)`
- `processed_emails(user_id, status)`
- `processed_emails(google_account_id, status)`

These support:
- dashboard trip list
- trip detail pages
- dedupe for Gmail sync
- filtered booking queries

## 4. Core API endpoints for v1

### Auth
- `POST /api/auth/google/connect`
- `GET /api/auth/google/callback`
- `POST /api/auth/logout`

### Gmail sync
- `POST /api/gmail/sync`
- `GET /api/gmail/sync/status/:job_id`
- `GET /api/gmail/last-sync`

### Trips
- `GET /api/trips`
- `GET /api/trips/:id`
- `PATCH /api/trips/:id`
- `DELETE /api/trips/:id` (soft delete preferred in v1)

### Bookings
- `GET /api/bookings`
- `GET /api/bookings/:id`
- `PATCH /api/bookings/:id`
- `DELETE /api/bookings/:id` (soft delete preferred in v1)

### Processed email dedupe
- `GET /api/processed-emails/check?message_id=...`
- `POST /api/processed-emails/retry`

## 5. Recommended v1 behavior

- Trips and bookings are primarily created by the extraction pipeline, not manually by users.
- Frontend reads trips and booking details from the API.
- User updates are limited to corrections or marking trip status.
- Gmail sync uses `processed_emails` to prevent repeated processing.
- Redis is deferred to Phase 2 for caching and async job processing.

## 6. Recommended implementation order

1. Set up Django, Postgres, and auth app.
2. Implement Google OAuth connect + callback.
3. Create JWT issuance and middleware.
4. Implement user and Google account models.
5. Implement processed email dedupe and Gmail sync flow.
6. Implement trip and booking extraction pipeline.
7. Expose trip and booking read APIs for dashboard and detail pages.
8. Build React frontend using these APIs.

## 7. MVP success criteria

- User logs in with Google and reaches dashboard.
- Backend stores Google account auth data securely.
- Gmail sync fetches travel-related email messages.
- Extractor creates trips and bookings from parsed emails.
- Frontend shows upcoming trips and booking detail pages.
- Duplicate Gmail messages are not reprocessed.

## 8. Final note

This design is intentionally lean for v1: it keeps the core product value while avoiding unnecessary storage and API complexity. We avoid storing full raw Gmail messages in the DB, focus on dedupe and extracted results, and reserve Redis and more advanced optimization for Phase 2.
