"""
TravelBuddy – Unified AI service layer.

This module is the single entry point for all AI features in views.py.
It implements a Gemini-first strategy with automatic local-model fallback.

          User request
               │
    ┌──────────▼──────────┐
    │  1. extract_slots() │  ← Always runs via local HF model
    └──────────┬──────────┘
               │
    ┌──────────▼──────────────────────────────────────┐
    │  2. Primary: Gemini 2.5 Flash                   │
    │     High-quality, detailed, accurate            │
    └──────────┬──────────────────────────────────────┘
               │  if GeminiUnavailable / AuthError
    ┌──────────▼──────────────────────────────────────┐
    │  3. Fallback: StableLM local model              │
    │     Fast, offline, good-enough quality          │
    └──────────┬──────────────────────────────────────┘
               │  if local model also down
    ┌──────────▼──────────────────────────────────────┐
    │  4. Static fallback (template strings)          │
    └─────────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from .gemini import (
    gemini_generate_buddy_match,
    gemini_generate_cost_estimate,
    gemini_generate_itinerary,
)
from .local_llm import (
    extract_slots,
    local_generate_buddy_match_blurb,
    local_generate_cost_estimate,
    local_generate_itinerary,
)
from .prompt import TravelSlots

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Public API – called directly from views.py
# ─────────────────────────────────────────────

def generate_itinerary(raw_input: str) -> Dict[str, Any]:
    """
    Generate a day-by-day travel itinerary from natural language input.

    Args:
        raw_input: e.g. "5-day budget trip to Japan, love food and culture"

    Returns:
        {
            "result": str,       # the itinerary markdown/text
            "source": str,       # "gemini" | "local_llm" | "static_fallback"
            "success": bool,
            "slots": dict,       # extracted travel parameters
            "error": str | None,
        }
    """
    slots = extract_slots(raw_input)

    # Try Gemini first
    gemini_result = gemini_generate_itinerary(raw_input, slots)
    if gemini_result["success"]:
        return {**gemini_result, "slots": _slots_to_dict(slots)}

    # Fallback: local Hugging Face model
    logger.info("Falling back to local LLM for itinerary (Gemini failed: %s)", gemini_result["error"])
    local_result = local_generate_itinerary(raw_input, slots)
    return {**local_result, "slots": _slots_to_dict(slots)}


def estimate_cost(raw_input: str) -> Dict[str, Any]:
    """
    Estimate travel costs from natural language input.

    Args:
        raw_input: e.g. "10 days in Italy, mid-range budget, couple"

    Returns:
        {
            "result": str,       # cost breakdown text
            "source": str,
            "success": bool,
            "slots": dict,
            "error": str | None,
        }
    """
    slots = extract_slots(raw_input)

    gemini_result = gemini_generate_cost_estimate(raw_input, slots)
    if gemini_result["success"]:
        return {**gemini_result, "slots": _slots_to_dict(slots)}

    logger.info("Falling back to local LLM for cost estimate")
    local_result = local_generate_cost_estimate(raw_input, slots)
    return {**local_result, "slots": _slots_to_dict(slots)}


def generate_trip_bundle(raw_input: str) -> Dict[str, Any]:
    """
    Generate the full AI response bundle for a travel request.

    The local model always extracts slots first; Gemini is the primary
    generator for itinerary and cost estimate, with the local model
    providing fallback responses when needed.
    """
    itinerary = generate_itinerary(raw_input)
    cost_estimate = estimate_cost(raw_input)

    return {
        "success": itinerary["success"] or cost_estimate["success"],
        "raw_input": raw_input,
        "slots": itinerary["slots"],
        "itinerary": itinerary,
        "cost_estimate": cost_estimate,
        "primary_source": itinerary["source"] if itinerary.get("success") else cost_estimate["source"],
        "errors": [error for error in [itinerary.get("error"), cost_estimate.get("error")] if error],
    }


def explain_buddy_match(
    plan_a: Dict[str, Any],
    plan_b: Dict[str, Any],
    score: float,
) -> Dict[str, Any]:
    """
    Generate a human-readable explanation of why two travel plans are compatible.

    Args:
        plan_a / plan_b: TravelPlan-like dicts with keys:
                         destination, start_date, end_date, travel_style, interests
        score: float 0.0–1.0 from the matching algorithm

    Returns:
        { "result": str, "source": str, "success": bool, "error": str | None }
    """
    gemini_result = gemini_generate_buddy_match(plan_a, plan_b, score)
    if gemini_result["success"]:
        return gemini_result

    logger.info("Falling back to local LLM for buddy match blurb")
    return local_generate_buddy_match_blurb(plan_a, plan_b, score)


# ─────────────────────────────────────────────
# Matching score calculation (pure Python, no AI)
# ─────────────────────────────────────────────

def calculate_match_score(plan_a: Dict[str, Any], plan_b: Dict[str, Any]) -> float:
    """
    Compute a 0–1 compatibility score between two travel plans.
    Rule-based (deterministic) – AI is used only for the explanation text.

    Scoring breakdown:
        - Same destination      : 40 pts
        - Overlapping dates     : 25 pts
        - Same travel style     : 20 pts
        - Shared interests      : up to 15 pts
    """
    score = 0.0

    # 1. Destination match (case-insensitive, partial)
    dest_a = (plan_a.get("destination") or "").lower().strip()
    dest_b = (plan_b.get("destination") or "").lower().strip()
    if dest_a and dest_b:
        if dest_a == dest_b:
            score += 40
        elif dest_a in dest_b or dest_b in dest_a:
            score += 20  # partial match (e.g. "Japan" vs "Tokyo, Japan")

    # 2. Date overlap
    from datetime import date
    try:
        start_a = date.fromisoformat(plan_a.get("start_date") or "")
        end_a   = date.fromisoformat(plan_a.get("end_date")   or "")
        start_b = date.fromisoformat(plan_b.get("start_date") or "")
        end_b   = date.fromisoformat(plan_b.get("end_date")   or "")

        overlap_start = max(start_a, start_b)
        overlap_end   = min(end_a, end_b)
        overlap_days  = max(0, (overlap_end - overlap_start).days)

        if overlap_days > 0:
            # Full overlap or partial – scale up to 25 pts
            plan_duration = max(1, (end_a - start_a).days)
            score += min(25, 25 * (overlap_days / plan_duration))
    except (ValueError, TypeError):
        pass  # dates not available

    # 3. Travel style match
    style_a = (plan_a.get("travel_style") or "").lower()
    style_b = (plan_b.get("travel_style") or "").lower()
    if style_a and style_b and style_a == style_b:
        score += 20

    # 4. Shared interests (tokenize and count overlap)
    interests_a = set(_tokenize(plan_a.get("interests") or ""))
    interests_b = set(_tokenize(plan_b.get("interests") or ""))
    if interests_a and interests_b:
        overlap = interests_a & interests_b
        union   = interests_a | interests_b
        jaccard = len(overlap) / len(union)
        score += jaccard * 15

    return round(min(score, 100) / 100, 3)  # normalise to 0.0–1.0


def _tokenize(text: str) -> list[str]:
    import re
    return [w.lower() for w in re.findall(r"[a-zA-Z]{3,}", text)]


def _slots_to_dict(slots: TravelSlots) -> Dict[str, Any]:
    """Convert TravelSlots dataclass to plain dict for JSON serialisation."""
    return {
        "destination":     slots.destination,
        "start_date":      slots.start_date,
        "end_date":        slots.end_date,
        "duration_days":   slots.duration_days,
        "budget":          slots.budget,
        "budget_currency": slots.budget_currency,
        "interests":       slots.interests,
        "travel_style":    slots.travel_style,
        "group_size":      slots.group_size,
        "language":        slots.language,
    }
