import base64
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Booking, ExtractionJob, GoogleAccount, ProcessedEmail, Trip, User
from .serializers import (
    BookingSerializer,
    ExtractionJobSerializer,
    GoogleAccountSerializer,
    ProcessedEmailSerializer,
    TripSerializer,
    UserSerializer,
)

logger = logging.getLogger("travel_agent.backend")
EXTRACTION_BATCH_SIZE = 10


def _safe_response_body(response):
    text = getattr(response, "text", None)
    if text is not None:
        return text

    content = getattr(response, "content", None)
    if content is not None:
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
        return str(content)

    try:
        return str(response.json())
    except Exception:
        return str(response)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class GoogleAccountViewSet(viewsets.ModelViewSet):
    queryset = GoogleAccount.objects.all()
    serializer_class = GoogleAccountSerializer

    @action(detail=False, methods=["post"], url_path="connect")
    def connect(self, request, *args, **kwargs):
        return Response(
            {"message": "Google OAuth placeholder: connect flow will be implemented later."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="callback")
    def callback(self, request, *args, **kwargs):
        return Response(
            {"message": "Google OAuth callback placeholder: will be implemented later."},
            status=status.HTTP_200_OK,
        )


class ProcessedEmailViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProcessedEmail.objects.all()
    serializer_class = ProcessedEmailSerializer

    @action(detail=False, methods=["get"], url_path="check")
    def check(self, request, *args, **kwargs):
        return Response(
            {"message": "Processed email dedupe check placeholder: Gmail sync not connected yet."},
            status=status.HTTP_200_OK,
        )


class GmailMessageViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _decode_message_body(message_data):
        payload = message_data.get("payload", {})
        parts = payload.get("parts") or []
        body_text = ""

        def walk(part):
            nonlocal body_text
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data")
                if data:
                    body_text += base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
            for child in part.get("parts", []) or []:
                walk(child)

        for part in parts:
            walk(part)

        if not body_text and payload.get("body", {}).get("data"):
            data = payload["body"]["data"]
            body_text = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")

        return body_text.strip()

    @staticmethod
    def _extract_headers(message_data):
        headers = {}
        for item in message_data.get("payload", {}).get("headers", []):
            name = item.get("name", "").lower()
            if name:
                headers[name] = item.get("value", "")
        return headers

    @staticmethod
    def _quarter_queries(year):
        return [
            {"quarter": "Q1", "query": f"after:{year}/01/01 before:{year}/04/01"},
            {"quarter": "Q2", "query": f"after:{year}/04/01 before:{year}/07/01"},
            {"quarter": "Q3", "query": f"after:{year}/07/01 before:{year}/10/01"},
            {"quarter": "Q4", "query": f"after:{year}/10/01 before:{year + 1}/01/01"},
        ]

    def _fetch_message_ids_for_query(self, access_token, query):
        try:
            response = requests.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": query, "includeSpamTrash": False, "maxResults": 500},
                timeout=30,
            )
        except requests.RequestException:
            return []

        if response.status_code != 200:
            return []

        payload = response.json()
        return [item.get("id") for item in payload.get("messages", []) if item.get("id")]

    def _fetch_message_detail(self, access_token, message_id):
        try:
            response = requests.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"format": "full"},
                timeout=30,
            )
        except requests.RequestException:
            return None

        if response.status_code != 200:
            return None

        detail = response.json()
        headers = self._extract_headers(detail)
        return {
            "id": detail.get("id"),
            "threadId": detail.get("threadId"),
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            "snippet": detail.get("snippet", ""),
            "body": self._decode_message_body(detail),
        }

    @staticmethod
    def _trigger_extraction_pipeline(messages, user_email):
        if not messages:
            logger.info("[GMAIL_PIPELINE] No messages to process for extraction.")
            return {"extraction": None, "indexing": None}

        base_url = settings.EXTRACTION_SERVICE_URL.rstrip("/")
        request_timeout = getattr(settings, "EXTRACTION_SERVICE_TIMEOUT", 120)
        logger.info(
            "[GMAIL_PIPELINE] Starting extraction pipeline for %s message(s) for user %s with batch_size=%s timeout=%ss",
            len(messages),
            user_email,
            EXTRACTION_BATCH_SIZE,
            request_timeout,
        )

        batches = [messages[i:i + EXTRACTION_BATCH_SIZE] for i in range(0, len(messages), EXTRACTION_BATCH_SIZE)]
        aggregated_trips = []
        aggregated_bookings = []
        aggregated_notes = []
        indexing_results = []

        for batch_index, batch in enumerate(batches, start=1):
            logger.info("[GMAIL_PIPELINE] Sending batch %s/%s with %s message(s)", batch_index, len(batches), len(batch))
            extraction_payload = {
                "source": "gmail",
                "user_email": user_email,
                "year": datetime.now().year,
                "messages": batch,
            }

            try:
                logger.info("[GMAIL_PIPELINE] Calling extraction service: %s/extract", base_url)
                extraction_response = requests.post(
                    f"{base_url}/extract",
                    json=extraction_payload,
                    timeout=request_timeout,
                )
                logger.info("[GMAIL_PIPELINE] Extraction response status=%s", extraction_response.status_code)
                extraction_body = _safe_response_body(extraction_response)
                logger.info("[GMAIL_PIPELINE] Extraction response body=%s", extraction_body[:2000])

                if extraction_response.status_code != 200:
                    logger.error("[GMAIL_PIPELINE] Extraction service returned non-200 for batch %s: %s", batch_index, extraction_body)
                    return {"extraction": {"error": extraction_body}, "indexing": None}

                extraction_result = extraction_response.json()
                aggregated_trips.extend(extraction_result.get("trips", []))
                aggregated_bookings.extend(extraction_result.get("bookings", []))
                if extraction_result.get("notes"):
                    aggregated_notes.append(str(extraction_result.get("notes")))

                logger.info(
                    "[GMAIL_PIPELINE] Extraction batch %s returned %s trip(s) and %s booking(s)",
                    batch_index,
                    len(extraction_result.get("trips", [])),
                    len(extraction_result.get("bookings", [])),
                )

                try:
                    logger.info("[GMAIL_PIPELINE] Calling Pinecone index endpoint: %s/index-relevant-messages", base_url)
                    indexing_response = requests.post(
                        f"{base_url}/index-relevant-messages",
                        json={"messages": batch, "result": extraction_result},
                        timeout=request_timeout,
                    )
                    logger.info("[GMAIL_PIPELINE] Index response status=%s", indexing_response.status_code)
                    index_body = _safe_response_body(indexing_response)
                    logger.info("[GMAIL_PIPELINE] Index response body=%s", index_body[:2000])
                    indexing_result = indexing_response.json() if indexing_response.status_code == 200 else None
                    indexing_results.append(indexing_result)
                except requests.RequestException as exc:
                    logger.exception("[GMAIL_PIPELINE] Pinecone indexing request failed for batch %s: %s", batch_index, exc)
                    indexing_results.append({"error": str(exc)})
            except requests.RequestException as exc:
                logger.exception("[GMAIL_PIPELINE] Extraction service unavailable for batch %s: %s", batch_index, exc)
                return {"extraction": {"error": "Extraction service unavailable."}, "indexing": None}

        return {
            "extraction": {
                "trips": aggregated_trips,
                "bookings": aggregated_bookings,
                "notes": "\n".join(aggregated_notes),
            },
            "indexing": indexing_results,
        }

    @action(detail=False, methods=["get"], url_path="messages")
    def messages(self, request, *args, **kwargs):
        google_account = GoogleAccount.objects.filter(user=request.user, provider="google", is_connected=True).first()
        if not google_account or not google_account.access_token:
            return Response(
                {"messages": [], "detail": "Google account not connected or access token missing."},
                status=status.HTTP_200_OK,
            )

        current_year = datetime.now().year
        quarter_queries = self._quarter_queries(current_year)
        started_at = time.time()

        message_ids = []
        seen_ids = set()
        with ThreadPoolExecutor(max_workers=min(8, len(quarter_queries) * 2)) as executor:
            for quarter_result in executor.map(
                lambda quarter: self._fetch_message_ids_for_query(google_account.access_token, quarter["query"]),
                quarter_queries,
            ):
                for message_id in quarter_result:
                    if message_id and message_id not in seen_ids:
                        seen_ids.add(message_id)
                        message_ids.append(message_id)

        fetched_messages = []
        logger.info("[GMAIL_SYNC] Started Gmail fetch for user=%s; message_ids=%s", request.user.email, len(message_ids))
        with ThreadPoolExecutor(max_workers=min(8, max(len(message_ids), 1)) or 1) as executor:
            for message in executor.map(
                lambda message_id: self._fetch_message_detail(google_account.access_token, message_id),
                message_ids,
            ):
                if message:
                    fetched_messages.append(message)

        logger.info("[GMAIL_SYNC] Gmail fetch completed. Fetched %s message(s).", len(fetched_messages))
        extraction_pipeline_result = self._trigger_extraction_pipeline(fetched_messages, request.user.email)

        elapsed_seconds = round(time.time() - started_at, 3)
        logger.info("[GMAIL_SYNC] Gmail sync finished in %ss", elapsed_seconds)
        return Response(
            {
                "year": current_year,
                "query": f"after:{current_year}/01/01 before:{current_year + 1}/01/01",
                "count": len(fetched_messages),
                "fetch_duration_seconds": elapsed_seconds,
                "messages": fetched_messages,
                "extraction_input": {
                    "source": "gmail",
                    "year": current_year,
                    "messages": fetched_messages,
                },
                "extraction_pipeline": extraction_pipeline_result,
            },
            status=status.HTTP_200_OK,
        )


