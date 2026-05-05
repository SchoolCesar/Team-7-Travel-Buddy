"""
TravelBuddy – Local LLM client backed by Hugging Face Transformers.

Primary model:
    stabilityai/stablelm-2-zephyr-1_6b

Responsibilities:
  1. Slot extraction from raw user text.
  2. Lightweight itinerary / cost draft as fallback when Gemini is unavailable.
  3. Simple buddy match blurb generation.

Environment variables:
    LOCAL_LLM_MODEL      = stabilityai/stablelm-2-zephyr-1_6b   (default)
    LOCAL_LLM_DEVICE     = auto                                 (default)
    LOCAL_LLM_TIMEOUT    = 30                                   (kept for compatibility)
    LOCAL_LLM_MAX_TOKENS = 1024                                 (default)

Legacy environment variables OLLAMA_MODEL / OLLAMA_TIMEOUT are still
accepted as fallback config keys to reduce migration friction.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import date
from typing import Any, Dict, Optional

try:
    from decouple import config as decouple_config
except ImportError:  # pragma: no cover - environment-dependent import
    decouple_config = None

try:
    import torch
except ImportError:  # pragma: no cover - environment-dependent import
    torch = None

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError:  # pragma: no cover - environment-dependent import
    AutoModelForCausalLM = None
    AutoTokenizer = None

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


LOCAL_LLM_MODEL: str = _get_setting("LOCAL_LLM_MODEL", "", cast=str) or _get_setting(
    "OLLAMA_MODEL",
    "stabilityai/stablelm-2-zephyr-1_6b",
    cast=str,
)
LOCAL_LLM_DEVICE: str = _get_setting("LOCAL_LLM_DEVICE", "auto", cast=str)
LOCAL_LLM_TIMEOUT: int = _get_setting("LOCAL_LLM_TIMEOUT", _get_setting("OLLAMA_TIMEOUT", 30, cast=int), cast=int)
LOCAL_LLM_MAX_TOKENS: int = _get_setting("LOCAL_LLM_MAX_TOKENS", 1024, cast=int)

_SLOT_DEFAULTS: Dict[str, Any] = {
    "destination": None,
    "start_date": None,
    "end_date": None,
    "duration_days": 3,
    "budget": "moderate",
    "budget_currency": "USD",
    "interests": "general sightseeing",
    "travel_style": "balanced",
    "group_size": 1,
    "language": "en",
}


# ─────────────────────────────────────────────
# Low-level local model client
# ─────────────────────────────────────────────

class LocalLLMUnavailableError(RuntimeError):
    """Raised when the local Hugging Face model cannot be loaded or used."""


# Backward compatibility for older imports and tests.
OllamaUnavailableError = LocalLLMUnavailableError


class LocalTransformersClient:
    """
    Thin wrapper around a local Hugging Face chat model.

    StableLM 2 Zephyr 1.6B exposes a chat template through the tokenizer,
    so we can format system and user turns directly and run local generation.
    """

    def __init__(
        self,
        model_name: str = LOCAL_LLM_MODEL,
        device: str = LOCAL_LLM_DEVICE,
        timeout: int = LOCAL_LLM_TIMEOUT,
        max_tokens: int = LOCAL_LLM_MAX_TOKENS,
    ):
        self.model_name = model_name
        self.device_preference = device
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._model = None
        self._tokenizer = None
        self._device = None
        self._lock = threading.Lock()

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """
        Generate a chat completion from the local model.
        """
        model, tokenizer, device = self._ensure_loaded()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            encoded = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_tensors="pt",
                return_dict=True,
            )
            if hasattr(encoded, "to"):
                encoded = encoded.to(device)

            input_ids = encoded["input_ids"]
            attention_mask = encoded.get("attention_mask")
            if attention_mask is None:
                attention_mask = torch.ones_like(input_ids, device=device)

            do_sample = temperature > 0
            generation_kwargs = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "max_new_tokens": max_tokens,
                "pad_token_id": tokenizer.eos_token_id,
                "eos_token_id": tokenizer.eos_token_id,
                "do_sample": do_sample,
            }
            if do_sample:
                generation_kwargs["temperature"] = max(temperature, 1e-5)
                generation_kwargs["top_p"] = 0.95

            with self._lock:
                with torch.inference_mode():
                    output = model.generate(**generation_kwargs)

            generated_tokens = output[0][input_ids.shape[-1]:]
            return tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()

        except Exception as exc:
            raise LocalLLMUnavailableError(
                f"Local model generation failed for {self.model_name}: {exc}"
            ) from exc

    def is_alive(self) -> bool:
        """Return True when the local model can be loaded."""
        try:
            self._ensure_loaded()
            return True
        except Exception:
            return False

    def _ensure_loaded(self):
        if self._model is not None and self._tokenizer is not None and self._device is not None:
            return self._model, self._tokenizer, self._device

        if torch is None or AutoTokenizer is None or AutoModelForCausalLM is None:
            raise LocalLLMUnavailableError(
                "Local LLM dependencies are missing. Install torch and transformers to use "
                f"{self.model_name}."
            )

        try:
            tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True,
            )

            if tokenizer.pad_token_id is None:
                tokenizer.pad_token = tokenizer.eos_token

            device = self._resolve_device()
            dtype = self._resolve_dtype(device)

            model_kwargs = {"trust_remote_code": True}
            if dtype is not None:
                model_kwargs["dtype"] = dtype

            model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                **model_kwargs,
            )
            model.to(device)
            model.eval()

            self._model = model
            self._tokenizer = tokenizer
            self._device = device
            logger.info("Loaded local LLM model %s on %s", self.model_name, device)
            return model, tokenizer, device

        except Exception as exc:
            raise LocalLLMUnavailableError(
                f"Could not load local model {self.model_name}: {exc}"
            ) from exc

    def _resolve_device(self) -> str:
        if torch is None:
            return "cpu"
        if self.device_preference and self.device_preference != "auto":
            return self.device_preference
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def _resolve_dtype(device: str):
        if torch is None:
            return None
        if device in {"cuda", "mps"}:
            return torch.float16
        return torch.float32


# ─────────────────────────────────────────────
# Singleton client
# ─────────────────────────────────────────────

_client: Optional[LocalTransformersClient] = None


def get_local_llm_client() -> LocalTransformersClient:
    global _client
    if _client is None:
        _client = LocalTransformersClient()
    return _client


# Backward compatibility for older imports and integration helpers.
def get_ollama_client() -> LocalTransformersClient:
    return get_local_llm_client()


# ─────────────────────────────────────────────
# Slot extraction
# ─────────────────────────────────────────────

def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` markdown fences."""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "")
    return text.strip()


