"""Unit tests for the Travel Buddy AI module.

Run from the project root with either:

    python -m unittest listings.ai.test

or:

    python listings/ai/test.py
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from listings.ai import calculate_match_score, generate_trip_bundle
from listings.ai.gemini import _gemini_error_response
from listings.ai.local_llm import _regex_extract_slots
from listings.ai.prompt import TravelSlots
from listings.ai.service import estimate_cost, explain_buddy_match, generate_itinerary


class RegexSlotExtractionTests(unittest.TestCase):
    def test_regex_extract_slots_reads_destination_dates_and_budget_signal(self):
        slots = _regex_extract_slots(
            "Need a 4 day budget trip to Tokyo on 2026-07-01 to 2026-07-05 with anime and food"
        )

        self.assertEqual(slots.destination, "Tokyo")
        self.assertEqual(slots.start_date, "2026-07-01")
        self.assertEqual(slots.end_date, "2026-07-05")
        self.assertEqual(slots.duration_days, 4)
        self.assertEqual(slots.budget, "low")
        self.assertEqual(slots.travel_style, "budget")
        self.assertEqual(slots.language, "en")

    def test_regex_extract_slots_detects_chinese_language(self):
        slots = _regex_extract_slots("我想去日本玩5天，低预算，喜欢美食和文化")

        self.assertEqual(slots.language, "zh")
        self.assertEqual(slots.duration_days, 5)
        self.assertEqual(slots.budget, "low")


class MatchScoreTests(unittest.TestCase):
    def test_match_score_rewards_destination_dates_style_and_interests(self):
        score = calculate_match_score(
            {
                "destination": "Tokyo, Japan",
                "start_date": "2026-07-01",
                "end_date": "2026-07-05",
                "travel_style": "budget",
                "interests": "food, anime, culture",
            },
            {
                "destination": "Japan",
                "start_date": "2026-07-03",
                "end_date": "2026-07-08",
                "travel_style": "budget",
                "interests": "culture, food, hiking",
            },
        )

        self.assertGreater(score, 0.5)
        self.assertLessEqual(score, 1.0)

    def test_match_score_handles_missing_dates(self):
        score = calculate_match_score(
            {"destination": "Paris", "travel_style": "luxury", "interests": "food, museums"},
            {"destination": "Paris", "travel_style": "luxury", "interests": "museums, cafes"},
        )

        self.assertGreater(score, 0.4)


class ServiceFallbackTests(unittest.TestCase):
    @patch("listings.ai.service.extract_slots")
    @patch("listings.ai.service.gemini_generate_itinerary")
    @patch("listings.ai.service.local_generate_itinerary")
    def test_generate_itinerary_falls_back_to_local_llm(
        self,
        mock_local_generate,
        mock_gemini_generate,
        mock_extract_slots,
    ):
        slots = TravelSlots(destination="Tokyo", duration_days=4, budget="low")
        mock_extract_slots.return_value = slots
        mock_gemini_generate.return_value = _gemini_error_response("Gemini unavailable")
        mock_local_generate.return_value = {
            "result": "Local itinerary draft",
            "source": "local_llm",
            "success": True,
            "error": None,
        }

        result = generate_itinerary("Trip to Tokyo")

        self.assertTrue(result["success"])
        self.assertEqual(result["source"], "local_llm")
        self.assertEqual(result["result"], "Local itinerary draft")
        self.assertEqual(result["slots"]["destination"], "Tokyo")

    @patch("listings.ai.service.extract_slots")
    @patch("listings.ai.service.gemini_generate_cost_estimate")
    @patch("listings.ai.service.local_generate_cost_estimate")
    def test_estimate_cost_falls_back_to_local_llm(
        self,
        mock_local_generate,
        mock_gemini_generate,
        mock_extract_slots,
    ):
        slots = TravelSlots(destination="Seoul", duration_days=5, budget="moderate")
        mock_extract_slots.return_value = slots
        mock_gemini_generate.return_value = _gemini_error_response("Gemini timeout")
        mock_local_generate.return_value = {
            "result": "Local cost estimate",
            "source": "local_llm",
            "success": True,
            "error": None,
        }

        result = estimate_cost("5 days in Seoul")

        self.assertTrue(result["success"])
        self.assertEqual(result["source"], "local_llm")
        self.assertEqual(result["result"], "Local cost estimate")
        self.assertEqual(result["slots"]["destination"], "Seoul")

    @patch("listings.ai.service.gemini_generate_buddy_match")
    @patch("listings.ai.service.local_generate_buddy_match_blurb")
    def test_explain_buddy_match_falls_back_to_local_llm(
        self,
        mock_local_generate,
        mock_gemini_generate,
    ):
        mock_gemini_generate.return_value = _gemini_error_response("Gemini auth failed")
        mock_local_generate.return_value = {
            "result": "You both like budget city trips and food exploration.",
            "source": "local_llm",
            "success": True,
            "error": None,
        }

        result = explain_buddy_match(
            {"destination": "Tokyo", "travel_style": "budget", "interests": "food"},
            {"destination": "Tokyo", "travel_style": "budget", "interests": "food, anime"},
            0.82,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["source"], "local_llm")
        self.assertIn("budget", result["result"])


class BundleShapeTests(unittest.TestCase):
    @patch("listings.ai.service.generate_itinerary")
    @patch("listings.ai.service.estimate_cost")
    def test_generate_trip_bundle_returns_expected_shape(
        self,
        mock_estimate_cost,
        mock_generate_itinerary,
    ):
        mock_generate_itinerary.return_value = {
            "result": "Gemini itinerary",
            "source": "gemini",
            "success": True,
            "error": None,
            "slots": {
                "destination": "Kyoto",
                "start_date": "2026-09-01",
                "end_date": "2026-09-04",
                "duration_days": 3,
                "budget": "moderate",
                "budget_currency": "USD",
                "interests": "temples, food",
                "travel_style": "balanced",
                "group_size": 1,
                "language": "en",
            },
        }
        mock_estimate_cost.return_value = {
            "result": "Gemini cost estimate",
            "source": "gemini",
            "success": True,
            "error": None,
            "slots": mock_generate_itinerary.return_value["slots"],
        }

        result = generate_trip_bundle("3 days in Kyoto with temples and food")

        self.assertTrue(result["success"])
        self.assertEqual(result["primary_source"], "gemini")
        self.assertEqual(result["itinerary"]["result"], "Gemini itinerary")
        self.assertEqual(result["cost_estimate"]["result"], "Gemini cost estimate")
        self.assertEqual(result["slots"]["destination"], "Kyoto")
        self.assertEqual(result["errors"], [])

    @patch("listings.ai.service.generate_itinerary")
    @patch("listings.ai.service.estimate_cost")
    def test_generate_trip_bundle_collects_errors(
        self,
        mock_estimate_cost,
        mock_generate_itinerary,
    ):
        mock_generate_itinerary.return_value = {
            "result": "Static itinerary",
            "source": "static_fallback",
            "success": True,
            "error": "Gemini unavailable",
            "slots": {"destination": "Osaka"},
        }
        mock_estimate_cost.return_value = {
            "result": "Static cost",
            "source": "static_fallback",
            "success": True,
            "error": "Ollama unavailable",
            "slots": {"destination": "Osaka"},
        }

        result = generate_trip_bundle("Trip to Osaka")

        self.assertTrue(result["success"])
        self.assertEqual(result["primary_source"], "static_fallback")
        self.assertEqual(result["errors"], ["Gemini unavailable", "Ollama unavailable"])


if __name__ == "__main__":
    unittest.main()
