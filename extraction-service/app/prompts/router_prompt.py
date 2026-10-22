ROUTER_PROMPT = """
You route questions for a travel assistant that can search three sources:
- STRUCTURED: the user's trips/bookings database (dates, destinations, providers, status, prices).
- SEMANTIC: the text of the user's travel emails (policies, baggage allowance, amenities, instructions, details not stored as fields).

- WEB: a web search, for general travel knowledge that is not about the user's own bookings (airline/hotel policies, visas, airport info, weather).

Choose one route:
- STRUCTURED: the answer is a stored field (e.g. "when is my next flight", "which trips are cancelled", "how much was my hotel").
- SEMANTIC: the answer is only in email text and does not depend on picking a specific booking (e.g. "what is the cancellation policy of the Hilton").
- HYBRID: needs a specific booking first, then details from its email (e.g. "what is the baggage allowance for my next flight").
- WEB: general public information not tied to the user's own booking (e.g. "what is the baggage allowance for Air India", "do I need a visa for Japan"). If the question says "my", "next", or refers to a specific booking of the user, use HYBRID/SEMANTIC/STRUCTURED instead.

Today's date is {today}.

Return only JSON with exactly these keys:
{{
  "route": "STRUCTURED" | "SEMANTIC" | "HYBRID" | "WEB",
  "entity": "flight" | "hotel" | "train" | "bus" | "activity" | "trip" | "any",
  "time_scope": "upcoming" | "past" | "any",
  "status": "confirmed" | "cancelled" | "any",
  "date_from": "YYYY-MM-DD or empty",
  "date_to": "YYYY-MM-DD or empty",
  "destination": "city/place or empty",
  "provider": "airline/hotel name or empty",
  "sort": "date_asc" | "date_desc" | "price_asc" | "price_desc",
  "limit": integer 1-10,
  "semantic_query": "the information to look up in emails, or empty",
  "followup": null | {{"for_each": "provider" | "destination", "web_template": "query with {{provider}} or {{destination}}"}},
  "web_query": "a concise, self-contained web search query for WEB (include airline/place names and key qualifiers), or empty"
}}
"next"/"upcoming"/"soon" => time_scope upcoming, sort date_asc, limit 1 for "next" (singular). "last"/"previous" => past, date_desc.
Two-step questions: when the answer needs a web search about something found in step 1, add "followup" (otherwise null). The route is then the FIRST step (STRUCTURED/SEMANTIC/HYBRID, never WEB) and the web search runs afterwards, once per distinct value:
- "for_each": "provider" (one search per airline/hotel found in the user's bookings) or "destination" (one search per place found in the user's bookings/emails).
- "web_template": a search query containing the placeholder {{provider}} or {{destination}}.
Examples:
- "luggage details of all my upcoming flights" => route STRUCTURED, entity flight, time_scope upcoming, limit 10, followup {{"for_each": "provider", "web_template": "{{provider}} checked and cabin baggage allowance"}}
- "find my booking email mentioning scuba diving and check the destination's current weather" => route SEMANTIC, semantic_query "scuba diving booking", followup {{"for_each": "destination", "web_template": "current weather in {{destination}}"}}
- "for my scuba diving trip, tell me the weather of that city" => route SEMANTIC, semantic_query "scuba diving booking", followup {{"for_each": "destination", "web_template": "current weather in {{destination}}"}}
- An activity, tour or experience named by the user (scuba diving, spa, safari, concert): use SEMANTIC with that activity in semantic_query, entity "activity". Do not fill "destination" for these: the place comes from the email. Use STRUCTURED with entity "activity" only for generic listings like "show my activities".
- "what is the luggage policy of Air India" is NOT two-step: route WEB, followup null.
"trip" is the default entity for generic trip questions.

Question: {question}
"""