def extract_slots(raw_input: str) -> TravelSlots:
    """
    Parse natural-language travel input into structured TravelSlots.
    Falls back to regex extraction whenever the local model fails.
    """
    system_prompt, user_prompt = PromptBuilder.slot_extraction(raw_input)

    try:
        client = get_local_llm_client()
        raw_json = client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=256,
        )

        cleaned = _strip_json_fences(raw_json)
        parsed: Dict[str, Any] = json.loads(cleaned)
        normalized = _normalize_slot_payload(parsed)
        merged = {**_SLOT_DEFAULTS, **{k: v for k, v in normalized.items() if v is not None}}

        if merged.get("duration_days") is None and merged.get("start_date") and merged.get("end_date"):
            try:
                delta = date.fromisoformat(merged["end_date"]) - date.fromisoformat(merged["start_date"])
                merged["duration_days"] = max(1, delta.days)
            except ValueError:
                merged["duration_days"] = _SLOT_DEFAULTS["duration_days"]

        return TravelSlots(**{k: merged[k] for k in TravelSlots.__dataclass_fields__})  # type: ignore[attr-defined]

    except LocalLLMUnavailableError:
        logger.warning("Local model unavailable – using regex-based slot extraction fallback")
        return _regex_extract_slots(raw_input)

    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("Slot extraction JSON parse failed: %s", exc)
        return _regex_extract_slots(raw_input)


