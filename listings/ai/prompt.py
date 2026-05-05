"""
TravelBuddy – Prompt templates for all AI features.

Usage pattern:
    from .prompt import PromptBuilder
    prompt = PromptBuilder.itinerary(user_input, slots)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────
# Shared system persona
# ─────────────────────────────────────────────

TRAVEL_SYSTEM_PERSONA = """\
You are TravelBuddy AI, an expert travel planner and cost analyst.
You are concise, practical, and friendly. Always reply in the same language the user writes in.
Never invent specific prices without noting they are estimates.
Format responses clearly with sections and bullet points where helpful.\
"""


# ─────────────────────────────────────────────
# Slot schema (shared across all prompts)
# ─────────────────────────────────────────────

@dataclass
class TravelSlots:
    destination: str = "unknown destination"
    start_date: str = "unspecified"
    end_date: str = "unspecified"
    duration_days: int = 3
    budget: str = "moderate"
    budget_currency: str = "USD"
    interests: str = "general sightseeing"
    travel_style: str = "balanced"       # budget | backpacking | luxury | adventure | relaxed
    group_size: int = 1
    language: str = "en"

    def context_block(self) -> str:
        """Render slots as a readable context block for prompt injection."""
        return f"""\
- Destination   : {self.destination}
- Dates         : {self.start_date} → {self.end_date} ({self.duration_days} days)
- Budget        : {self.budget} ({self.budget_currency})
- Travel style  : {self.travel_style}
- Group size    : {self.group_size} person(s)
- Interests     : {self.interests}\
"""


# ─────────────────────────────────────────────
# Feature: Itinerary generation
# ─────────────────────────────────────────────

ITINERARY_SYSTEM = TRAVEL_SYSTEM_PERSONA + """

When generating an itinerary:
1. Organize by day (Day 1, Day 2, …).
2. For each day include: morning / afternoon / evening activities.
3. Add 1–2 specific local food recommendations per day.
4. Note practical tips (transport, booking in advance, best time to visit).
5. Keep descriptions concrete – real place names, not vague generalities.
6. End with a "Quick Tips" section (3–5 bullets).
"""

ITINERARY_USER_TEMPLATE = """\
Please create a detailed day-by-day travel itinerary based on the following:

USER REQUEST:
{raw_input}

EXTRACTED DETAILS:
{context_block}

Generate the full itinerary now.\
"""


# ─────────────────────────────────────────────
# Feature: Cost estimation
# ─────────────────────────────────────────────

COST_SYSTEM = TRAVEL_SYSTEM_PERSONA + """

When estimating travel costs:
1. Break down into categories: Flights, Accommodation, Food, Local Transport, Activities, Misc.
2. Provide LOW / MID / HIGH range for each category.
3. Give a TOTAL estimate range at the end.
4. All amounts in the user's preferred currency; note exchange-rate caveat.
5. Call out the top 2–3 cost-saving opportunities.
6. Note any items that are highly variable (season, booking time, etc.).
"""

COST_USER_TEMPLATE = """\
Please estimate the total travel cost for this trip:

USER REQUEST:
{raw_input}

TRIP DETAILS:
{context_block}

Provide a detailed cost breakdown with ranges.\
"""


# ─────────────────────────────────────────────
# Feature: Buddy matching explanation
# ─────────────────────────────────────────────

BUDDY_MATCH_SYSTEM = TRAVEL_SYSTEM_PERSONA + """

When explaining a travel buddy match:
1. Highlight 3–5 specific compatibility points between the two travelers.
2. Note any potential friction points honestly.
3. Suggest a short icebreaker question they could ask each other.
4. Keep the tone warm and encouraging, not salesy.
5. Maximum 200 words.
"""

BUDDY_MATCH_USER_TEMPLATE = """\
Explain why these two travelers are a good match:

TRAVELER A:
- Destination: {dest_a}
- Dates: {dates_a}
- Style: {style_a}
- Interests: {interests_a}

TRAVELER B:
- Destination: {dest_b}
- Dates: {dates_b}
- Style: {style_b}
- Interests: {interests_b}

Compatibility score: {score:.0%}

Write a friendly match explanation.\
"""


# ─────────────────────────────────────────────
# Feature: Slot extraction (used by Local LLM)
# ─────────────────────────────────────────────

SLOT_EXTRACTION_SYSTEM = """\
You are a travel intent parser. Extract structured travel information from user input.
Respond ONLY with a valid JSON object – no preamble, no markdown fences.

JSON schema:
{
  "destination": "string or null",
  "start_date": "YYYY-MM-DD or null",
  "end_date": "YYYY-MM-DD or null",
  "duration_days": integer or null,
  "budget": "string or null",
  "budget_currency": "3-letter ISO code or null",
  "interests": "comma-separated list or null",
  "travel_style": "budget|backpacking|luxury|adventure|relaxed or null",
  "group_size": integer or null,
  "language": "ISO 639-1 code"
}

Rules:
- Infer duration_days from dates if possible.
- If the user writes in Chinese, set language to "zh". English → "en". Japanese → "ja". etc.
- Return null for any field you cannot determine.
- Never add extra keys.\
"""

SLOT_EXTRACTION_USER_TEMPLATE = """\
Extract travel intent from:
\"{raw_input}\"\
"""


# ─────────────────────────────────────────────
# Prompt builder (convenience class)
# ─────────────────────────────────────────────

class PromptBuilder:
    """
    Central factory for all TravelBuddy prompts.
    Returns (system_prompt, user_prompt) tuples ready for any LLM API.
    """

    @staticmethod
    def itinerary(raw_input: str, slots: TravelSlots) -> tuple[str, str]:
        return (
            ITINERARY_SYSTEM,
            ITINERARY_USER_TEMPLATE.format(
                raw_input=raw_input,
                context_block=slots.context_block(),
            ),
        )

    @staticmethod
    def cost_estimate(raw_input: str, slots: TravelSlots) -> tuple[str, str]:
        return (
            COST_SYSTEM,
            COST_USER_TEMPLATE.format(
                raw_input=raw_input,
                context_block=slots.context_block(),
            ),
        )

    @staticmethod
    def buddy_match(
        dest_a: str, dates_a: str, style_a: str, interests_a: str,
        dest_b: str, dates_b: str, style_b: str, interests_b: str,
        score: float,
    ) -> tuple[str, str]:
        return (
            BUDDY_MATCH_SYSTEM,
            BUDDY_MATCH_USER_TEMPLATE.format(
                dest_a=dest_a, dates_a=dates_a, style_a=style_a, interests_a=interests_a,
                dest_b=dest_b, dates_b=dates_b, style_b=style_b, interests_b=interests_b,
                score=score,
            ),
        )

    @staticmethod
    def slot_extraction(raw_input: str) -> tuple[str, str]:
        return (
            SLOT_EXTRACTION_SYSTEM,
            SLOT_EXTRACTION_USER_TEMPLATE.format(raw_input=raw_input),
        )