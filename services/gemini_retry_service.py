import re
import time

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Longest server-requested wait we are willing to honor (seconds).
MAX_SERVER_RETRY_DELAY = 30


def get_server_retry_delay(error):
    """
    Extract retry delay from Gemini error details.

    Supports formats such as:
      retryDelay: 22s
      retryDelay="22s"
      retry_delay: 22s
      Please retry in 22.37s
    """

    error_text = str(error)

    # Try common Gemini / Google API error formats.
    patterns = [
        r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s",
        r"retry_delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s",
        r"retry in\s+(\d+(?:\.\d+)?)\s*s",
    ]

    for pattern in patterns:
        match = re.search(pattern, error_text, re.IGNORECASE)

        if match:
            delay = float(match.group(1))
            return min(delay, MAX_SERVER_RETRY_DELAY)

    return None


def generate_with_retry(
    generate_fn,
    max_retries=3,
    retry_quota_errors=True,
):
    """
    Retry temporary Gemini API failures.

    max_retries=3 means up to 4 total attempts. Delays are 1s, 2s, 4s
    (exponential backoff), except for 429 errors that carry a
    server-provided retry delay: that delay is honored (max 30s).
    Non-temporary errors are raised immediately.

    retry_quota_errors=False raises 429 immediately instead of waiting,
    so the caller can switch to another model.
    """

    for attempt in range(max_retries + 1):
        try:
            result = generate_fn()

            if result is None:
                raise RuntimeError("Gemini returned None.")

            return result

        except Exception as error:
            # google-genai APIError exposes the HTTP status as `.code`.
            status_code = (
                getattr(error, "status_code", None)
                or getattr(error, "code", None)
            )

            try:
                status_code = int(status_code)
            except (TypeError, ValueError):
                status_code = None

            if (
                status_code not in RETRYABLE_STATUS_CODES
                or attempt == max_retries
                or (status_code == 429 and not retry_quota_errors)
            ):
                raise

            delay = 2 ** attempt

            if status_code == 429:
                server_delay = get_server_retry_delay(error)

                if server_delay is not None:
                    delay = server_delay

            print(
                f"Gemini temporary error {status_code}. "
                f"Retrying in {delay:g}s "
                f"({attempt + 1}/{max_retries})..."
            )

            time.sleep(delay)