def _normalize_slot_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Coerce loosely-structured model JSON into the TravelSlots schema.

    Local models often return lists, numeric strings, or extra whitespace even
    when prompted for a strict schema. This helper normalizes the common cases
    before we build the dataclass.
    """
    normalized: Dict[str, Any] = {}

    for key in TravelSlots.__dataclass_fields__:
        normalized[key] = payload.get(key)

    normalized["destination"] = _coerce_string(normalized.get("destination"))
    normalized["start_date"] = _coerce_date_string(normalized.get("start_date"))
    normalized["end_date"] = _coerce_date_string(normalized.get("end_date"))
    normalized["budget"] = _coerce_string(normalized.get("budget"))
    normalized["budget_currency"] = _coerce_currency(normalized.get("budget_currency"))
    normalized["interests"] = _coerce_interests(normalized.get("interests"))
    normalized["travel_style"] = _coerce_travel_style(normalized.get("travel_style"))
    normalized["group_size"] = _coerce_int(normalized.get("group_size"))
    normalized["duration_days"] = _coerce_int(normalized.get("duration_days"))
    normalized["language"] = _coerce_language(normalized.get("language"))

    return normalized


def _coerce_first_scalar(value: Any) -> Any:
    while isinstance(value, list) and value:
        value = value[0]
    return value


def _coerce_string(value: Any) -> Optional[str]:
    value = _coerce_first_scalar(value)
    if value is None:
        return None
    if isinstance(value, dict):
        return None
    text = str(value).strip()
    return text or None


def _coerce_date_string(value: Any) -> Optional[str]:
    text = _coerce_string(value)
    if not text:
        return None
    return _normalize_date_string(text)


def _coerce_int(value: Any) -> Optional[int]:
    value = _coerce_first_scalar(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _coerce_currency(value: Any) -> Optional[str]:
    text = _coerce_string(value)
    if not text:
        return None
    text = text.upper()
    if len(text) == 3 and text.isalpha():
        return text
    currency_aliases = {
        "USDOLLAR": "USD",
        "US DOLLAR": "USD",
        "DOLLAR": "USD",
        "EURO": "EUR",
        "YEN": "JPY",
        "POUND": "GBP",
    }
    return currency_aliases.get(text)


def _coerce_interests(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(parts) or None
    return _coerce_string(value)


def _coerce_travel_style(value: Any) -> Optional[str]:
    text = _coerce_string(value)
    if not text:
        return None
    text = text.lower()
    aliases = {
        "budget travel": "budget",
        "backpacking": "backpacking",
        "luxury travel": "luxury",
        "adventurous": "adventure",
        "relaxing": "relaxed",
        "balanced": "balanced",
    }
    if text in {"budget", "backpacking", "luxury", "adventure", "relaxed", "balanced"}:
        return text
    return aliases.get(text, text)


def _coerce_language(value: Any) -> Optional[str]:
    text = _coerce_string(value)
    if not text:
        return None
    text = text.lower()
    aliases = {
        "english": "en",
        "chinese": "zh",
        "japanese": "ja",
        "korean": "ko",
    }
    if len(text) == 2 and text.isalpha():
        return text
    return aliases.get(text)


def _regex_extract_slots(raw_input: str) -> TravelSlots:
    """
    Pure-regex fallback slot extractor (no model required).
    """
    text = raw_input.lower()

    dest_match = re.search(
        r"\b(?:in|to|visit|going to|travel to)\s+([a-zA-Z\u4e00-\u9fff][a-zA-Z\u4e00-\u9fff\s]{1,30}?)(?=\s+(?:on|from|for|with|and)\b|[,.]|$)",
        raw_input,
        re.IGNORECASE,
    )
    destination = dest_match.group(1).strip() if dest_match else None

    date_matches = re.findall(r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b", raw_input)
    start_date = _normalize_date_string(date_matches[0]) if len(date_matches) >= 1 else None
    end_date = _normalize_date_string(date_matches[1]) if len(date_matches) >= 2 else None

    dur_match = re.search(r"(\d+)\s*(?:day|days|天|日)", text)
    duration_days = int(dur_match.group(1)) if dur_match else None

    if any(word in text for word in ["budget", "cheap", "affordable", "low-cost", "低预算", "便宜", "节省"]):
        travel_style = "budget"
        budget = "low"
    elif any(word in text for word in ["luxury", "premium", "high-end", "奢华", "豪华", "高端"]):
        travel_style = "luxury"
        budget = "high"
    elif any(word in text for word in ["adventure", "hiking", "backpack", "冒险", "徒步"]):
        travel_style = "adventure"
        budget = "moderate"
    else:
        travel_style = "relaxed"
        budget = "moderate"

    has_cjk = bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", raw_input))
    language = "zh" if has_cjk else "en"

    if duration_days is None and start_date and end_date:
        try:
            duration_days = max(1, (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days)
        except ValueError:
            duration_days = 3

    budget_currency = "USD"
    if "€" in raw_input or "eur" in text:
        budget_currency = "EUR"
    elif "¥" in raw_input or "jpy" in text or "yen" in text:
        budget_currency = "JPY"
    elif "£" in raw_input or "gbp" in text:
        budget_currency = "GBP"

    return TravelSlots(
        destination=destination or "your destination",
        start_date=start_date or "unspecified",
        end_date=end_date or "unspecified",
        duration_days=duration_days or 3,
        budget=budget,
        budget_currency=budget_currency,
        travel_style=travel_style,
        language=language,
    )


def _normalize_date_string(raw_date: str) -> Optional[str]:
    normalized = raw_date.replace("/", "-")
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError:
        return None


# ─────────────────────────────────────────────
# Lightweight generation
# ─────────────────────────────────────────────

def local_generate_itinerary(raw_input: str, slots: TravelSlots) -> Dict[str, Any]:
    """
    Generate a travel itinerary using the local Hugging Face model.
    Called as fallback when Gemini is unavailable.
    """
    system_prompt, user_prompt = PromptBuilder.itinerary(raw_input, slots)

    try:
        client = get_local_llm_client()
        text = client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            max_tokens=1500,
        )
        return {
            "result": text,
            "source": "local_llm",
            "success": True,
            "error": None,
            "model": client.model_name,
        }

    except LocalLLMUnavailableError as exc:
        logger.warning("Local LLM unavailable for itinerary: %s", exc)
        return {
            "result": _static_itinerary_fallback(slots),
            "source": "static_fallback",
            "success": True,
            "error": str(exc),
            "model": LOCAL_LLM_MODEL,
        }


def local_generate_cost_estimate(raw_input: str, slots: TravelSlots) -> Dict[str, Any]:
    """
    Generate a cost estimate using the local Hugging Face model.
    Called as fallback when Gemini is unavailable.
    """
    system_prompt, user_prompt = PromptBuilder.cost_estimate(raw_input, slots)

    try:
        client = get_local_llm_client()
        text = client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=800,
        )
        return {
            "result": text,
            "source": "local_llm",
            "success": True,
            "error": None,
            "model": client.model_name,
        }

    except LocalLLMUnavailableError as exc:
        return {
            "result": _static_cost_fallback(slots),
            "source": "static_fallback",
            "success": True,
            "error": str(exc),
            "model": LOCAL_LLM_MODEL,
        }


def local_generate_buddy_match_blurb(
    plan_a: Dict[str, Any],
    plan_b: Dict[str, Any],
    score: float,
) -> Dict[str, Any]:
    """Generate a buddy match explanation using the local Hugging Face model."""
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
        client = get_local_llm_client()
        text = client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.6,
            max_tokens=300,
        )
        return {
            "result": text,
            "source": "local_llm",
            "success": True,
            "error": None,
            "model": client.model_name,
        }

    except LocalLLMUnavailableError as exc:
        return {
            "result": _static_buddy_fallback(plan_a, plan_b, score),
            "source": "static_fallback",
            "success": True,
            "error": str(exc),
            "model": LOCAL_LLM_MODEL,
        }


# ─────────────────────────────────────────────
# Static fallbacks
# ─────────────────────────────────────────────

def _static_itinerary_fallback(slots: TravelSlots) -> str:
    return f"""
