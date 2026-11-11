import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors

from services.gemini_retry_service import (
    generate_with_retry,
    get_server_retry_delay,
)

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing from .env")

client = genai.Client(api_key=api_key)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Tried in order when the current model is out of quota (429), not
# found (404) or temporarily failing (5xx). Free-tier quota is
# tracked per model, so another model usually still has capacity.
# Override with GEMINI_FALLBACK_MODELS="modelA,modelB" in .env.
FALLBACK_MODELS = [
    name.strip()
    for name in os.getenv(
        "GEMINI_FALLBACK_MODELS",
        "gemini-3.1-flash-lite,gemini-2.5-flash",
    ).split(",")
    if name.strip()
]

# HTTP statuses that should move on to the next model.
MODEL_SWITCH_CODES = {404, 429, 500, 502, 503, 504}

# Seconds to skip a model after it reported exhausted quota, so every
# call does not waste a request on a model known to be out of quota.
QUOTA_COOLDOWN_SECONDS = 60

# Wait used before the last-resort retry when no server delay is given.
DEFAULT_QUOTA_WAIT_SECONDS = 5

_quota_cooldown_until = {}


def _model_order() -> list[str]:
    models = [MODEL_NAME] + [
        name for name in FALLBACK_MODELS if name != MODEL_NAME
    ]

    now = time.time()

    available = [
        name for name in models
        if _quota_cooldown_until.get(name, 0) <= now
    ]
    cooling = [name for name in models if name not in available]

    return available + cooling


def _generate_with_model(model: str, prompt: str, **retry_options) -> str:

    response = generate_with_retry(
        lambda: client.models.generate_content(
            model=model,
            contents=prompt
        ),
        **retry_options
    )

    text = getattr(response, "text", None)

    # Never hand None/empty text to callers (it would be saved or
    # crash on .strip()); fail loudly so no empty answer is stored.
    if not text or not text.strip():
        raise RuntimeError("Gemini returned an empty response.")

    return text


def generate_answer(prompt: str) -> str:
    """
    Generate text, falling back to another Gemini model when the
    current one has no quota left or is unavailable.
    """

    last_error = None
    last_quota_error = None
    quota_delays = []

    for model in _model_order():

        try:
            # First pass: do not sleep on quota errors, just switch.
            return _generate_with_model(
                model,
                prompt,
                max_retries=1,
                retry_quota_errors=False,
            )

        except errors.APIError as error:
            code = getattr(error, "code", None)

            if code not in MODEL_SWITCH_CODES:
                raise

            last_error = error

            if code == 429:
                last_quota_error = error

                server_delay = get_server_retry_delay(error)

                if server_delay is not None:
                    quota_delays.append(server_delay)

                _quota_cooldown_until[model] = (
                    time.time() + QUOTA_COOLDOWN_SECONDS
                )

            print(
                f"Gemini model '{model}' failed ({code}); "
                "trying next model..."
            )

        except RuntimeError as error:
            # Empty response from this model: try the next one.
            last_error = error

            print(
                f"Gemini model '{model}' gave no usable text; "
                "trying next model..."
            )

    # Every model failed. If they all ran out of quota, wait for the
    # server-suggested delay (max 30s) and retry the primary once more.
    if last_quota_error is not None and last_error is last_quota_error:
        wait = max(
            quota_delays,
            default=DEFAULT_QUOTA_WAIT_SECONDS,
        )

        print(
            f"All Gemini models are out of quota; "
            f"waiting {wait:g}s before retrying..."
        )

        time.sleep(wait)

        return _generate_with_model(MODEL_NAME, prompt)

    raise last_error


def rewrite_query(
    query: str,
    history: list = None,
    memory_summary: str = ""
) -> str:

    history = history or []

    if not history and not memory_summary:
        return query

    history_text = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in history[-6:]
    )

    prompt = f"""
You are a search query rewriting assistant.

Your task is to convert the latest user question
into a standalone search query.

LONG-TERM MEMORY:
{memory_summary or "No long-term memory available."}

RECENT CONVERSATION:
{history_text or "No recent conversation."}

LATEST USER QUESTION:
{query}

RULES:
1. Resolve references using long-term memory and recent conversation.
2. Resolve words such as they, them, their, he and she.
3. Preserve names, IDs and important details.
4. Do not answer the question.
5. Do not invent information.
6. If the question is already standalone, preserve its meaning.
7. Return ONLY the rewritten search query.

STANDALONE SEARCH QUERY:
"""

    return generate_answer(prompt).strip()