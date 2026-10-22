import unittest
from unittest.mock import MagicMock, patch

from app import web_search as ws
from app.config import Settings


class WebSearchTests(unittest.TestCase):
    def test_parses_results_and_sends_bearer_key(self):
        resp = MagicMock()
        resp.json.return_value = {"results": [{"title": "T", "url": "https://a.com", "content": "x \n y"}]}
        with patch.object(ws, "get_settings", return_value=Settings(tavily_api_key="k")), \
             patch.object(ws.httpx, "post", return_value=resp) as post:
            out = ws.web_search("air india baggage", num=50)
        self.assertEqual(out, [{"title": "T", "url": "https://a.com", "snippet": "x y"}])
        self.assertEqual(post.call_args.kwargs["json"]["max_results"], 10)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer k")

    def test_missing_key_returns_empty_without_calling(self):
        with patch.object(ws, "get_settings", return_value=Settings(tavily_api_key="")), patch.object(ws.httpx, "post") as post:
            self.assertEqual(ws.web_search("q"), [])
        post.assert_not_called()

    def test_http_error_returns_empty(self):
        with patch.object(ws, "get_settings", return_value=Settings(tavily_api_key="k")), \
             patch.object(ws.httpx, "post", side_effect=RuntimeError("boom")):
            self.assertEqual(ws.web_search("q"), [])


if __name__ == "__main__":
    unittest.main()
