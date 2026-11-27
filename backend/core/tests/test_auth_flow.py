from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import GoogleAccount


class AuthFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="demo",
            email="demo@example.com",
            password="StrongPass123!",
        )

    def test_manual_login_returns_auth_tokens(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": "demo@example.com", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], self.user.email)

    def test_signup_creates_user_and_returns_auth_tokens(self):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "first_name": "Taylor",
                "last_name": "Traveller",
                "email": "taylor@example.com",
                "password": "TravellerSafe123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user"]["email"], "taylor@example.com")
        self.assertIn("access", response.data)
        self.assertTrue(get_user_model().objects.get(email="taylor@example.com").check_password("TravellerSafe123!"))

    def test_signup_rejects_duplicate_email_and_weak_password(self):
        duplicate_response = self.client.post(
            "/api/auth/signup/",
            {
                "first_name": "Demo",
                "last_name": "User",
                "email": "DEMO@example.com",
                "password": "AnotherSafe987!",
            },
            format="json",
        )
        weak_password_response = self.client.post(
            "/api/auth/signup/",
            {
                "first_name": "Taylor",
                "last_name": "Traveller",
                "email": "taylor@example.com",
                "password": "12345678",
            },
            format="json",
        )

        self.assertEqual(duplicate_response.status_code, 400)
        self.assertEqual(weak_password_response.status_code, 400)

    def test_manual_login_rejects_invalid_password(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": "demo@example.com", "password": "incorrect"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_password_reset_request_is_generic_and_reset_token_is_single_use(self):
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            FRONTEND_URL="http://localhost:5173",
        ):
            existing_response = self.client.post(
                "/api/auth/password-reset/",
                {"email": self.user.email},
                format="json",
            )
            unknown_response = self.client.post(
                "/api/auth/password-reset/",
                {"email": "unknown@example.com"},
                format="json",
            )

        self.assertEqual(existing_response.status_code, 200)
        self.assertEqual(unknown_response.status_code, 200)
        self.assertEqual(existing_response.data, unknown_response.data)
        self.assertEqual(len(mail.outbox), 1)

        reset_url = next(
            part for part in mail.outbox[0].body.split() if part.startswith("http://")
        )
        reset_params = parse_qs(urlsplit(reset_url).query)
        reset_response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": reset_params["uid"][0],
                "token": reset_params["token"][0],
                "password": "AnotherStrongPass987!",
                "password_confirm": "AnotherStrongPass987!",
            },
            format="json",
        )
        replay_response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": reset_params["uid"][0],
                "token": reset_params["token"][0],
                "password": "AnotherStrongPass987!",
                "password_confirm": "AnotherStrongPass987!",
            },
            format="json",
        )
        login_response = self.client.post(
            "/api/auth/login/",
            {"email": self.user.email, "password": "AnotherStrongPass987!"},
            format="json",
        )

        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(replay_response.status_code, 400)
        self.assertEqual(login_response.status_code, 200)

    def test_password_reset_rejects_mismatched_confirmation(self):
        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": "invalid",
                "token": "invalid",
                "password": "AnotherStrongPass987!",
                "password_confirm": "DifferentStrongPass987!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_me_requires_auth(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)

    def test_logout_ignores_invalid_or_expired_token(self):
        response = self.client.post(
            "/api/auth/logout/",
            {"refresh": "bad-token"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    @patch("core.auth_views.requests.post")
    @patch("core.auth_views.requests.get")
    def test_google_connect_returns_auth_url(self, mock_get, mock_post):
        with self.settings(
            GOOGLE_CLIENT_ID="test-client-id",
            GOOGLE_CLIENT_SECRET="test-client-secret",
            GOOGLE_REDIRECT_URI="http://localhost:8000/api/auth/google/callback/",
            FRONTEND_URL="http://localhost:5173",
        ):
            response = self.client.get("/api/auth/google/connect/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("auth_url", response.data)
        self.assertIn("accounts.google.com", response.data["auth_url"])

    @patch("core.auth_views.requests.post")
    @patch("core.auth_views.requests.get")
    def test_google_callback_creates_user_and_redirects(self, mock_get, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "google-access-token",
            "refresh_token": "google-refresh-token",
            "expires_in": 3600,
            "id_token": "fake-token",
        }
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "sub": "google-123",
            "email": "google-user@example.com",
            "name": "Google User",
        }

        with self.settings(
            GOOGLE_CLIENT_ID="test-client-id",
            GOOGLE_CLIENT_SECRET="test-client-secret",
            GOOGLE_REDIRECT_URI="http://localhost:8000/api/auth/google/callback/",
            FRONTEND_URL="http://localhost:5173",
        ):
            response = self.client.get(
                "/api/auth/google/callback/",
                {"code": "abc123"},
                follow=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(email="google-user@example.com").exists())

    @patch("core.views.requests.post")
    @patch("core.views.requests.get")
    def test_gmail_messages_endpoint_returns_messages_for_authenticated_user(self, mock_get, mock_post):
        GoogleAccount.objects.create(
            user=self.user,
            provider="google",
            google_user_id="google-123",
            email=self.user.email,
            access_token="test-google-access-token",
            refresh_token="test-refresh-token",
            is_connected=True,
        )

        user_email = self.user.email

        def fake_get(url, headers=None, params=None, timeout=None):
            if "/messages" in url and not url.endswith("/msg-1") and not url.endswith("/msg-2"):
                return type(
                    "Response",
                    (),
                    {"status_code": 200, "json": lambda self: {"messages": [{"id": "msg-1"}, {"id": "msg-2"}] }},
                )()

            if url.endswith("/msg-1"):
                return type(
                    "Response",
                    (),
                    {
                        "status_code": 200,
                        "json": lambda self: {
                            "id": "msg-1",
                            "threadId": "thread-1",
                            "snippet": "Flight to Tokyo",
                            "payload": {
                                "headers": [
                                    {"name": "Subject", "value": "Flight to Tokyo"},
                                    {"name": "From", "value": "airline@example.com"},
                                    {"name": "To", "value": user_email},
                                    {"name": "Date", "value": "Wed, 1 Jan 2026 10:00:00 +0000"},
                                ],
                                "parts": [{
                                    "mimeType": "text/plain",
                                    "body": {"data": "RmxpZ2h0IHRvIFRvLWtpbw=="},
                                    "parts": [],
                                }],
                            },
                        },
                    },
                )()

            if url.endswith("/msg-2"):
                return type(
                    "Response",
                    (),
                    {
                        "status_code": 200,
                        "json": lambda self: {
                            "id": "msg-2",
                            "threadId": "thread-2",
                            "snippet": "Hotel confirmation",
                            "payload": {
                                "headers": [
                                    {"name": "Subject", "value": "Hotel confirmation"},
                                    {"name": "From", "value": "hotel@example.com"},
                                    {"name": "To", "value": user_email},
                                    {"name": "Date", "value": "Thu, 2 Jan 2026 12:00:00 +0000"},
                                ],
                                "parts": [{
                                    "mimeType": "text/plain",
                                    "body": {"data": "SG90ZWwgY29uZmlybWF0aW9u"},
                                    "parts": [],
                                }],
                            },
                        },
                    },
                )()

            return type("Response", (), {"status_code": 200, "json": lambda self: {"messages": []}})()

        def fake_post(url, json=None, timeout=None):
            if url == "http://localhost:8001/extract":
                return type(
                    "Response",
                    (),
                    {
                        "status_code": 200,
                        "json": lambda self: {
                            "trips": [{"title": "Paris Trip", "location": "Paris", "start_date": "2026-11-10", "end_date": "2026-11-15", "status": "upcoming"}],
                            "bookings": [{"booking_type": "flight", "provider_name": "Air France", "confirmation_number": "AF123", "origin": "New York", "destination": "Paris", "departure_at": "2026-11-10T08:00:00Z", "arrival_at": "2026-11-10T20:00:00Z", "currency": "USD", "total_amount": 850.0, "status": "confirmed", "confidence_score": 0.98}],
                            "notes": "flight confirmed",
                        },
                    },
                )()
            if url == "http://localhost:8001/index-relevant-messages":
                return type(
                    "Response",
                    (),
                    {"status_code": 200, "json": lambda self: {"status": "ok", "indexed": {"indexed_count": 2}}},
                )()
            return type("Response", (), {"status_code": 200, "json": lambda self: {}})()

        mock_get.side_effect = fake_get
        mock_post.side_effect = fake_post

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/gmail/messages/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["messages"]), 2)
        self.assertEqual(response.data["messages"][0]["id"], "msg-1")
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(mock_post.call_args_list[0].args[0], "http://localhost:8001/extract")
        self.assertEqual(mock_post.call_args_list[1].args[0], "http://localhost:8001/index-relevant-messages")

    @patch("core.assistant.clients.requests.post")
    def test_assistant_search_routes_through_extraction_service(self, mock_post):
        responses = {
            "/route": {"route": "SEMANTIC", "entity": "any", "semantic_query": "Paris flight"},
            "/semantic-search": {"matches": [{"id": "m1", "metadata": {"subject": "Paris", "body": "Flight 2026-11-10"}}]},
            "/answer": {"answer": "Your flight to Paris is scheduled for 2026-11-10."},
        }

        def fake_post(url, json=None, timeout=None):
            response = type("R", (), {})()
            response.raise_for_status = lambda: None
            response.json = lambda: responses[url.replace("http://localhost:8001", "")]
            return response

        mock_post.side_effect = fake_post

        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/assistant/search/",
            {"query": "When is my Paris flight?"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["answer"], "Your flight to Paris is scheduled for 2026-11-10.")
        self.assertEqual(response.data["route"], "SEMANTIC")
        self.assertEqual(len(response.data["matches"]), 1)
        semantic_call = [c for c in mock_post.call_args_list if c.args[0].endswith("/semantic-search")][0]
        self.assertEqual(semantic_call.kwargs["json"]["user_email"], self.user.email)
