## Plan: Trip Discovery v1

TL;DR - Build a Django + React app that connects to Gmail, extracts travel bookings (hotels, flights, trains, buses) using a pluggable LLM extractor, stores structured trips in PostgreSQL, and displays upcoming trips in a React frontend. Work is split into three phases (MVP, improvements, deployment decisions).

**Steps**
1. Create repository scaffold with `backend/` (Django REST) and `frontend/` (React).
2. Implement Gmail OAuth2 connect + read-only fetch flow (dev: mockable).  
3. Create Postgres schema and Django models for User, EmailSource, Trip, Booking, ExtractionJob.  
4. Implement a pluggable LLM adapter and a Rule+Prompt extractor with hard-coded contexts (Phase 1).  
5. Implement REST API endpoints for trips and trip details.  
6. Build React pages: Connect Gmail, Dashboard (upcoming trips), Trip details, Settings.  
7. Add docker-compose for local Postgres (recommended).  
8. Phase 2: add Redis for caching/queue, improve LLM (embeddings/NER), add tests and CI.  
9. Phase 3: decide deployment stack, containerize, create CI/CD and IaC artifacts.

**Relevant files**
- `backend/` — Django project, app(s), models, serializers, views, and OAuth handlers.
- `frontend/` — React app, pages, API client.
- `docker-compose.yml` — Postgres (+ Redis optional) for local dev.
- `README.md` — setup, env vars, run steps, Gmail dev console notes.

**Phase 1**

Goal: MVP that can connect to Gmail, fetch messages, extract bookings via a basic LLM+rules adapter, persist results to Postgres, and display upcoming trips in React.

Implementation tasks:
- Backend
  - Scaffold Django + Django REST Framework.
  - Models: `User`, `EmailSource`, `Trip`, `Booking`, `ExtractionJob`.
  - OAuth endpoints: `POST /api/auth/google/connect`, `GET /api/auth/google/callback`.
  - Fetcher: Gmail API client (read-only scope: `https://www.googleapis.com/auth/gmail.readonly`), store raw message metadata and message text.
  - Extractor: adapter interface + basic rule/prompt extractor using hard-coded contexts for flight/hotel/train/bus.
  - API endpoints: `POST /api/email/fetch`, `GET /api/trips`, `GET /api/trips/:id`.
  - Persist tokens encrypted (env-keyed encryption) and store processed message IDs.
- Frontend
  - Minimal React app with pages: Connect, Dashboard, Trip details, Settings.
  - API client to call backend, display upcoming trips and booking details.
- Local dev
  - `docker-compose` with Postgres (and optional Redis commented out).
  - Env variables documented: DB, Google OAuth client ID/secret, DJANGO_SECRET_KEY.

Deliverables:
- Working local flow: connect Gmail -> fetch sample emails -> extractor populates Trips/Bookings -> React shows trips.
- `README.md` with setup and demo steps.

Success criteria:
- OAuth connect + fetch works in dev (mock or real Gmail).  
- Frontend shows parsed upcoming trips.  
- Basic extraction accuracy on sample emails (manual verification target: ~70%).

**Phase 2**

Goal: Improve extraction intelligence, reliability, and add tests/observability.

Tasks:
- LLM pipeline improvements
  - Add embeddings + vector search for semantic matching of templates where needed.
  - Integrate NER or regex validators for dates, locations, times.
  - Make LLM adapter pluggable so swapping to external provider or self-hosted model is straightforward.
- Performance & reliability
  - Add Redis: cache API responses and use as job queue (Celery or RQ) for async parsing.
  - Implement incremental sync and processed-message tracking to avoid re-parsing.
  - Add Gmail API rate-limit/backoff handling.
- Testing & CI
  - Unit tests for parsing, models, and React components.  
  - Integration tests for end-to-end parsing pipeline (mock Gmail).  
  - GitHub Actions to run tests, lint, and build.
- Observability
  - Structured logs and basic metrics for parsing success/failure and latency.

Deliverables & success criteria:
- Parsing accuracy improved (target ~85% on validation set).  
- Async job queue with Redis processes parsing jobs locally.  
- Tests run in CI and meet coverage goals for core modules.

**Phase 3**

Goal: Decide and implement deployment tooling and runbook for production.

Decisions to evaluate:
- Hosting: managed platform (Render/Heroku) vs cloud VM/k8s (AWS/GCP/Azure) vs serverless.
- LLM hosting: external API (OpenAI/Anthropic) vs self-hosted inference (cost/privacy tradeoffs).
- Managed services: Postgres (RDS/Cloud SQL), Redis (Elasticache/Redis Cloud), secrets manager.

Recommended minimal production stack (options):
- Containerize backend/frontend and deploy via managed container service (Render/Cloud Run) + managed Postgres + managed Redis; CI/CD with GitHub Actions.
- For heavy LLM usage, evaluate hosted LLM API cost vs. self-hosting inference on GPUs.

Deliverables:
- Deployment checklist and recommended IaC manifests (Terraform / cloud provider templates) for chosen infra.
- Runbook for OAuth credential rotation, token expiry handling, and data deletion requests.

**Data model (core fields)**
- User: id, email, name, oauth_tokens_encrypted, created_at.
- EmailSource: id, user_id, provider, last_synced_at.
- Trip: id, user_id, title, start_date, end_date, created_at, source_message_ids.
- Booking: id, trip_id, type (flight/hotel/train/bus), provider_name, start_time, end_time, origin, destination, confirmation_number, raw_text, confidence_score.
- ExtractionJob: id, user_id, message_id, status, error, processed_at.

**Security & Privacy**
- Request Gmail scope: `https://www.googleapis.com/auth/gmail.readonly` only.
- Encrypt OAuth tokens and sensitive PII in DB; document retention policy and deletion endpoints.
- Provide user controls: disconnect Gmail and delete stored messages/trips.

**Verification**
1. Manual demo: connect Gmail, fetch emails, verify parsed trips in UI.  
2. Unit/integration tests for parsers and API endpoints.  
3. Load test/parsing throughput assessment in Phase 2 for scaling guidance.

**Decisions & assumptions**
- Single-user MVP (multi-user support added but not hardened for large-scale multi-tenant security).  
- Initial LLM usage is local/adapter-based with deterministic prompts + rules to minimize cost.  
- Postgres is the primary persistent store; Redis is optional in Phase 1 and required in Phase 2 for queueing/caching.

**Further Considerations**
1. Privacy option: offer on-device parsing or processing only via user-approved external LLM provider.  
2. Vendor variability: maintain a corpus of sample emails across top airlines/hotels to improve extraction templates.  


