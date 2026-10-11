from unittest.mock import patch

from django.contrib.auth import get_user_model
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

    def test_google_login_route_is_disabled_for_manual_login(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": "demo@example.com", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 410)

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

    @patch("core.views.requests.get")
    def test_gmail_messages_endpoint_returns_messages_for_authenticated_user(self, mock_get):
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

        mock_get.side_effect = fake_get

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/gmail/messages/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["messages"]), 2)
        self.assertEqual(response.data["messages"][0]["id"], "msg-1")
