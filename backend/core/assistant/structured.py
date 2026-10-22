"""Structured retrieval: answer date/status/price/destination questions from the DB."""
from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional

from django.utils import timezone

from ..models import Booking, Trip

_FAR_FUTURE = datetime.max.replace(tzinfo=dt_timezone.utc)
_FAR_PAST = datetime.min.replace(tzinfo=dt_timezone.utc)
BOOKING_ENTITIES = {choice for choice, _ in Booking.BOOKING_TYPE_CHOICES}


def _booking_when(booking: Booking) -> Optional[datetime]:
    """Departure/check-in time, falling back to the trip's start date when the email gave no time."""
    when = booking.departure_at or booking.check_in_at
    if when is None and booking.trip.start_date:
        when = datetime.combine(booking.trip.start_date, datetime.min.time(), tzinfo=dt_timezone.utc)
    return when


def _booking_dict(booking: Booking) -> Dict[str, Any]:
    return {
        "type": booking.booking_type,
        "when": _booking_when(booking),
        "provider": booking.provider_name,
        "confirmation_number": booking.confirmation_number,
        "origin": booking.origin,
        "destination": booking.destination,
        "departure_at": booking.departure_at,
        "arrival_at": booking.arrival_at,
        "check_in_at": booking.check_in_at,
        "check_out_at": booking.check_out_at,
        "total_amount": str(booking.total_amount) if booking.total_amount is not None else None,
        "currency": booking.currency,
        "status": booking.status,
        "gmail_message_id": booking.gmail_message_id,
    }


def _trip_start(trip: Trip) -> Optional[date]:
    if trip.start_date:
        return trip.start_date
    whens = [w for w in (_booking_when(b) for b in trip.bookings.all()) if w]
    return min(whens).date() if whens else None


def _parse(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _in_window(day: Optional[date], plan: Dict[str, Any], today: date) -> bool:
    scope = plan.get("time_scope", "any")
    date_from, date_to = _parse(plan.get("date_from", "")), _parse(plan.get("date_to", ""))
    if day is None:
        return scope == "any" and not (date_from or date_to)
    if scope == "upcoming" and day < today:
        return False
    if scope == "past" and day >= today:
        return False
    return not ((date_from and day < date_from) or (date_to and day > date_to))


def _status_ok(status: str, wanted: str) -> bool:
    status = (status or "").lower()
    if wanted == "cancelled":
        return status in ("cancelled", "canceled")
    if wanted == "confirmed":
        return status not in ("cancelled", "canceled", "deleted")
    return True


def _hidden_by_default(status: str, plan: Dict[str, Any]) -> bool:
    """Cancelled records are only shown when the question asks for them (or status=any with no time scope)."""
    if plan.get("status") == "cancelled":
        return False
    return plan.get("time_scope") != "any" and (status or "").lower() in ("cancelled", "canceled", "deleted")


def _contains(haystack: str, needle: str) -> bool:
    return not needle or needle.lower() in (haystack or "").lower()


def search(user, plan: Dict[str, Any], today: Optional[date] = None) -> Dict[str, Any]:
    """Run ``plan`` against the user's trips/bookings. Returns ``{"trips": [...], "bookings": [...]}``."""
    today = today or timezone.localdate()
    entity = plan.get("entity", "any")
    descending = plan.get("sort", "date_asc") == "date_desc"
    by_price = plan.get("sort", "").startswith("price")
    limit = int(plan.get("limit", 5))

    if entity in BOOKING_ENTITIES:
        bookings = Booking.objects.filter(trip__user=user, booking_type=entity).exclude(trip__status="deleted").select_related("trip")
        rows: List[Booking] = []
        for booking in bookings:
            when = _booking_when(booking)
            if not _in_window(when.date() if when else None, plan, today):
                continue
            if not _status_ok(booking.status, plan.get("status", "any")) or _hidden_by_default(booking.status, plan):
                continue
            if not _contains(booking.destination, plan.get("destination", "")) and not _contains(booking.trip.location, plan.get("destination", "")):
                continue
            if not _contains(booking.provider_name, plan.get("provider", "")):
                continue
            rows.append(booking)

        if by_price:
            rows.sort(key=lambda b: (b.total_amount is None, b.total_amount or 0), reverse=plan["sort"] == "price_desc")
        else:
            rows.sort(key=lambda b: _booking_when(b) or (_FAR_PAST if descending else _FAR_FUTURE), reverse=descending)
        return {"trips": [], "bookings": [_booking_dict(b) for b in rows[:limit]]}

    trips = Trip.objects.filter(user=user).exclude(status="deleted").prefetch_related("bookings")
    selected = []
    for trip in trips:
        start = _trip_start(trip)
        if not _in_window(start, plan, today):
            continue
        if not _status_ok(trip.status, plan.get("status", "any")) or _hidden_by_default(trip.status, plan):
            continue
        destination = plan.get("destination", "")
        if not (_contains(trip.location, destination) or _contains(trip.title, destination)):
            continue
        provider = plan.get("provider", "")
        if provider and not any(_contains(b.provider_name, provider) for b in trip.bookings.all()):
            continue
        selected.append((start, trip))

    selected.sort(key=lambda pair: pair[0] or (date.min if descending else date.max), reverse=descending)

    result = []
    for start, trip in selected[:limit]:
        result.append(
            {
                "title": trip.title,
                "location": trip.location,
                "start_date": start,
                "end_date": trip.end_date,
                "status": trip.status,
                "bookings": [_booking_dict(b) for b in sorted(trip.bookings.all(), key=lambda b: _booking_when(b) or _FAR_FUTURE)],
            }
        )
    return {"trips": result, "bookings": []}


def message_ids(result: Dict[str, Any], limit: int = 5) -> List[str]:
    """Gmail message ids behind the structured result, for hybrid email lookups."""
    ids: List[str] = []
    for booking in result.get("bookings", []):
        ids.append(booking.get("gmail_message_id") or "")
    for trip in result.get("trips", []):
        ids.extend(b.get("gmail_message_id") or "" for b in trip.get("bookings", []))
    return list(dict.fromkeys(i for i in ids if i))[:limit]
