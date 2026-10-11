from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .auth_views import google_callback, google_connect, login_view, logout_view, me_view
from .views import (
    BookingViewSet,
    ExtractionJobViewSet,
    GmailMessageViewSet,
    GoogleAccountViewSet,
    ProcessedEmailViewSet,
    TripViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"auth/google", GoogleAccountViewSet, basename="google-auth")
router.register(r"processed-emails", ProcessedEmailViewSet, basename="processed-email")
router.register(r"gmail", GmailMessageViewSet, basename="gmail")
router.register(r"trips", TripViewSet, basename="trip")
router.register(r"bookings", BookingViewSet, basename="booking")
router.register(r"jobs", ExtractionJobViewSet, basename="job")

urlpatterns = [
    path("auth/login/", login_view, name="login"),
    path("auth/google/connect/", google_connect, name="google-connect"),
    path("auth/google/callback/", google_callback, name="google-callback"),
    path("auth/logout/", logout_view, name="logout"),
    path("auth/me/", me_view, name="me"),
    path("gmail/messages/", GmailMessageViewSet.as_view({"get": "messages"}), name="gmail-messages"),
    path("", include(router.urls)),
]