## {slots.duration_days}-Day Trip to {slots.destination}

**Day 1** – Arrival & orientation
- Morning: Arrive and check in to accommodation
- Afternoon: Explore the city centre / local neighbourhood
- Evening: Try local street food

**Day 2** – Main attractions
- Morning: Visit top landmarks
- Afternoon: Cultural or outdoor activities based on interests ({slots.interests})
- Evening: Local restaurant dinner

**Day 3+** – Free exploration
- Tailor remaining days to your {slots.travel_style} travel style
- Budget range: {slots.budget} ({slots.budget_currency})

*(This is a general template. Full AI generation is currently unavailable.)*
""".strip()


def _static_cost_fallback(slots: TravelSlots) -> str:
    return f"""
## Estimated Costs for {slots.destination} ({slots.duration_days} days, {slots.group_size} person)

| Category       | Estimate              |
|----------------|----------------------|
| Flights        | Varies by origin     |
| Accommodation  | Depends on style     |
| Food           | ~$30–80/day          |
| Local transport| ~$10–25/day          |
| Activities     | ~$20–60/day          |
| Miscellaneous  | ~$15–30/day          |

*(Full AI cost estimation is currently unavailable. Figures are rough global averages.)*
""".strip()


def _static_buddy_fallback(plan_a: Dict[str, Any], plan_b: Dict[str, Any], score: float) -> str:
    dest_a = plan_a.get("destination", "a destination")
    dest_b = plan_b.get("destination", "a destination")
    return (
        f"You and your potential travel buddy are both interested in visiting {dest_a} / {dest_b}. "
        f"Your compatibility score is {score:.0%}. "
        "Reach out and introduce yourself – shared travel experiences start with a conversation!"
    )
