from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model for the Travel Agent backend."""

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"], name="idx_users_email"),
            models.Index(fields=["created_at"], name="idx_users_created_at"),
        ]

    def __str__(self) -> str:
        return self.email or self.username


class GoogleAccount(models.Model):
    """Placeholder Google account linkage for future OAuth integration."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="google_accounts")
    provider = models.CharField(max_length=20, default="google")
    google_user_id = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    access_token = models.TextField(blank=True, default="")
    refresh_token = models.TextField(blank=True, default="")
    token_expiry = models.DateTimeField(null=True, blank=True)
    is_connected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "google_accounts"
        indexes = [
            models.Index(fields=["user", "is_connected"], name="idx_ga_user_connected"),
            models.Index(fields=["google_user_id"], name="idx_ga_google_user_id"),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} -> {self.provider}"


class ProcessedEmail(models.Model):
    """Deduplication table for Gmail syncing in v1."""

    STATUS_CHOICES = [
        ("processed", "processed"),
        ("failed", "failed"),
        ("skipped", "skipped"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="processed_emails")
    google_account = models.ForeignKey(GoogleAccount, on_delete=models.CASCADE, related_name="processed_emails")
    gmail_message_id = models.CharField(max_length=255, db_index=True)
    thread_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="processed")
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "processed_emails"
        unique_together = ("user", "gmail_message_id")
        indexes = [
            models.Index(fields=["user", "status"], name="idx_pe_user_status"),
            models.Index(fields=["google_account", "status"], name="idx_pe_ga_status"),
        ]

    def __str__(self) -> str:
        return f"{self.gmail_message_id} ({self.status})"


class Trip(models.Model):
    """Travel trip record created from processed emails or manual updates."""

    STATUS_CHOICES = [
        ("upcoming", "upcoming"),
        ("completed", "completed"),
        ("cancelled", "cancelled"),
        ("deleted", "deleted"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trips")
    google_account = models.ForeignKey(GoogleAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="trips")
    title = models.CharField(max_length=255, blank=True, default="")
    location = models.CharField(max_length=255, blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="upcoming")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trips"
        indexes = [
            models.Index(fields=["user", "start_date"], name="idx_trips_user_start"),
            models.Index(fields=["status"], name="idx_trips_status"),
        ]

    def __str__(self) -> str:
        return self.title or f"Trip {self.id}"


class Booking(models.Model):
    """Booking record extracted from a source email."""

    BOOKING_TYPE_CHOICES = [
        ("flight", "flight"),
        ("hotel", "hotel"),
        ("train", "train"),
        ("bus", "bus"),
        ("activity", "activity"),
    ]

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="bookings")
    gmail_message_id = models.CharField(max_length=255, null=True, blank=True, default="")
    booking_type = models.CharField(max_length=20, choices=BOOKING_TYPE_CHOICES, default="flight")
    provider_name = models.CharField(max_length=255, blank=True, default="")
    confirmation_number = models.CharField(max_length=255, blank=True, default="")
    origin = models.CharField(max_length=255, blank=True, default="")
    destination = models.CharField(max_length=255, blank=True, default="")
    departure_at = models.DateTimeField(null=True, blank=True)
    arrival_at = models.DateTimeField(null=True, blank=True)
    check_in_at = models.DateTimeField(null=True, blank=True)
    check_out_at = models.DateTimeField(null=True, blank=True)
    currency = models.CharField(max_length=10, blank=True, default="USD")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=50, blank=True, default="confirmed")
    confidence_score = models.FloatField(default=0.0)
    raw_extracted_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bookings"
        indexes = [
            models.Index(fields=["trip"], name="idx_bookings_trip"),
            models.Index(fields=["booking_type", "departure_at"], name="idx_bookings_type_dep"),
            models.Index(fields=["provider_name"], name="idx_bookings_provider"),
        ]

    def __str__(self) -> str:
        return f"{self.booking_type.title()} booking for trip {self.trip_id}"


class ExtractionJob(models.Model):
    """Placeholder job table for future Gmail sync / LLM extraction processing."""

    STATUS_CHOICES = [
        ("queued", "queued"),
        ("running", "running"),
        ("success", "success"),
        ("failed", "failed"),
    ]

    JOB_TYPE_CHOICES = [
        ("gmail_sync", "gmail_sync"),
        ("llm_extract", "llm_extract"),
        ("retry", "retry"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="extraction_jobs")
    gmail_message_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    job_type = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES, default="gmail_sync")
    model_name = models.CharField(max_length=255, blank=True, default="")
    prompt_version = models.CharField(max_length=255, blank=True, default="")
    result_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "extraction_jobs"
        indexes = [
            models.Index(fields=["user", "status"], name="idx_jobs_user_status"),
            models.Index(fields=["job_type", "created_at"], name="idx_jobs_type_created"),
        ]

    def __str__(self) -> str:
        return f"{self.job_type}::{self.status}"
