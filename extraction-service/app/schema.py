TRAVEL_EXTRACTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "trips": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "location": {"type": "STRING"},
                    "start_date": {"type": "STRING", "nullable": True},
                    "end_date": {"type": "STRING", "nullable": True},
                    "status": {"type": "STRING"},
                },
                "required": ["title", "location", "status"],
            },
        },
        "bookings": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "booking_type": {"type": "STRING"},
                    "provider_name": {"type": "STRING"},
                    "confirmation_number": {"type": "STRING"},
                    "origin": {"type": "STRING"},
                    "destination": {"type": "STRING"},
                    "departure_at": {"type": "STRING", "nullable": True},
                    "arrival_at": {"type": "STRING", "nullable": True},
                    "check_in_at": {"type": "STRING", "nullable": True},
                    "check_out_at": {"type": "STRING", "nullable": True},
                    "currency": {"type": "STRING"},
                    "total_amount": {"type": "NUMBER", "nullable": True},
                    "status": {"type": "STRING"},
                    "confidence_score": {"type": "NUMBER"},
                },
                "required": ["booking_type"],
            },
        },
        "notes": {"type": "STRING"},
    },
    "required": ["trips", "bookings", "notes"],
}
