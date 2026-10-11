## Plan: Google OAuth + Gmail Integration

### Objective
Add the Google identity and inbox access required for user authentication and travel-email extraction. This is the foundation for the app’s login flow and Gmail-based trip discovery.

### Core Google services needed

#### 1) Google OAuth 2.0 / OpenID Connect
Purpose:
- allow users to sign in with Google
- connect a Google account to their app account
- issue the app’s own JWT after successful Google authentication

Required OAuth flow:
- user clicks “Continue with Google” in the frontend
- frontend sends the auth request or redirects to backend OAuth endpoint
- backend exchanges authorization code for tokens
- backend validates identity and stores user + Google account metadata
- backend creates a local JWT for app session management

Recommended scopes:
- `openid`
- `https://www.googleapis.com/auth/userinfo.email`
- `https://www.googleapis.com/auth/userinfo.profile`

Why needed:
- authentication for app users
- linking user accounts to Gmail data
- profile data such as email, name, and avatar

Backend responsibilities:
- generate OAuth authorization URL
- handle callback and token exchange
- validate ID token or userinfo response
- create/update `User` and `GoogleAccount` records
- issue JWT access token and refresh token strategy if needed
- implement logout to revoke local session and clear JWT

#### 2) Gmail API
Purpose:
- read travel-related emails from the user’s connected Gmail inbox
- fetch message metadata and message bodies for parsing
- identify new content and avoid reprocessing duplicates

Required scope:
- `https://www.googleapis.com/auth/gmail.readonly`

Why needed:
- trip discovery depends on Gmail message ingestion
- app reads booking confirmations, itineraries, and travel updates
- extraction engine uses Gmail contents to produce structured trips and bookings

Backend responsibilities:
- fetch messages from Gmail using the user’s access token
- store only minimal useful metadata and dedupe record
- process message IDs to avoid duplicate parsing
- detect and extract relevant mail types: flights, hotels, trains, buses, car rentals, itineraries
- keep raw data minimal and avoid storing all email content permanently in v1

#### 3) Google People API / UserInfo endpoint
Purpose:
- get user profile details after OAuth login
- enrich the local user profile with Google account information

Why needed:
- name/email/avatar available for user onboarding and account display
- ensures local profile data matches the authenticated Google identity

Recommended usage:
- use `userinfo` endpoint for quick profile retrieval, or People API for richer fields if needed

### Recommended MVP architecture

- Frontend
  - button to initiate Google sign-in or connect account
  - handle success redirection to dashboard or auth callback route
  - store JWT in secure client storage or memory
  - include JWT in `Authorization` header for backend API requests

- Backend
  - create a dedicated auth flow for Google OAuth
  - implement `POST /api/auth/google/connect`
  - implement `GET /api/auth/google/callback`
  - implement `POST /api/auth/logout`
  - issue own JWT after successful Google login
  - create `GoogleAccount` records with access token/refresh token metadata
  - provide Gmail sync endpoint such as `POST /api/gmail/sync`

### Required app-level endpoints

- `POST /api/auth/google/connect`
  - starts the OAuth authorization flow
- `GET /api/auth/google/callback`
  - handles Google redirect, exchanges code, creates/updates user, returns app redirect
- `POST /api/auth/logout`
  - invalidates local session/JWT and clears connection state
- `POST /api/gmail/sync`
  - fetches unread or recent Gmail messages for the connected account
- `GET /api/trips`
  - lists user trips
- `GET /api/trips/:id`
  - returns trip details and bookings

### Data model relevant to Google integration

- `User`
  - id
  - email
  - name
  - google_account_id or linked Google account
  - created_at

- `GoogleAccount`
  - id
  - user_id
  - google_user_id
  - email
  - access_token
  - refresh_token
  - token_expires_at
  - connected_at
  - status

- `ProcessedEmail`
  - id
  - user_id
  - gmail_message_id
  - processed_at
  - status
  - source_type

This model ensures we do not repeatedly parse the same Gmail item and keeps the system efficient.

### Security and privacy requirements

- request only the minimum necessary scopes
- encrypt stored OAuth tokens at rest
- avoid storing full raw email bodies unless explicitly needed for debugging
- allow logout and disconnect actions for the user
- manage token expiry and refresh lifecycle safely
- document Gmail data retention and user deletion behavior

### v1 focus

For the initial version, only these integrations are required:
- Google OAuth 2.0
- Gmail API
- Google user info/profile lookup

Everything else, such as Google Calendar or Maps, can wait until a later phase.

### Acceptance checklist

- user can sign in with Google
- user can connect Google account to the app
- backend stores the Google account and user identity securely
- backend issues a JWT for app authentication
- user can logout and clear session state
- app can fetch Gmail messages using Google access token
- processed email dedupe prevents reprocessing
- extracted trips are created from Gmail booking confirmations

### Notes for implementation

- Keep OAuth and Gmail logic behind a dedicated backend auth/service layer.
- Use provider-friendly naming: `GoogleAccount`, `processed_email`, `gmail_sync_job`.
- Prefer read-only Gmail access for v1.
- Keep the flow simple: OAuth login -> JWT app auth -> Gmail sync -> trip extraction.

### Decision summary
The minimum viable Google integration is:
- Google OAuth 2.0 for login/authentication
- Gmail API for inbox reading and trip extraction
- Google user profile data for account enrichment

This is the exact set needed to support our intended product flow without overbuilding the first release.
