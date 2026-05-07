# Travel Buddy AI Integration - System Description

## Overview

Harbor uses AI to enhance the student marketplace experience through:
1. **Local LLM:** Automated listing description generation (HuggingFace)
2. **External API:** Advanced text generation via Google Gemini API

---

## AI Workflow

1. **AI Description Generator**
   - User provides: Basic details
   - Method: Django form with POST request

2. **Gemini API**
   - User provides: Free-form text input
   - Method: Simple text prompt via web form
```python
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


```


## AI Models Used

**Model:** `gemini-2.5-flash`

- Smallest model that produces coherent text
- Fast inference
- Free tier: 15 requests/minute
- Used for enhanced descriptions

---