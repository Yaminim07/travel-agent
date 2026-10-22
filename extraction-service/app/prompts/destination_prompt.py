DESTINATION_PROMPT = """
From the travel email below, name the main destination: the single city or place the traveller is going to (not the departure city).
Return only JSON: {{"destination": "city or place, or empty if unclear"}}

Subject: {subject}

Email:
{body}
"""
