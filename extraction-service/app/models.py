from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class EmailMessage(BaseModel):
    id: str
    threadId: Optional[str] = None
    subject: str = ""
    from_email: str = Field(default="", alias="from")
    to: str = ""
    date: str = ""
    snippet: str = ""
    body: str = ""


class ExtractionInput(BaseModel):
    source: str = "gmail"
    user_email: str
    year: int
    messages: List[EmailMessage]


class BookingExtraction(BaseModel):
    booking_type: str = Field(..., description="flight, hotel, train, bus")
    provider_name: str = ""
    confirmation_number: str = ""
    origin: str = ""
    destination: str = ""
    departure_at: Optional[str] = None
    arrival_at: Optional[str] = None
    check_in_at: Optional[str] = None
    check_out_at: Optional[str] = None
    currency: str = "USD"
    total_amount: Optional[float] = None
    status: str = "confirmed"
    confidence_score: float = 0.0


class TripExtraction(BaseModel):
    title: str = ""
    location: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str = "upcoming"


class ExtractionResult(BaseModel):
    trips: List[TripExtraction] = Field(default_factory=list)
    bookings: List[BookingExtraction] = Field(default_factory=list)
    notes: str = ""
