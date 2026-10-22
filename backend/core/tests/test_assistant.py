from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.assistant import chain, service, structured
from core.models import Booking, Trip
from core.persistence import save_extraction

TODAY = date(2026, 10, 22)


def plan(**overrides):
    base = {"route": "STRUCTURED", "entity": "trip", "time_scope": "upcoming", "status": "any", "date_from": "",
            "date_to": "", "destination": "", "provider": "", "sort": "date_asc", "limit": 1, "semantic_query": "q"}
    base.update(overrides)
    return base


class StructuredSearchTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="a", email="a@example.com", password="x")
        self.other = get_user_model().objects.create_user(username="b", email="b@example.com", password="x")
        extraction = {
            "trips": [
                {"title": "Old Goa", "location": "Goa", "start_date": "2026-03-01", "status": "completed", "source_message_id": "m1"},
                {"title": "Cancelled Paris", "location": "Paris", "start_date": "2026-10-25", "status": "cancelled", "source_message_id": "m2"},
                {"title": "Tokyo", "location": "Tokyo", "start_date": "2026-11-10", "status": "upcoming", "source_message_id": "m3"},
                {"title": "London", "location": "London", "start_date": "2027-01-05", "status": "upcoming", "source_message_id": "m4"},
            ],
            "bookings": [
                {"booking_type": "flight", "provider_name": "ANA", "confirmation_number": "ANA1", "origin": "BOM", "destination": "Tokyo",
                 "departure_at": "2026-11-10T09:00:00Z", "status": "confirmed", "total_amount": 900, "source_message_id": "m3"},
                {"booking_type": "flight", "provider_name": "AF", "confirmation_number": "AF1", "origin": "BOM", "destination": "Paris",
                 "departure_at": "2026-10-25T09:00:00Z", "status": "cancelled", "total_amount": 500, "source_message_id": "m2"},
                {"booking_type": "flight", "provider_name": "BA", "confirmation_number": "BA1", "origin": "BOM", "destination": "London",
                 "departure_at": "2027-01-05T09:00:00Z", "status": "confirmed", "total_amount": 700, "source_message_id": "m4"},
            ],
        }
        save_extraction(self.user, None, extraction)

    def test_next_trip_skips_past_and_cancelled(self):
        result = structured.search(self.user, plan(), TODAY)
        self.assertEqual([t["title"] for t in result["trips"]], ["Tokyo"])

    def test_next_flight_is_earliest_confirmed_future(self):
        result = structured.search(self.user, plan(entity="flight"), TODAY)
        self.assertEqual([b["provider"] for b in result["bookings"]], ["ANA"])

    def test_cancelled_filter(self):
        result = structured.search(self.user, plan(time_scope="any", status="cancelled", limit=5), TODAY)
        self.assertEqual([t["title"] for t in result["trips"]], ["Cancelled Paris"])

    def test_past_trip_and_price_sort(self):
        past = structured.search(self.user, plan(time_scope="past", sort="date_desc"), TODAY)
        self.assertEqual(past["trips"][0]["title"], "Old Goa")
        cheapest = structured.search(self.user, plan(entity="flight", time_scope="any", sort="price_asc", limit=2), TODAY)
        self.assertEqual([b["provider"] for b in cheapest["bookings"]], ["AF", "BA"])

    def test_users_are_isolated(self):
        self.assertEqual(structured.search(self.other, plan(), TODAY), {"trips": [], "bookings": []})

    def test_message_ids_for_hybrid(self):
        result = structured.search(self.user, plan(), TODAY)
        self.assertEqual(structured.message_ids(result), ["m3"])


class ActivityBookingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="a", email="a@example.com", password="x")
        save_extraction(self.user, None, {"trips": [], "bookings": [
            {"booking_type": "activity", "provider_name": "Dive Andaman", "confirmation_number": "SCUBA5521",
             "destination": "Havelock Island, Andaman Islands", "check_in_at": "2026-12-22T09:00:00Z",
             "status": "confirmed", "total_amount": 5000, "source_message_id": "m9"},
        ]})

    def test_activity_is_persisted_with_its_destination(self):
        booking = Booking.objects.get()
        self.assertEqual((booking.booking_type, booking.destination, booking.gmail_message_id),
                         ("activity", "Havelock Island, Andaman Islands", "m9"))

    def test_structured_search_by_activity_entity(self):
        result = structured.search(self.user, plan(entity="activity"), TODAY)
        self.assertEqual(result["bookings"][0]["provider"], "Dive Andaman")

    def test_destination_for_followup_comes_from_the_activity_booking(self):
        match = [{"metadata": {"message_id": "m9", "subject": "Scuba", "body": "..."}}]
        self.assertEqual(chain.destinations(self.user, {"trips": [], "bookings": []}, match, prefer_emails=True),
                         ["Havelock Island, Andaman Islands"])


class PersistenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="a", email="a@example.com", password="x")

    def test_resync_is_idempotent_and_cancellation_applies(self):
        booking = {"booking_type": "flight", "confirmation_number": "X1", "destination": "Rome", "departure_at": "2026-12-01T08:00:00Z",
                   "status": "confirmed", "source_message_id": "m1"}
        data = {"trips": [{"title": "Rome", "location": "Rome", "start_date": "2026-12-01", "status": "upcoming", "source_message_id": "m1"}],
                "bookings": [booking]}
        save_extraction(self.user, None, data)
        save_extraction(self.user, None, data)
        self.assertEqual((Trip.objects.count(), Booking.objects.count()), (1, 1))

        cancel = {"trips": [], "bookings": [{"booking_type": "flight", "confirmation_number": "X1", "status": "cancelled", "source_message_id": "m2"}]}
        save_extraction(self.user, None, cancel)
        self.assertEqual(Booking.objects.get(departure_at__isnull=False).status, "cancelled")

    def test_bad_dates_and_types_do_not_crash(self):
        data = {"trips": [{"title": "T", "start_date": "10 Feb", "status": "weird"}],
                "bookings": [{"booking_type": "cab"}, {"booking_type": "hotel", "check_in_at": "nonsense", "total_amount": "abc"}]}
        save_extraction(self.user, None, data)
        self.assertEqual(Trip.objects.get().status, "upcoming")
        self.assertEqual(Booking.objects.count(), 1)


class OrchestrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="a", email="a@example.com", password="x")
        save_extraction(self.user, None, {
            "trips": [{"title": "Tokyo", "location": "Tokyo", "start_date": "2026-11-10", "status": "upcoming", "source_message_id": "m3"}],
            "bookings": [{"booking_type": "flight", "provider_name": "ANA", "destination": "Tokyo", "departure_at": "2026-11-10T09:00:00Z", "source_message_id": "m3"}],
        })

    def run_service(self, route_plan, matches=None, answer="ok", search_side_effect=None, web=None):
        with patch.object(service.clients, "route_query", return_value=route_plan), \
             patch.object(service.clients, "web_search", return_value=web or []) as self.web_mock, \
             patch.object(service.clients, "semantic_search", return_value=matches or [], side_effect=search_side_effect) as sem, \
             patch.object(service.clients, "generate_answer", return_value=answer) as gen:
            return service.answer_question(self.user, "q", TODAY), sem, gen

    def test_structured_does_not_call_pinecone(self):
        result, sem, gen = self.run_service(plan(entity="flight"))
        sem.assert_not_called()
        self.assertEqual(gen.call_args[0][1]["bookings"][0]["provider"], "ANA")
        self.assertEqual(result["route"], "STRUCTURED")

    def test_hybrid_scopes_semantic_to_booking_email(self):
        match = [{"metadata": {"subject": "Your ANA ticket", "body": "Baggage 23kg"}}]
        _, sem, gen = self.run_service(plan(route="HYBRID", entity="flight"), matches=match)
        self.assertEqual(sem.call_args.kwargs["message_ids"], ["m3"])
        self.assertIn("Baggage", gen.call_args[0][2][0]["excerpt"])

    def test_structured_miss_falls_back_to_semantic(self):
        result, sem, _ = self.run_service(plan(entity="hotel"))
        sem.assert_called()
        self.assertEqual(result["route"], "STRUCTURED->SEMANTIC")

    def test_web_route_uses_google_only(self):
        web = [{"title": "Baggage", "url": "https://airindia.com/b", "snippet": "25kg"}]
        result, sem, gen = self.run_service(plan(route="WEB", web_query="Air India baggage allowance"), web=web)
        sem.assert_not_called()
        self.web_mock.assert_called_once_with("Air India baggage allowance")
        self.assertEqual(gen.call_args[0][3], web)
        self.assertEqual(result["route"], "WEB")

    def test_web_failure_still_answers(self):
        with patch.object(service.clients, "route_query", return_value=plan(route="WEB")), \
             patch.object(service.clients, "web_search", side_effect=RuntimeError("down")), \
             patch.object(service.clients, "generate_answer", return_value="sorry") as gen:
            result = service.answer_question(self.user, "q", TODAY)
        self.assertEqual((result["answer"], gen.call_args[0][3]), ("sorry", []))

    def test_semantic_without_email_matches_falls_back_to_web(self):
        web = [{"title": "t", "url": "u", "snippet": "s"}]
        _, _, gen = self.run_service(plan(route="SEMANTIC"), matches=[], web=web)
        self.assertEqual(gen.call_args[0][3], web)

    def test_email_matches_skip_web(self):
        match = [{"metadata": {"subject": "s", "body": "b"}}]
        self.run_service(plan(route="SEMANTIC"), matches=match)
        self.web_mock.assert_not_called()

    def test_generic_web_question_unaffected_by_followup_support(self):
        result, sem, gen = self.run_service(plan(route="WEB", web_query="Air India luggage policy", followup=None),
                                            web=[{"title": "t", "url": "u", "snippet": "s"}])
        self.web_mock.assert_called_once_with("Air India luggage policy")
        self.assertNotIn("for", gen.call_args[0][3][0])

    def test_followup_searches_each_distinct_provider(self):
        save_extraction(self.user, None, {"trips": [], "bookings": [
            {"booking_type": "flight", "provider_name": "IndiGo", "destination": "Goa", "departure_at": "2026-12-01T09:00:00Z", "source_message_id": "m5"},
            {"booking_type": "flight", "provider_name": "IndiGo", "destination": "Delhi", "departure_at": "2026-12-05T09:00:00Z", "source_message_id": "m6"},
        ]})
        fu = {"for_each": "provider", "web_template": "{provider} baggage allowance"}
        queries = []
        def fake_search(query, num=5):
            queries.append(query)
            return [{"title": "t", "url": "u", "snippet": query}]
        with patch.object(service.clients, "route_query", return_value=plan(entity="flight", limit=10, followup=fu)), \
             patch.object(service.clients, "web_search", side_effect=fake_search), \
             patch.object(service.clients, "generate_answer", return_value="ok") as gen:
            service.answer_question(self.user, "luggage for upcoming flights", TODAY)
        self.assertEqual(sorted(queries), ["ANA baggage allowance", "IndiGo baggage allowance"])
        self.assertEqual({w["for"] for w in gen.call_args[0][3]}, {"ANA", "IndiGo"})

    def test_followup_destination_from_matched_email_via_db(self):
        fu = {"for_each": "destination", "web_template": "current weather in {destination}"}
        match = [{"metadata": {"message_id": "m3", "subject": "Scuba", "body": "dive"}}]
        with patch.object(service.clients, "route_query", return_value=plan(route="SEMANTIC", followup=fu)), \
             patch.object(service.clients, "semantic_search", return_value=match), \
             patch.object(service.clients, "web_search", return_value=[{"title": "w", "url": "u", "snippet": "sunny"}]) as ws, \
             patch.object(service.clients, "extract_destination") as llm, \
             patch.object(service.clients, "generate_answer", return_value="ok") as gen:
            service.answer_question(self.user, "scuba weather", TODAY)
        ws.assert_called_once_with("current weather in Tokyo", num=3)
        llm.assert_not_called()
        self.assertEqual(gen.call_args[0][3][0]["for"], "Tokyo")

    def test_followup_destination_falls_back_to_llm_reading_email(self):
        fu = {"for_each": "destination", "web_template": "weather in {destination}"}
        match = [{"metadata": {"message_id": "unknown", "subject": "Scuba", "body": "Dive in Bali"}}]
        with patch.object(service.clients, "route_query", return_value=plan(route="SEMANTIC", followup=fu)), \
             patch.object(service.clients, "semantic_search", return_value=match), \
             patch.object(service.clients, "extract_destination", return_value="Bali"), \
             patch.object(service.clients, "web_search", return_value=[]) as ws, \
             patch.object(service.clients, "generate_answer", return_value="ok"):
            service.answer_question(self.user, "q", TODAY)
        ws.assert_called_once_with("weather in Bali", num=3)

    def test_destination_priority_between_structured_and_email(self):
        structured_result = {"trips": [{"title": "Jaipur", "location": "Jaipur", "bookings": []}], "bookings": []}
        match = [{"metadata": {"message_id": "unknown", "subject": "Scuba", "body": "Location: Havelock Island"}}]
        with patch.object(service.clients, "extract_destination", return_value="Havelock Island"):
            self.assertEqual(chain.destinations(self.user, structured_result, match, prefer_emails=True), ["Havelock Island"])
            self.assertEqual(chain.destinations(self.user, structured_result, match), ["Jaipur"])

    def test_followup_with_nothing_found_does_not_search(self):
        fu = {"for_each": "destination", "web_template": "weather in {destination}"}
        result, _, gen = self.run_service(plan(route="SEMANTIC", followup=fu), matches=[])
        self.web_mock.assert_not_called()
        self.assertEqual(gen.call_args[0][3], [])

    def test_router_failure_defaults_to_hybrid(self):
        with patch.object(service.clients, "route_query", side_effect=RuntimeError("down")), \
             patch.object(service.clients, "semantic_search", return_value=[]), \
             patch.object(service.clients, "web_search", return_value=[]), \
             patch.object(service.clients, "generate_answer", return_value="ok"):
            result = service.answer_question(self.user, "anything", TODAY)
        self.assertEqual(result["route"], "HYBRID")

    def test_llm_failure_uses_deterministic_answer(self):
        with patch.object(service.clients, "route_query", return_value=plan()), \
             patch.object(service.clients, "generate_answer", side_effect=RuntimeError("llm down")):
            result = service.answer_question(self.user, "next trip?", TODAY)
        self.assertIn("Tokyo", result["answer"])


class ReextractionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="a", email="a@example.com", password="x")

    def test_undated_booking_falls_back_to_trip_start_date(self):
        save_extraction(self.user, None, {
            "trips": [{"title": "Delhi", "location": "Delhi", "start_date": "2026-11-15", "source_message_id": "m1"}],
            "bookings": [{"booking_type": "flight", "provider_name": "IndiGo", "source_message_id": "m1"}],
        })
        result = structured.search(self.user, plan(entity="flight"), TODAY)
        self.assertEqual([b["provider"] for b in result["bookings"]], ["IndiGo"])
        self.assertEqual(result["bookings"][0]["when"].date(), date(2026, 11, 15))

    def test_reextracting_an_email_replaces_sparse_booking_and_reuses_trip(self):
        trip = {"title": "Trip to Delhi", "location": "Delhi", "start_date": "2026-11-15", "source_message_id": "m1"}
        save_extraction(self.user, None, {"trips": [trip], "bookings": [{"booking_type": "flight", "provider_name": "IndiGo", "source_message_id": "m1"}]})
        full = {"booking_type": "flight", "provider_name": "IndiGo", "confirmation_number": "6E1", "origin": "Bengaluru",
                "destination": "Delhi", "departure_at": "2026-11-15T08:30:00Z", "source_message_id": "m1"}
        save_extraction(self.user, None, {"trips": [dict(trip, title="Flight to Delhi")], "bookings": [full]})
        self.assertEqual((Trip.objects.count(), Booking.objects.count()), (1, 1))
        self.assertEqual(Booking.objects.get().origin, "Bengaluru")

    def test_only_one_trip_per_email(self):
        save_extraction(self.user, None, {"trips": [
            {"title": "Bus trip to Coorg", "location": "Coorg", "start_date": "2026-11-28", "source_message_id": "m1"},
            {"title": "Bus to Coorg", "location": "Madikeri", "start_date": "2026-11-28", "source_message_id": "m1"},
        ], "bookings": []})
        self.assertEqual(Trip.objects.count(), 1)

    def test_cancellation_wins_regardless_of_processing_order(self):
        original = {"booking_type": "flight", "confirmation_number": "X1", "departure_at": "2026-12-01T08:00:00Z", "status": "confirmed", "source_message_id": "m1"}
        cancel = {"booking_type": "flight", "confirmation_number": "X1", "status": "cancelled", "source_message_id": "m2"}
        trip = {"title": "Rome", "location": "Rome", "start_date": "2026-12-01", "source_message_id": "m1"}
        save_extraction(self.user, None, {"trips": [], "bookings": [cancel]})
        save_extraction(self.user, None, {"trips": [trip], "bookings": [original]})
        self.assertFalse(Booking.objects.exclude(status="cancelled").exists())


class ClientSerializationTests(TestCase):
    def test_generate_answer_sends_orm_dates_as_json(self):
        from datetime import datetime, timezone
        from decimal import Decimal
        from core.assistant import clients

        structured_result = {"trips": [{"start_date": date(2026, 12, 10)}],
                             "bookings": [{"when": datetime(2026, 12, 10, 20, 30, tzinfo=timezone.utc), "total_amount": Decimal("28455.00")}]}
        with patch.object(clients.requests, "post") as post:
            post.return_value.json.return_value = {"answer": "ok"}
            self.assertEqual(clients.generate_answer("q", structured_result, []), "ok")
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["structured"]["trips"][0]["start_date"], "2026-12-10")
        self.assertTrue(sent["structured"]["bookings"][0]["when"].startswith("2026-12-10T20:30"))
