"""Real integration test runner for the Travel Buddy AI stack.

This script is designed for real service validation rather than unit testing.
It can:

1. Measure local-model slot extraction latency and output quality.
2. Measure Gemini itinerary and cost generation latency and reliability.
3. Exercise the service-layer bundle with real network calls.
4. Run repeated requests to estimate stability over multiple attempts.
5. Run a forced-fallback smoke check to confirm service orchestration.

Usage examples:

    python listings/ai/integration_test.py --scenario all
    python listings/ai/integration_test.py --scenario local --repeat 5
    python listings/ai/integration_test.py --scenario gemini --repeat 3
    python listings/ai/integration_test.py --scenario bundle
    python listings/ai/integration_test.py --scenario fallback
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import statistics
import time
from dataclasses import asdict
from typing import Any, Callable, Dict, List
from unittest.mock import patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from listings.ai.gemini import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GeminiAuthError,
    gemini_generate_cost_estimate,
    gemini_generate_itinerary,
)
from listings.ai.local_llm import LOCAL_LLM_MODEL, get_local_llm_client, extract_slots
from listings.ai.prompt import TravelSlots
from listings.ai.service import generate_trip_bundle


DEFAULT_PROMPTS = [
    "Plan a 4 day budget trip to Tokyo from 2026-07-01 to 2026-07-05 focused on food and anime.",
    "Create a 5 day moderate trip to Seoul from 2026-08-10 to 2026-08-15 with cafes, shopping, and nightlife.",
    "Estimate the cost for a 7 day relaxed trip to Paris for two travelers with museums and fine dining.",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real integration tests for the AI module.")
    parser.add_argument(
        "--scenario",
        choices=["all", "local", "gemini", "bundle", "fallback"],
        default="all",
        help="Which scenario to run.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="How many times to run each prompt.",
    )
    parser.add_argument(
        "--prompt",
        action="append",
        dest="prompts",
        help="Optional custom prompt. Repeat this flag to add multiple prompts.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the final report as JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prompts = args.prompts or DEFAULT_PROMPTS
    report: Dict[str, Any] = {
        "scenario": args.scenario,
        "repeat": args.repeat,
        "prompts": prompts,
        "environment": environment_snapshot(),
        "results": {},
    }

    if args.scenario in {"all", "local"}:
        report["results"]["local"] = run_repeated(prompts, args.repeat, run_local_checks)

    if args.scenario in {"all", "gemini"}:
        report["results"]["gemini"] = run_repeated(prompts, args.repeat, run_gemini_checks)

    if args.scenario in {"all", "bundle"}:
        report["results"]["bundle"] = run_repeated(prompts, args.repeat, run_bundle_checks)

    if args.scenario in {"all", "fallback"}:
        report["results"]["fallback"] = run_fallback_smoke(prompts[0])

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_human_report(report)


def environment_snapshot() -> Dict[str, Any]:
    local_client = get_local_llm_client()
    local_model_ready = False
    try:
        local_model_ready = local_client.is_alive()
    except Exception:
        local_model_ready = False

    gemini_configured = bool(GEMINI_API_KEY)
    return {
        "local_llm_model": LOCAL_LLM_MODEL,
        "local_model_ready": local_model_ready,
        "gemini_configured": gemini_configured,
    }


def run_repeated(
    prompts: List[str],
    repeat: int,
    runner: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any]:
    attempts: List[Dict[str, Any]] = []
    for prompt in prompts:
        for index in range(repeat):
            result = runner(prompt)
            result["attempt_index"] = index + 1
            result["prompt"] = prompt
            attempts.append(result)

    latencies = [item["latency_seconds"] for item in attempts if item.get("latency_seconds") is not None]
    success_count = sum(1 for item in attempts if item.get("success"))

    return {
        "attempts": attempts,
        "summary": {
            "total_attempts": len(attempts),
            "success_count": success_count,
            "failure_count": len(attempts) - success_count,
            "success_rate": round(success_count / len(attempts), 3) if attempts else 0.0,
            "min_latency_seconds": min(latencies) if latencies else None,
            "avg_latency_seconds": round(statistics.mean(latencies), 3) if latencies else None,
            "max_latency_seconds": max(latencies) if latencies else None,
        },
    }


def run_local_checks(prompt: str) -> Dict[str, Any]:
    started_at = time.perf_counter()
    try:
        slots = extract_slots(prompt)
        latency = time.perf_counter() - started_at
        return {
            "success": True,
            "latency_seconds": round(latency, 3),
            "slots": asdict(slots),
            "notes": validate_slot_quality(slots),
        }
    except Exception as exc:
        latency = time.perf_counter() - started_at
        return {
            "success": False,
            "latency_seconds": round(latency, 3),
            "error": str(exc),
        }


def run_gemini_checks(prompt: str) -> Dict[str, Any]:
    started_at = time.perf_counter()
    try:
        slots = extract_slots(prompt)
        itinerary = gemini_generate_itinerary(prompt, slots)
        cost_estimate = gemini_generate_cost_estimate(prompt, slots)
        latency = time.perf_counter() - started_at

        return {
            "success": itinerary["success"] and cost_estimate["success"],
            "latency_seconds": round(latency, 3),
            "slots": asdict(slots),
            "itinerary_source": itinerary["source"],
            "cost_source": cost_estimate["source"],
            "itinerary_preview": shorten(itinerary.get("result")),
            "cost_preview": shorten(cost_estimate.get("result")),
            "errors": [value for value in [itinerary.get("error"), cost_estimate.get("error")] if value],
        }
    except (GeminiAuthError, Exception) as exc:
        latency = time.perf_counter() - started_at
        return {
            "success": False,
            "latency_seconds": round(latency, 3),
            "error": str(exc),
        }


def run_bundle_checks(prompt: str) -> Dict[str, Any]:
    started_at = time.perf_counter()
    try:
        result = generate_trip_bundle(prompt)
        latency = time.perf_counter() - started_at
        return {
            "success": result["success"],
            "latency_seconds": round(latency, 3),
            "primary_source": result["primary_source"],
            "slots": result["slots"],
            "itinerary_source": result["itinerary"]["source"],
            "cost_source": result["cost_estimate"]["source"],
            "itinerary_preview": shorten(result["itinerary"].get("result")),
            "cost_preview": shorten(result["cost_estimate"].get("result")),
            "errors": result["errors"],
        }
    except Exception as exc:
        latency = time.perf_counter() - started_at
        return {
            "success": False,
            "latency_seconds": round(latency, 3),
            "error": str(exc),
        }


def run_fallback_smoke(prompt: str) -> Dict[str, Any]:
    """
    This smoke check intentionally forces the Gemini layer to fail so that
    the service bundle must rely on the local path or the static fallback.
    """
    started_at = time.perf_counter()

    def forced_failure(_: str, __: TravelSlots) -> Dict[str, Any]:
        return {
            "result": None,
            "source": "gemini_error",
            "success": False,
            "error": "Forced Gemini failure for fallback verification",
            "model": GEMINI_MODEL,
        }

    with patch("listings.ai.service.gemini_generate_itinerary", side_effect=forced_failure), patch(
        "listings.ai.service.gemini_generate_cost_estimate", side_effect=forced_failure
    ):
        result = generate_trip_bundle(prompt)

    latency = time.perf_counter() - started_at
    return {
        "success": result["success"],
        "latency_seconds": round(latency, 3),
        "primary_source": result["primary_source"],
        "itinerary_source": result["itinerary"]["source"],
        "cost_source": result["cost_estimate"]["source"],
        "errors": result["errors"],
        "slots": result["slots"],
    }


def validate_slot_quality(slots: TravelSlots) -> List[str]:
    notes: List[str] = []
    destination = str(slots.destination).strip() if slots.destination is not None else ""
    interests = str(slots.interests).strip() if slots.interests is not None else ""

    if not destination or destination in {"unknown destination", "your destination"}:
        notes.append("Destination looks weak or generic.")
    if slots.start_date == "unspecified" or slots.end_date == "unspecified":
        notes.append("Dates were not fully extracted.")
    if not interests or interests == "general sightseeing":
        notes.append("Interests stayed generic.")
    if not notes:
        notes.append("Slot extraction looks usable.")
    return notes


def shorten(value: Any, limit: int = 180) -> str | None:
    if not value:
        return None
    text = str(value).strip().replace("\n", " ")
    return text if len(text) <= limit else f"{text[:limit].rstrip()}..."


def print_human_report(report: Dict[str, Any]) -> None:
    print("=== AI Integration Test Report ===")
    print(f"Scenario: {report['scenario']}")
    print(f"Repeat: {report['repeat']}")
    print("Environment:")
    for key, value in report["environment"].items():
        print(f"  - {key}: {value}")

    for section, payload in report["results"].items():
        print(f"\n--- {section.upper()} ---")
        if section == "fallback":
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            continue

        summary = payload["summary"]
        print(
            "Summary: "
            f"success_rate={summary['success_rate']} "
            f"avg_latency={summary['avg_latency_seconds']}s "
            f"failures={summary['failure_count']}"
        )
        for attempt in payload["attempts"]:
            status = "OK" if attempt["success"] else "FAIL"
            print(
                f"[{status}] attempt={attempt['attempt_index']} "
                f"latency={attempt['latency_seconds']}s "
                f"prompt={shorten(attempt['prompt'], 70)}"
            )
            if attempt.get("error"):
                print(f"      error={attempt['error']}")
            if attempt.get("errors"):
                print(f"      errors={attempt['errors']}")
            if attempt.get("slots"):
                print(f"      destination={attempt['slots'].get('destination')}")
            if attempt.get("notes"):
                print(f"      notes={attempt['notes']}")
            if attempt.get("itinerary_source"):
                print(
                    f"      itinerary_source={attempt['itinerary_source']} "
                    f"cost_source={attempt.get('cost_source')}"
                )


if __name__ == "__main__":
    main()
