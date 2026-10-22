import json
import unittest
from datetime import date

from app.query_router import classify_query, heuristic_plan, normalize_plan

TODAY = date(2026, 10, 22)


class QueryRouterTests(unittest.TestCase):
    def test_llm_plan_is_used_and_normalised(self):
        raw = {"route": "hybrid", "entity": "Flight", "time_scope": "upcoming", "sort": "date_asc", "limit": 99, "date_from": "tomorrow"}
        plan = classify_query("baggage for my next flight", TODAY, llm=lambda _: json.dumps(raw))
        self.assertEqual((plan["route"], plan["entity"], plan["limit"], plan["date_from"]), ("HYBRID", "flight", 10, ""))
        self.assertEqual(plan["classified_by"], "llm")

    def test_invalid_json_falls_back_to_heuristic(self):
        plan = classify_query("which is my next trip?", TODAY, llm=lambda _: "not json")
        self.assertEqual(plan["classified_by"], "heuristic")
        self.assertEqual((plan["route"], plan["entity"], plan["time_scope"], plan["limit"]), ("STRUCTURED", "trip", "upcoming", 1))

    def test_llm_exception_falls_back(self):
        def boom(_):
            raise RuntimeError("down")
        self.assertEqual(classify_query("x", TODAY, llm=boom)["classified_by"], "heuristic")

    def test_heuristic_routes(self):
        self.assertEqual(heuristic_plan("what is the baggage policy")["route"], "SEMANTIC")
        self.assertEqual(heuristic_plan("baggage allowance for my next flight")["route"], "HYBRID")
        self.assertEqual(heuristic_plan("show cancelled hotels")["status"], "cancelled")
        self.assertEqual(heuristic_plan("hello there")["route"], "HYBRID")

    def test_web_route_heuristic(self):
        self.assertEqual(heuristic_plan("baggage allowance for Air India flight")["route"], "WEB")
        self.assertEqual(heuristic_plan("baggage allowance for my next Air India flight")["route"], "HYBRID")

    def test_web_query_defaults_to_question(self):
        plan = normalize_plan({"route": "web", "web_query": "Air India baggage"}, "q")
        self.assertEqual((plan["route"], plan["web_query"]), ("WEB", "Air India baggage"))
        self.assertEqual(normalize_plan({}, "q")["web_query"], "q")

    def test_followup_is_validated(self):
        good = {"route": "STRUCTURED", "followup": {"for_each": "provider", "web_template": "{provider} baggage"}}
        self.assertEqual(normalize_plan(good, "q")["followup"], {"for_each": "provider", "web_template": "{provider} baggage"})
        for bad in ({"for_each": "provider", "web_template": "no placeholder"}, {"for_each": "x", "web_template": "{x}"}, "junk"):
            self.assertIsNone(normalize_plan({"route": "STRUCTURED", "followup": bad}, "q")["followup"])
        self.assertIsNone(normalize_plan({"route": "WEB", "followup": good["followup"]}, "q")["followup"])
        self.assertIsNone(normalize_plan({}, "q")["followup"])

    def test_activity_questions_use_email_search(self):
        self.assertEqual(heuristic_plan("for my scuba diving trip, weather of that city")["route"], "SEMANTIC")

    def test_activity_entity(self):
        self.assertEqual(normalize_plan({"entity": "Activity"}, "q")["entity"], "activity")
        self.assertEqual(heuristic_plan("my scuba diving booking")["entity"], "activity")

    def test_garbage_plan_gets_safe_defaults(self):
        plan = normalize_plan("junk", "q")
        self.assertEqual((plan["route"], plan["limit"], plan["semantic_query"]), ("HYBRID", 5, "q"))


if __name__ == "__main__":
    unittest.main()