class TripViewSet(viewsets.ModelViewSet):
    queryset = Trip.objects.all().order_by("-start_date")
    serializer_class = TripSerializer


class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all().order_by("-departure_at")
    serializer_class = BookingSerializer


class ExtractionJobViewSet(viewsets.ModelViewSet):
    queryset = ExtractionJob.objects.all().order_by("-created_at")
    serializer_class = ExtractionJobSerializer

    @action(detail=False, methods=["post"], url_path="trigger")
    def trigger(self, request, *args, **kwargs):
        return Response(
            {"message": "Extraction job placeholder: external extraction service not connected yet."},
            status=status.HTTP_200_OK,
        )


class AssistantSearchViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"], url_path="search")
    def search(self, request, *args, **kwargs):
        query = (request.data or {}).get("query", "").strip()
        if not query:
            return Response({"detail": "A search query is required."}, status=status.HTTP_400_BAD_REQUEST)

        extraction_service_url = f"{settings.EXTRACTION_SERVICE_URL.rstrip('/')}/search"
        request_timeout = getattr(settings, "EXTRACTION_SERVICE_TIMEOUT", 120)
        try:
            response = requests.post(
                extraction_service_url,
                json={"query": query, "user_email": request.user.email},
                timeout=request_timeout,
            )
        except requests.RequestException as exc:
            return Response(
                {"detail": f"Assistant search failed: {str(exc)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.status_code != 200:
            return Response(
                {"detail": "Extraction service rejected the search request."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payload = response.json()
        return Response(
            {
                "answer": payload.get("answer", "I could not find a clear answer for that search."),
                "matches": payload.get("matches", []),
                "query": query,
            },
            status=status.HTTP_200_OK,
        )
