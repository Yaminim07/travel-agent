import base64
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
        with ThreadPoolExecutor(max_workers=min(8, max(len(message_ids), 1)) or 1) as executor:
            for message in executor.map(
                lambda message_id: self._fetch_message_detail(google_account.access_token, message_id),
                message_ids,
            ):
                if message:
                    fetched_messages.append(message)

        elapsed_seconds = round(time.time() - started_at, 3)
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
