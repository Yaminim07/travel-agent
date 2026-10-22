"""Persist LLM extraction output into Trip / Booking rows (idempotent across re-syncs)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from .models import Booking, Trip

logger = logging.getLogger("travel_agent.backend")

BOOKING_TYPES = {choice for choice, _ in Booking.BOOKING_TYPE_CHOICES}
TRIP_STATUSES = {choice for choice, _ in Trip.STATUS_CHOICES}


def parse_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


def parse_date(value: Any) -> Optional[date]:
    parsed = parse_datetime(value)
    return parsed.date() if parsed else None


def _amount(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _booking_anchor_date(booking: Dict[str, Any]) -> Optional[date]:
    return parse_date(booking.get("departure_at")) or parse_date(booking.get("check_in_at"))


def _upsert_trip(user, google_account, data: Dict[str, Any]) -> Trip:
    """One trip per (user, location, start_date); titles vary run to run so they are not part of the key."""
    status = str(data.get("status") or "upcoming").lower()
    trip, _ = Trip.objects.update_or_create(
        user=user,
        location=(data.get("location") or "")[:255],
        start_date=parse_date(data.get("start_date")),
        defaults={
            "google_account": google_account,
            "title": (data.get("title") or "")[:255],
            "end_date": parse_date(data.get("end_date")),
            "status": status if status in TRIP_STATUSES else "upcoming",
        },
    )
    return trip


@transaction.atomic
def save_extraction(user, google_account, extraction: Dict[str, Any]) -> Dict[str, int]:
    """Upsert trips and bookings from one ``/extract`` response. Returns counts saved."""
    # Re-extracting an email replaces its old bookings instead of adding to them.
    message_ids = {str(b.get("source_message_id") or "") for b in extraction.get("bookings", []) or []} - {""}
    if message_ids:
        Booking.objects.filter(trip__user=user, gmail_message_id__in=message_ids).delete()

    trips_by_message: Dict[str, Trip] = {}
    all_trips: List[Trip] = []
    for data in extraction.get("trips", []) or []:
        message_id = str(data.get("source_message_id") or "")
        if message_id and message_id in trips_by_message:
            continue  # one trip per email; ignore extra trips the model invented for the same journey
        trip = _upsert_trip(user, google_account, data)
        all_trips.append(trip)
        trips_by_message.setdefault(message_id, trip)

    saved_bookings = 0
    for data in extraction.get("bookings", []) or []:
        booking_type = str(data.get("booking_type") or "").lower()
        if booking_type not in BOOKING_TYPES:
            logger.info("[PERSIST] Skipping unsupported booking_type=%r", booking_type)
            continue

        message_id = str(data.get("source_message_id") or "")
        trip = trips_by_message.get(message_id) or (all_trips[0] if len(all_trips) == 1 else None)
        if trip is None:
            destination = data.get("destination") or ""
            anchor = _booking_anchor_date(data)
            trip = _upsert_trip(
                user,
                google_account,
                {
                    "title": f"{destination} trip" if destination else f"{booking_type.title()} booking",
                    "location": destination,
                    "start_date": anchor.isoformat() if anchor else None,
                    "status": "upcoming",
                },
            )

        status = str(data.get("status") or "confirmed").lower()
        confirmation = (data.get("confirmation_number") or "")[:255]
        departure_at = parse_datetime(data.get("departure_at"))
        check_in_at = parse_datetime(data.get("check_in_at"))

        # A cancellation applies to every leg of the same confirmation, even if
        # the cancellation email omits the original times, and regardless of the
        # order the emails are processed in.
        if confirmation:
            same_booking = Booking.objects.filter(trip__user=user, confirmation_number=confirmation, booking_type=booking_type)
            if status == "cancelled":
                same_booking.update(status="cancelled")
            elif same_booking.filter(status="cancelled").exclude(gmail_message_id=message_id).exists():
                status = "cancelled"

        Booking.objects.update_or_create(
            trip=trip,
            booking_type=booking_type,
            confirmation_number=confirmation,
            origin=(data.get("origin") or "")[:255],
            destination=(data.get("destination") or "")[:255],
            departure_at=departure_at,
            check_in_at=check_in_at,
            defaults={
                "gmail_message_id": message_id,
                "provider_name": (data.get("provider_name") or "")[:255],
                "arrival_at": parse_datetime(data.get("arrival_at")),
                "check_out_at": parse_datetime(data.get("check_out_at")),
                "currency": (data.get("currency") or "USD")[:10],
                "total_amount": _amount(data.get("total_amount")),
                "status": status[:50],
                "confidence_score": float(data.get("confidence_score") or 0.0),
                "raw_extracted_data": data,
            },
        )
        saved_bookings += 1

    return {"trips": len(all_trips), "bookings": saved_bookings}
