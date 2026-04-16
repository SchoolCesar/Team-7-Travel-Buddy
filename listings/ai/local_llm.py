"""
Local description generation entrypoint for Harbor.

Compatibility note:
- The view currently imports `generate_listing_description` from this module.
- We keep that API stable, but internally route to the lightweight
  semantic retrieval engine (no LLM, no transformers model loading).
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Optional

import bleach

from .description_retriever import DescriptionRetriever


logger = logging.getLogger(__name__)

# Safety constants
MAX_INPUT_LENGTH = 500
BLOCKED_PATTERNS = [
    r"<script.*?>",
    r"DROP\s+TABLE",
    r"eval\s*\(",
]

DEFAULT_UNSAFE_FALLBACK = (
    "{category} listing available at ${price}. Contact for details and availability."
)


def sanitize_input(text: str, max_length: int = MAX_INPUT_LENGTH) -> str:
    """
    Normalize and trim user input before retrieval.
    """
    clean = bleach.clean(text, strip=True)
    clean = " ".join(clean.split())
    return clean[:max_length].strip()


def is_safe_input(text: str) -> bool:
    """
    Block obvious malicious patterns before processing.
    """
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False
    return True


def validate_output(text: str) -> bool:
    """
    Ensure generated description is usable for listing creation.
    """
    if len(text) < 60 or len(text) > 1000:
        return False
    sentences = [segment.strip() for segment in text.split(".") if segment.strip()]
    return len(sentences) >= 2


_retriever: Optional[DescriptionRetriever] = None


def get_description_retriever() -> DescriptionRetriever:
    """
    Lazy-init singleton retriever for low per-request latency.
    """
    global _retriever
    if _retriever is None:
        _retriever = DescriptionRetriever(confidence_threshold=0.10)
    return _retriever


def _build_retrieval_input(title: str, category: str, price: float, basic_info: str) -> str:
    """
    Build a compact but context-rich query for semantic matching.
    """
    try:
        numeric_price = float(price)
        price_text = f"${numeric_price:.2f}"
    except (TypeError, ValueError):
        price_text = "a fair price"
    return (
        f"Title: {title}. "
        f"Category: {category}. "
        f"Price: {price_text}. "
        f"Details: {basic_info}"
    )


def _safe_fallback(category: str, price: float, basic_info: str) -> str:
    """
    Deterministic fallback used for unsafe/error cases.
    """
    details_preview = basic_info[:120].rstrip() if basic_info else "Flexible details available"
    try:
        numeric_price = float(price)
    except (TypeError, ValueError):
        numeric_price = 0.0
    base = DEFAULT_UNSAFE_FALLBACK.format(category=category, price=f"{numeric_price:.2f}")
    return f"{base} {details_preview}. Message for quick coordination."


def generate_listing_description(title: str, category: str, price: float, basic_info: str) -> Dict[str, object]:
    """
    Generate a marketplace-ready description using semantic retrieval.

    Returns:
        dict with keys:
        - description (str)
        - source (str)
        - success (bool)
        - error (str | None)
        - confidence_score (float)
    """
    # Sanitize user-controlled inputs.
    title = sanitize_input(title, 100)
    category = sanitize_input(category, 80)
    basic_info = sanitize_input(basic_info, 500)

    # Safety gate.
    if not is_safe_input(title) or not is_safe_input(basic_info):
        return {
            "description": _safe_fallback(category=category or "General", price=price or 0.0, basic_info=basic_info),
            "source": "blocked_input_fallback",
            "success": False,
            "error": "Unsafe input detected",
            "confidence_score": 0.0,
        }

    retrieval_input = _build_retrieval_input(
        title=title,
        category=category or "General",
        price=price or 0.0,
        basic_info=basic_info,
    )

    try:
        retriever = get_description_retriever()
        result = retriever.generate_description(retrieval_input)

        description = str(result.get("description", "")).strip()
        if not validate_output(description):
            logger.warning("Retriever output failed quality validation; applying deterministic fallback")
            return {
                "description": _safe_fallback(
                    category=category or "General",
                    price=price or 0.0,
                    basic_info=basic_info,
                ),
                "source": "quality_fallback",
                "success": True,
                "error": None,
                "confidence_score": float(result.get("confidence_score", 0.0)),
            }

        return {
            "description": description,
            "source": str(result.get("source", "semantic_retrieval")),
            "success": True,
            "error": result.get("error"),
            "confidence_score": float(result.get("confidence_score", 0.0)),
        }
    except Exception as exc:
        logger.exception("Description generation failed")
        return {
            "description": _safe_fallback(category=category or "General", price=price or 0.0, basic_info=basic_info),
            "source": "error_fallback",
            "success": False,
            "error": str(exc),
            "confidence_score": 0.0,
        }
