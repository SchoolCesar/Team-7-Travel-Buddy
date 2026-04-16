"""
Lightweight, non-LLM description generator.

This module replaces generation-heavy model inference with:
1) Semantic retrieval (TF-IDF + cosine similarity), and
2) Rule-based slot extraction + template substitution.

Design goals:
- Fast CPU-only runtime
- OOM-safe behavior
- Deterministic, production-friendly output
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


logger = logging.getLogger(__name__)

# Matches placeholders like {item_name} in templates.
PLACEHOLDER_PATTERN = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


@dataclass(frozen=True)
class TemplateRecord:
    """
    One retrieval template.

    template:
        Final rich description with placeholders.
    retrieval_text:
        Keyword-rich text used for vector matching.
    """

    template: str
    retrieval_text: str


class DescriptionRetriever:
    """
    Production-ready semantic retriever with rule-based substitution.

    Workflow:
    1) Build TF-IDF vectors over a template corpus (once at startup).
    2) Convert user input to a vector.
    3) Retrieve the highest cosine-similarity template.
    4) Extract key terms from messy input using regex + token rules.
    5) Fill placeholders safely.
    6) Fall back to a dynamic safe template when confidence is low.
    """

    DEFAULT_CONFIDENCE_THRESHOLD = 0.10

    def __init__(
        self,
        corpus: Optional[Sequence[TemplateRecord]] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        max_features: int = 4000,
    ) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")
        if max_features <= 0:
            raise ValueError("max_features must be a positive integer")

        self.confidence_threshold = confidence_threshold
        self.max_features = max_features
        self.default_slot_values = self._default_slot_values()
        self.dynamic_fallback_template = (
            "Offering a {condition} {item_name} at {price_anchor}. "
            "Great fit for {user_keyword} needs in {location}, with {benefit}. {cta}"
        )

        # Use provided corpus or the built-in 12-template corpus.
        self.corpus: List[TemplateRecord] = list(corpus) if corpus else self._default_corpus()
        self._validate_corpus(self.corpus)

        # Build vector index once for low-latency retrieval.
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            max_features=self.max_features,
            strip_accents="unicode",
            sublinear_tf=True,
        )
        self.template_matrix = self._build_template_matrix()

    @staticmethod
    def _default_slot_values() -> Dict[str, str]:
        """
        Baseline slot defaults used when extraction misses a field.
        """
        return {
            "item_name": "item",
            "user_keyword": "everyday use",
            "condition": "good",
            "price_anchor": "a fair price",
            "location": "the campus area",
            "benefit": "reliable value and convenience",
            "cta": "Message me for quick details and pickup options.",
        }

    @staticmethod
    def _default_corpus() -> List[TemplateRecord]:
        """
        Mock corpus (12 templates) with rich copy + placeholders.
        """
        return [
            TemplateRecord(
                template=(
                    "Upgrade your setup with this {condition} {item_name}. "
                    "Perfect for {user_keyword}, it offers {benefit} and is listed at {price_anchor}. "
                    "Easy handoff around {location}. {cta}"
                ),
                retrieval_text="laptop monitor tablet phone electronics charger gaming tech setup",
            ),
            TemplateRecord(
                template=(
                    "This {condition} {item_name} is ideal for anyone focused on {user_keyword}. "
                    "You get {benefit} without overpaying, with pricing at {price_anchor}. "
                    "Available near {location}. {cta}"
                ),
                retrieval_text="desk chair furniture apartment dorm storage shelf sofa table home",
            ),
            TemplateRecord(
                template=(
                    "Get ahead this term with this {condition} {item_name}. "
                    "Built for {user_keyword}, it supports {benefit} and is offered at {price_anchor}. "
                    "Meetup available in {location}. {cta}"
                ),
                retrieval_text="textbook notes class study exam school university college learning",
            ),
            TemplateRecord(
                template=(
                    "Commute smarter with this {condition} {item_name}. "
                    "Great for {user_keyword}, with {benefit} and an asking range of {price_anchor}. "
                    "Pickup can be arranged in {location}. {cta}"
                ),
                retrieval_text="bike bicycle scooter ride transport commuting campus wheels helmet",
            ),
            TemplateRecord(
                template=(
                    "Professional {item_name} now available for {user_keyword}. "
                    "Clients can expect {benefit}, delivered in {condition} service quality at {price_anchor}. "
                    "Serving the {location} area. {cta}"
                ),
                retrieval_text="tutoring mentor lessons coaching math coding writing language service",
            ),
            TemplateRecord(
                template=(
                    "Capture memorable moments with this {condition} {item_name} package. "
                    "Ideal for {user_keyword}, it includes {benefit} and starts at {price_anchor}. "
                    "Bookings open around {location}. {cta}"
                ),
                retrieval_text="photography videography portraits events camera graduation media shoot",
            ),
            TemplateRecord(
                template=(
                    "A well-kept {condition} {item_name} opportunity for {user_keyword}. "
                    "Includes {benefit} and competitive terms around {price_anchor}. "
                    "Located in {location}. {cta}"
                ),
                retrieval_text="sublease apartment housing room roommate utilities lease bedroom rental",
            ),
            TemplateRecord(
                template=(
                    "Dependable {item_name} support designed for {user_keyword}. "
                    "Expect {benefit} at {price_anchor}, delivered with {condition} professionalism. "
                    "Available throughout {location}. {cta}"
                ),
                retrieval_text="cleaning moving help delivery errands handyman setup assistance labor",
            ),
            TemplateRecord(
                template=(
                    "Thoughtfully made {condition} {item_name} for people who value {user_keyword}. "
                    "You will get {benefit} with straightforward pricing at {price_anchor}. "
                    "Local pickup near {location}. {cta}"
                ),
                retrieval_text="handmade crafts art jewelry custom gift design creative small business",
            ),
            TemplateRecord(
                template=(
                    "Reliable {condition} {item_name} care for busy schedules and {user_keyword}. "
                    "Service emphasizes {benefit} at {price_anchor}. "
                    "Flexible coverage in {location}. {cta}"
                ),
                retrieval_text="pet sitting dog walking cat care feeding boarding animal service",
            ),
            TemplateRecord(
                template=(
                    "Boost your routine with this {condition} {item_name} option tailored to {user_keyword}. "
                    "It delivers {benefit} and is competitively offered at {price_anchor}. "
                    "Conveniently available around {location}. {cta}"
                ),
                retrieval_text="fitness training yoga coaching wellness gym workout health sessions",
            ),
            TemplateRecord(
                template=(
                    "Fast, practical {item_name} help for {user_keyword}. "
                    "With {condition} standards and {benefit}, this option is available at {price_anchor}. "
                    "Support offered near {location}. {cta}"
                ),
                retrieval_text="computer repair setup wifi troubleshooting software install support tech help",
            ),
        ]

    @staticmethod
    def _validate_corpus(corpus: Sequence[TemplateRecord]) -> None:
        if len(corpus) < 10:
            raise ValueError("Corpus must contain at least 10 templates")
        for idx, record in enumerate(corpus):
            if not record.template.strip():
                raise ValueError(f"Template at index {idx} is empty")
            if not record.retrieval_text.strip():
                raise ValueError(f"Retrieval text at index {idx} is empty")

    def _build_template_matrix(self):
        """
        Fit the TF-IDF vectorizer over corpus retrieval text.
        """
        try:
            retrieval_docs = [record.retrieval_text for record in self.corpus]
            return self.vectorizer.fit_transform(retrieval_docs)
        except Exception as exc:
            logger.exception("Failed to build TF-IDF matrix")
            raise RuntimeError("Could not initialize retrieval index") from exc

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Basic text normalization that is deterministic and cheap.
        """
        text = text.strip().lower()
        text = re.sub(r"[^\w\s$.-]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _sanitize_slot_value(value: str) -> str:
        """
        Remove braces/newlines to avoid breaking placeholder formatting.
        """
        clean = value.replace("{", "").replace("}", "").replace("\n", " ")
        return re.sub(r"\s+", " ", clean).strip()

    @staticmethod
    def _extract_price(user_input: str) -> Optional[str]:
        """
        Extract price-like patterns such as:
        - "$120"
        - "for 120"
        - "asking 75"
        """
        patterns = [
            r"\$\s?(\d{1,6}(?:\.\d{1,2})?)",
            r"(?:for|asking|price|cost)\s+\$?(\d{1,6}(?:\.\d{1,2})?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                return f"${match.group(1)}"
        return None

    @staticmethod
    def _extract_condition(user_input: str) -> Optional[str]:
        """
        Detect condition words from most specific to least specific.
        """
        ordered_conditions = [
            "brand new",
            "like new",
            "open box",
            "refurbished",
            "excellent",
            "used",
            "good",
            "great",
            "fair",
        ]
        for condition in ordered_conditions:
            if condition in user_input:
                return condition
        return None

    @staticmethod
    def _extract_location(user_input: str) -> Optional[str]:
        """
        Capture location snippets like "near ISR", "in Champaign", etc.
        """
        # Prefer explicit location connectors that are usually geographic.
        patterns = [
            r"\bnear\s+([a-z0-9][a-z0-9\s-]{1,40}?)(?=(?:,|\.|;|!|\?|$))",
            r"\baround\s+([a-z0-9][a-z0-9\s-]{1,40}?)(?=(?:,|\.|;|!|\?|$))",
            r"\bat\s+([a-z0-9][a-z0-9\s-]{1,40}?)(?=(?:,|\.|;|!|\?|$))",
            r"\bin\s+([a-z0-9][a-z0-9\s-]{1,40}?)(?=(?:,|\.|;|!|\?|$))",
        ]

        disallowed_heads = {
            "evening",
            "evenings",
            "morning",
            "mornings",
            "night",
            "nights",
            "weekend",
            "weekends",
            "weekly",
            "session",
            "sessions",
            "hour",
            "hours",
        }

        for pattern in patterns:
            for match in re.finditer(pattern, user_input):
                candidate = match.group(1).strip(" ,.-")

                # Handle phrases like "the evenings in champaign" by taking the final location segment.
                if " in " in candidate:
                    tail = candidate.split(" in ")[-1].strip(" ,.-")
                    if tail:
                        candidate = tail

                candidate = re.sub(r"^(the|a|an)\s+", "", candidate).strip(" ,.-")
                head_token = candidate.split(" ")[0] if candidate else ""
                if head_token in disallowed_heads:
                    continue

                candidate = re.sub(
                    r"\b(?:for|with|and|but|if|because)\b.*$",
                    "",
                    candidate,
                ).strip(" ,.-")
                if candidate:
                    return candidate

        return None

    @staticmethod
    def _extract_item_name(user_input: str) -> Optional[str]:
        """
        Heuristic item/service extraction for messy short prompts.
        """
        labeled_title = re.search(r"\btitle\s*[:\-]\s*([a-z0-9][a-z0-9\s/&+-]{2,60})", user_input)
        if labeled_title:
            return DescriptionRetriever._clean_item_phrase(labeled_title.group(1))

        action_patterns = [
            r"(?:selling|offer(?:ing)?|listing|renting|subleasing|providing|need|looking for)\s+(?:a|an|the)?\s*([a-z0-9][a-z0-9\s/&+-]{2,45}?)(?=(?:,|\.|;|!|\?|$|\bfor\b|\bin\b|\bnear\b|\baround\b|\bat\b))",
            r"(?:have|got)\s+(?:a|an|the)?\s*([a-z0-9][a-z0-9\s/&+-]{2,45}?)(?=(?:,|\.|;|!|\?|$|\bfor\b|\bin\b|\bnear\b|\baround\b|\bat\b))",
        ]
        for pattern in action_patterns:
            match = re.search(pattern, user_input)
            if match:
                extracted = re.sub(
                    r"\b(?:for|near|in|around|at)\b.*$",
                    "",
                    match.group(1),
                ).strip(" ,.-")
                if extracted:
                    return DescriptionRetriever._clean_item_phrase(extracted)
        return None

    @staticmethod
    def _clean_item_phrase(phrase: str) -> str:
        """
        Remove noisy suffix words and keep item phrase concise.
        """
        phrase = re.sub(r"\s+", " ", phrase).strip(" ,.-")
        tokens = phrase.split()
        if not tokens:
            return phrase

        # Remove condition-like leading adjectives from the item phrase.
        leading_noise = {
            "used",
            "new",
            "brand",
            "like",
            "excellent",
            "great",
            "good",
            "fair",
            "open",
            "refurbished",
        }
        while tokens and tokens[0] in leading_noise:
            tokens.pop(0)
        if not tokens:
            return phrase

        # If we detect a strong product/service anchor, clip at it for cleaner naming.
        anchors = {
            "laptop",
            "monitor",
            "tablet",
            "phone",
            "desk",
            "chair",
            "bike",
            "scooter",
            "textbook",
            "tutoring",
            "coaching",
            "photography",
            "videography",
            "sublease",
            "apartment",
            "room",
            "service",
            "repair",
            "training",
            "yoga",
            "camera",
            "sofa",
            "table",
            "shelf",
            "dog",
            "cat",
            "pet",
        }
        for index, token in enumerate(tokens):
            if token in anchors:
                return " ".join(tokens[: index + 1])

        trailing_noise = {
            "good",
            "great",
            "cheap",
            "affordable",
            "negotiable",
            "obo",
            "condition",
            "cond",
            "evening",
            "evenings",
            "morning",
            "mornings",
            "weekend",
            "weekends",
            "today",
            "tomorrow",
        }
        while tokens and tokens[-1] in trailing_noise:
            tokens.pop()

        # Keep the output compact for readability in long templates.
        return " ".join(tokens[:4]) if tokens else phrase

    @staticmethod
    def _token_set(text: str) -> Set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    @staticmethod
    def _has_token_prefix(token_set: Set[str], prefixes: Tuple[str, ...]) -> bool:
        for token in token_set:
            for prefix in prefixes:
                if len(prefix) <= 3:
                    if token == prefix or token == f"{prefix}s":
                        return True
                elif token.startswith(prefix):
                    return True
        return False

    def _infer_user_keyword(self, normalized: str, keywords: List[str], item_name: str) -> str:
        """
        Produce a human-readable audience/use-case phrase.
        """
        tokens = self._token_set(normalized)

        if self._has_token_prefix(tokens, ("tutor", "lesson", "coach", "math", "physics", "class")):
            return "coursework and exam prep"
        if self._has_token_prefix(tokens, ("laptop", "phone", "tablet", "computer", "tech", "monitor")):
            return "study, work, and entertainment"
        if self._has_token_prefix(tokens, ("bike", "scooter", "commut", "transport")):
            return "daily commuting"
        if self._has_token_prefix(tokens, ("sublease", "apartment", "room", "housing")):
            return "comfortable everyday living"
        if self._has_token_prefix(tokens, ("photo", "video", "camera", "portrait")):
            return "events, portraits, and social content"
        if self._has_token_prefix(tokens, ("pet", "dog", "cat", "walk", "sitt")):
            return "busy pet-owner schedules"
        if self._has_token_prefix(tokens, ("fitness", "train", "workout", "yoga", "wellness")):
            return "consistent health and fitness goals"

        item_tokens = set(re.findall(r"[a-z0-9]+", item_name.lower()))
        for token in keywords:
            if token not in item_tokens:
                return token
        return self.default_slot_values["user_keyword"]

    def _extract_keywords(self, user_input: str) -> List[str]:
        """
        Lightweight keyword extractor using regex tokenization + stopwords.
        """
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "from",
            "have",
            "has",
            "will",
            "your",
            "you",
            "need",
            "want",
            "pls",
            "please",
            "just",
            "very",
            "good",
            "great",
            "new",
            "used",
            "like",
            "sale",
            "sell",
            "selling",
            "offer",
            "offering",
            "available",
            "only",
            "now",
            "today",
            "tomorrow",
            "soon",
            "title",
            "category",
            "details",
            "price",
            "usd",
        }
        tokens = re.findall(r"[a-z][a-z0-9+-]{2,}", user_input)
        keywords: List[str] = []
        for token in tokens:
            if token not in stopwords and token not in keywords:
                keywords.append(token)
            if len(keywords) == 6:
                break
        return keywords

    def _extract_slots(self, raw_input: str) -> Dict[str, str]:
        """
        Build placeholder values from messy user text.
        """
        normalized = self._normalize_text(raw_input)
        raw_lower = raw_input.strip().lower()
        keywords = self._extract_keywords(normalized)

        item_name = self._extract_item_name(raw_lower)
        if not item_name:
            item_name = " ".join(keywords[:2]) if keywords else self.default_slot_values["item_name"]

        user_keyword = self._infer_user_keyword(normalized, keywords, item_name)
        condition = self._extract_condition(normalized)
        domain_tokens = self._token_set(normalized)
        if not condition:
            if self._has_token_prefix(domain_tokens, ("sublease", "apartment", "room", "housing")):
                condition = "move-in-ready"
            elif self._has_token_prefix(domain_tokens, ("tutor", "lesson", "coach", "service")):
                condition = "professional"
            elif self._has_token_prefix(domain_tokens, ("laptop", "phone", "tablet", "bike", "scooter")):
                condition = "good"
            else:
                condition = self.default_slot_values["condition"]

        price_anchor = self._extract_price(normalized) or self.default_slot_values["price_anchor"]
        location = self._extract_location(raw_lower) or self.default_slot_values["location"]

        # Category-aware benefits keep the copy fluent and predictable.
        if self._has_token_prefix(domain_tokens, ("tutor", "lesson", "coach", "math", "physics")):
            benefit = "clear explanations, structured practice, and steady progress"
        elif self._has_token_prefix(domain_tokens, ("laptop", "phone", "tablet", "computer", "tech")):
            benefit = "reliable performance, responsive use, and day-to-day convenience"
        elif self._has_token_prefix(domain_tokens, ("bike", "scooter", "commut")):
            benefit = "easy mobility, dependable handling, and daily convenience"
        elif self._has_token_prefix(domain_tokens, ("sublease", "apartment", "room", "housing")):
            benefit = "comfort, practical space use, and convenient living"
        elif self._has_token_prefix(domain_tokens, ("photo", "video", "camera")):
            benefit = "creative direction, polished output, and timely delivery"
        elif len(keywords) >= 2:
            benefit = f"reliable {keywords[0]} quality and practical {keywords[1]} value"
        else:
            benefit = self.default_slot_values["benefit"]

        # Simple call-to-action can reference location when available.
        if location != self.default_slot_values["location"]:
            cta = f"Send a message to coordinate next steps near {location}."
        else:
            cta = "Send a message to coordinate next steps."

        return {
            "item_name": self._sanitize_slot_value(item_name),
            "user_keyword": self._sanitize_slot_value(user_keyword),
            "condition": self._sanitize_slot_value(condition),
            "price_anchor": self._sanitize_slot_value(price_anchor),
            "location": self._sanitize_slot_value(location),
            "benefit": self._sanitize_slot_value(benefit),
            "cta": self._sanitize_slot_value(cta),
        }

    def _retrieve(self, raw_input: str) -> Tuple[int, float]:
        """
        Return index + score for the highest-similarity template.
        """
        normalized = self._normalize_text(raw_input)
        if not normalized:
            raise ValueError("Input text is empty after normalization")

        try:
            query_vector = self.vectorizer.transform([normalized])
            scores = cosine_similarity(query_vector, self.template_matrix).ravel()
            best_index = int(np.argmax(scores))
            best_score = float(scores[best_index])
            return best_index, best_score
        except Exception as exc:
            logger.exception("Semantic retrieval failed")
            raise RuntimeError("Template retrieval failed") from exc

    def _safe_fill_template(self, template: str, slots: Dict[str, str]) -> str:
        """
        Fill placeholders while tolerating missing fields.
        """
        merged = dict(self.default_slot_values)
        merged.update(slots)

        def replace_match(match: re.Match[str]) -> str:
            placeholder = match.group(1)
            return merged.get(placeholder, f"<missing:{placeholder}>")

        filled = PLACEHOLDER_PATTERN.sub(replace_match, template)
        return re.sub(r"\s+", " ", filled).strip()

    def generate_description(self, user_input: str) -> Dict[str, Any]:
        """
        Public entry point.

        Returns:
            {
                "description": "...",
                "source": "semantic_retrieval" | "dynamic_fallback" | "error_fallback",
                "confidence_score": 0.0-1.0,
                "matched_template_index": int | None,
                "used_fallback": bool,
                "error": str | None,
            }
        """
        if not isinstance(user_input, str):
            raise TypeError("user_input must be a string")
        if not user_input.strip():
            raise ValueError("user_input cannot be empty")

        slots = self._extract_slots(user_input)

        try:
            best_index, best_score = self._retrieve(user_input)
            if best_score < self.confidence_threshold:
                logger.warning(
                    "Low-confidence retrieval (score=%.4f < threshold=%.4f). Falling back.",
                    best_score,
                    self.confidence_threshold,
                )
                description = self._safe_fill_template(self.dynamic_fallback_template, slots)
                return {
                    "description": description,
                    "source": "dynamic_fallback",
                    "confidence_score": round(best_score, 4),
                    "matched_template_index": None,
                    "used_fallback": True,
                    "error": None,
                }

            matched_template = self.corpus[best_index].template
            description = self._safe_fill_template(matched_template, slots)
            return {
                "description": description,
                "source": "semantic_retrieval",
                "confidence_score": round(best_score, 4),
                "matched_template_index": best_index,
                "used_fallback": False,
                "error": None,
            }
        except Exception as exc:
            logger.exception("Description generation failed unexpectedly")
            description = self._safe_fill_template(self.dynamic_fallback_template, slots)
            return {
                "description": description,
                "source": "error_fallback",
                "confidence_score": 0.0,
                "matched_template_index": None,
                "used_fallback": True,
                "error": str(exc),
            }


if __name__ == "__main__":
    # CLI-style demo with 3 distinct test cases.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    retriever = DescriptionRetriever(confidence_threshold=0.10)

    test_inputs = [
        "selling used gaming laptop, good battery, $450 near UIUC campus",
        "need math tutoring calc + physics evenings in champaign, affordable",
        "blorp quantum vibes maybe thingy idk ???",
    ]

    for idx, user_text in enumerate(test_inputs, start=1):
        result = retriever.generate_description(user_text)
        print(f"\n--- Test Case {idx} ---")
        print(f"Input: {user_text}")
        print(f"Source: {result['source']}")
        print(f"Confidence: {result['confidence_score']}")
        print(f"Used fallback: {result['used_fallback']}")
        print("Description:")
        print(result["description"])
