"""
TravelBuddy – Gemini 2.5 Flash API client.

This is the primary AI engine for high-quality generation.
The local Hugging Face model acts as fallback when this is unavailable.

Environment variables (set in Django settings or .env):
    GEMINI_API_KEY        = api-key   (required)
    GEMINI_MODEL          = gemini-2.5-flash  (default)
    GEMINI_TIMEOUT        = 60               (seconds)
    GEMINI_MAX_TOKENS     = 2048             (default)

Get your API key at: https://aistudio.google.com/app/apikey
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

import httpx

try:
    from decouple import config as decouple_config
except ImportError:  # pragma: no cover - environment-dependent import
    decouple_config = None

from .prompt import PromptBuilder, TravelSlots

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

def _get_setting(name: str, default: Any, cast=None):
    env_value = os.getenv(name)
    if env_value not in (None, ""):
        return cast(env_value) if cast else env_value
    if decouple_config is not None:
        return decouple_config(name, default=default, cast=cast)
    return default


GEMINI_API_KEY: str = _get_setting("GEMINI_API_KEY", "", cast=str)
GEMINI_MODEL: str = _get_setting("GEMINI_MODEL", "gemini-2.5-flash", cast=str)
GEMINI_TIMEOUT: int = _get_setting("GEMINI_TIMEOUT", 60, cast=int)
GEMINI_MAX_TOKENS: int = _get_setting("GEMINI_MAX_TOKENS", 2048, cast=int)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


# ─────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────

class GeminiUnavailableError(RuntimeError):
    """Raised when the Gemini API is unreachable or returns an error."""

class GeminiAuthError(RuntimeError):
    """Raised when the API key is missing or invalid."""


# ─────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────

class GeminiClient:
    """
    Thin wrapper around the Gemini REST API (generateContent endpoint).

    Gemini doesn't have a separate system role in the same way as OpenAI,
    so we prefix the system prompt as the first user turn with a model
    acknowledgment, following Google's recommended pattern.
    """

    def __init__(
        self,
        api_key: str = GEMINI_API_KEY,
        model: str = GEMINI_MODEL,
        timeout: int = GEMINI_TIMEOUT,
        max_tokens: int = GEMINI_MAX_TOKENS,
    ):
        if not api_key:
            raise GeminiAuthError(
                "GEMINI_API_KEY environment variable is not set. "
                "Get a key at https://aistudio.google.com/app/apikey"
            )
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def _endpoint(self) -> str:
        return f"{_GEMINI_BASE}/{self.model}:generateContent?key={self.api_key}"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> str:
        """
        Call Gemini and return the generated text.
        Raises GeminiUnavailableError or GeminiAuthError on failure.
        """
        # Gemini uses a "system_instruction" field (available in v1beta)
        payload: Dict[str, Any] = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": self.max_tokens,
                "candidateCount": 1,
            },
        }

        try:
            resp = httpx.post(
                self._endpoint(),
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code == 401:
                raise GeminiAuthError("Gemini API key is invalid or expired.")

            resp.raise_for_status()
            data = resp.json()

            # Extract text from response
            candidates = data.get("candidates", [])
            if not candidates:
                raise GeminiUnavailableError("Gemini returned no candidates.")

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise GeminiUnavailableError("Gemini returned empty content parts.")

            return parts[0].get("text", "").strip()

        except httpx.ConnectError as exc:
            raise GeminiUnavailableError("Cannot reach Gemini API.") from exc
        except httpx.TimeoutException as exc:
            raise GeminiUnavailableError(f"Gemini API timed out after {self.timeout}s.") from exc
        except httpx.HTTPStatusError as exc:
            raise GeminiUnavailableError(
                f"Gemini API HTTP error {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc


# ─────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────

_gemini_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client


# ─────────────────────────────────────────────
# Feature functions
# ─────────────────────────────────────────────

def gemini_generate_itinerary(
    raw_input: str,
    slots: TravelSlots,
) -> Dict[str, Any]:
    """
    Generate a detailed day-by-day travel itinerary via Gemini 2.5 Flash.

    Returns:
        {
            "result": str,          # the itinerary text
            "source": str,          # "gemini"
            "success": bool,
            "error": str | None,
            "model": str,
        }
    """
    system_prompt, user_prompt = PromptBuilder.itinerary(raw_input, slots)

    try:
        client = get_gemini_client()
        text = client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
        )
        return {
            "result": text,
            "source": "gemini",
            "success": True,
            "error": None,
            "model": client.model,
        }

    except GeminiAuthError as exc:
        logger.error("Gemini auth error: %s", exc)
        return _gemini_error_response(str(exc))

    except GeminiUnavailableError as exc:
        logger.warning("Gemini unavailable for itinerary: %s", exc)
        return _gemini_error_response(str(exc))

    except Exception as exc:
        logger.exception("Unexpected Gemini error")
        return _gemini_error_response(str(exc))


def gemini_generate_cost_estimate(
    raw_input: str,
    slots: TravelSlots,
) -> Dict[str, Any]:
    """
    Generate a detailed cost breakdown via Gemini 2.5 Flash.
    """
    system_prompt, user_prompt = PromptBuilder.cost_estimate(raw_input, slots)

    try:
        client = get_gemini_client()
        text = client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,   # lower temp for more consistent numbers
        )
        return {
            "result": text,
            "source": "gemini",
            "success": True,
            "error": None,
            "model": client.model,
        }

    except (GeminiAuthError, GeminiUnavailableError, Exception) as exc:
        logger.warning("Gemini cost estimate failed: %s", exc)
        return _gemini_error_response(str(exc))


def gemini_generate_buddy_match(
    plan_a: Dict[str, Any],
    plan_b: Dict[str, Any],
    score: float,
) -> Dict[str, Any]:
    """
    Generate a buddy match explanation via Gemini 2.5 Flash.
    """
    system_prompt, user_prompt = PromptBuilder.buddy_match(
        dest_a=plan_a.get("destination", "unknown"),
        dates_a=f"{plan_a.get('start_date')} → {plan_a.get('end_date')}",
        style_a=plan_a.get("travel_style", "balanced"),
        interests_a=plan_a.get("interests", "general travel"),
        dest_b=plan_b.get("destination", "unknown"),
        dates_b=f"{plan_b.get('start_date')} → {plan_b.get('end_date')}",
        style_b=plan_b.get("travel_style", "balanced"),
        interests_b=plan_b.get("interests", "general travel"),
        score=score,
    )

    try:
        client = get_gemini_client()
        text = client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.6,
        )
        return {
            "result": text,
            "source": "gemini",
            "success": True,
            "error": None,
            "model": client.model,
        }

    except (GeminiAuthError, GeminiUnavailableError, Exception) as exc:
        logger.warning("Gemini buddy match failed: %s", exc)
        return _gemini_error_response(str(exc))


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _gemini_error_response(error: str) -> Dict[str, Any]:
    return {
        "result": None,
        "source": "gemini_error",
        "success": False,
        "error": error,
        "model": GEMINI_MODEL,
    }
