## Plan: Extraction Service Monorepo Setup

TL;DR - Add a dedicated extraction-service project alongside the existing frontend and backend in the Nx monorepo. The main Django app will keep user auth, Gmail fetch orchestration, and API routing, while the extraction service will receive raw email text, normalize it, call the LLM, validate a strict JSON response, and return structured trip data that the main app can save.

**Steps**
1. Define the service boundary and responsibilities.
   - Keep the Django backend in charge of user auth, Gmail integration, API endpoints, and persistence.
   - Keep the extraction service focused on raw email normalization, LLM calls, validation, and structured parsing.
   - Do not let the extraction service own app auth or user data model logic.

2. Add the new extraction-service project inside the monorepo.
   - Create a dedicated project folder for the extraction service next to the frontend and backend.
   - Initialize a Python app using FastAPI for a lightweight API and easy local testing.
   - Add environment configuration, startup scripts, and a health endpoint.

3. Define the extraction API contract.
   - Create a POST /extract endpoint with raw email text and optional metadata.
   - Define a strict structured response for trip and booking fields.
   - Create a POST /health endpoint and a simple test route for sample email testing.
   - Keep the contract stable so the service can be tested independently from the app.

4. Implement the email normalization pipeline.
   - Parse raw Gmail content into clean text.
   - Strip HTML, remove duplicate boilerplate, and normalize whitespace.
   - Extract the useful sections: subject, sender, body, timestamps, and message metadata.
   - Build a preprocessing layer that can be tested with sample emails before contacting the LLM.

5. Wire in the LLM extraction step.
   - Use a strong external LLM (OpenAI or Azure OpenAI) for v1.
   - Pass normalized email text plus a strict JSON schema to the model.
   - Specify a low-temperature, deterministic extraction prompt.
   - Require the model to return only valid JSON for recognized trip/booking fields.

6. Add validation and quality checks.
   - Validate extraction output using Pydantic or equivalent schema validation.
   - Reject incomplete or unsupported fields before they reach the main backend.
   - Add confidence scoring and parse-failure handling.
   - Keep the validation layer strict enough to prevent bad trip records from entering the database.

7. Connect the extraction service to the backend.
   - The backend fetches Gmail messages and sends the raw text to the extraction service.
   - The extraction service returns structured trip/booking JSON.
   - The backend validates saved records and marks processed email IDs as complete.
   - This gives the app a clean pipeline: Gmail -> raw email -> extraction -> structured data -> DB.

8. Add local execution and testability.
   - Update the monorepo so the extraction service can be run independently from Nx.
   - Add Docker support for local startup and isolated debugging.
   - Add sample email fixtures and endpoint tests.
   - Ensure the service can be tested without the full frontend and backend stacks.

9. Prepare the service for future expansion.
   - Keep extraction prompts and schema versioned for easier iteration.
   - Keep the result model reusable for future assistant or RAG features.
   - Leave room for a later chatbot service to answer natural language questions against structured trip data.

**Relevant files**
- [package.json](package.json) — root workspace scripts and Nx-driven startup commands
- [nx.json](nx.json) — monorepo project registration
- [frontend](frontend) — existing UI app
- [backend](backend) — existing Django API app
- The new extraction-service project — to be added alongside the other two apps in the monorepo
- [README.md](README.md) — project overview and development setup

**Verification**
1. Start the extraction service alone and confirm the health endpoint returns success.
2. Send a known sample travel email to the /extract endpoint and verify it returns valid structured trip JSON.
3. Confirm the backend can call the extraction service and save the parsed result without manual intervention.
4. Run extraction-specific tests for parser behavior, schema validation, and malformed input handling.

**Decisions**
- Use a separate project inside the monorepo instead of a separate repo for now because the team wants a shared Nx workflow and easier local orchestration.
- Keep the extraction service modular and testable, but do not let it own business logic outside the parsing pipeline.
- Keep the service synchronous at first, with optional async queue support later if job volume grows.

**Further Considerations**
1. Decide whether the extraction service should be invoked synchronously first or queued behind a lightweight worker in the next iteration.
2. Add a strict output schema early so future RAG or chatbot improvements use the same canonical trip data model.
3. Create seeded sample emails in the service repository so extraction prompt and parser quality can be tested independently of the main app.
