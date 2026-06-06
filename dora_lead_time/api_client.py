"""API client utilities: custom exceptions, error-checking helpers, and HTTP GET."""

import enum
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)


class ApiSource(enum.Enum):
    """Identifies the external API that a request was made against."""

    GITHUB = "GitHub"
    ATLASSIAN = "Atlassian"


class AuthError(Exception):
    """Raised when an API request fails due to an authentication error.

    Attributes:
        message: Explanation of which token failed and why.
    """


class RateLimitError(Exception):
    """Raised when an API request is rejected due to rate limiting.

    Attributes:
        message: Explanation of the rate limit and when to retry.
    """


class ApiError(Exception):
    """Raised when a structural API request fails with an unrecoverable error.

    Attributes:
        message: Explanation of what request failed and the HTTP status code.
    """


def raise_if_auth_error(
    response: requests.Response, source: ApiSource
) -> None:
    """Raise AuthError if the response indicates an authentication failure.

    Args:
        response: The HTTP response to inspect.
        source: The API source that returned the response.

    Raises:
        AuthError: If the response status code is 401 or 403.
    """
    if response.status_code in (401, 403):
        raise AuthError(
            f"Authentication failed for {source.value} "
            f"(HTTP {response.status_code}). "
            "Please check that your API token is valid and has not expired."
        )


def raise_if_rate_limit_error(
    response: requests.Response, source: ApiSource
) -> None:
    """Raise RateLimitError if the response indicates a rate-limit failure.

    Reads the ``Retry-After`` header (seconds to wait, used by Atlassian and
    other generic APIs) or the ``x-ratelimit-reset`` header (Unix timestamp,
    used by GitHub) to determine and log when it is safe to retry.

    Args:
        response: The HTTP response to inspect.
        source: The API source that returned the response.

    Raises:
        RateLimitError: If the response status code is 429.
    """
    if response.status_code != 429:
        return

    retry_message = "Retry time unknown."

    retry_after = response.headers.get("Retry-After")
    ratelimit_reset = response.headers.get("x-ratelimit-reset")

    if retry_after is not None:
        try:
            retry_seconds = int(retry_after)
            retry_at = datetime.now(tz=timezone.utc).timestamp() + retry_seconds
            retry_dt = datetime.fromtimestamp(retry_at, tz=timezone.utc)
            retry_message = (
                f"Retry after {retry_seconds} seconds "
                f"(at {retry_dt.strftime('%Y-%m-%d %H:%M:%S UTC')})."
            )
        except ValueError:
            retry_message = f"Retry after: {retry_after}."
    elif ratelimit_reset is not None:
        try:
            reset_dt = datetime.fromtimestamp(
                int(ratelimit_reset), tz=timezone.utc
            )
            retry_message = (
                f"Rate limit resets at "
                f"{reset_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}."
            )
        except ValueError:
            retry_message = f"Rate limit reset: {ratelimit_reset}."

    logger.error(
        "Rate limit exceeded for %s. %s", source.value, retry_message
    )
    raise RateLimitError(
        f"Rate limit exceeded for {source.value}. {retry_message}"
    )


def raise_if_api_error(
    response: requests.Response, source: ApiSource
) -> None:
    """Raise ApiError for any unrecoverable 4xx/5xx response.

    Intended for structural, list-based requests where a failure means the
    entire operation cannot proceed. Call this after ``raise_if_auth_error``
    and ``raise_if_rate_limit_error`` have already been invoked so that 401,
    403, and 429 responses are handled by their dedicated helpers.

    Args:
        response: The HTTP response to inspect.
        source: The API source that returned the response.

    Raises:
        ApiError: If the response status code is 400 or higher.
    """
    if response.status_code >= 400:
        raise ApiError(
            f"{source.value} API request failed "
            f"(HTTP {response.status_code})."
        )


def api_get(
    url: str,
    source: ApiSource,
    headers: dict[str, str],
    *,
    auth: tuple[str, str] | None = None,
    params: dict | None = None,
    timeout: int = 30,
    raise_on_error: bool = True,
) -> requests.Response:
    """Make a GET request with standard error checking.

    Always raises ``AuthError`` on 401/403 and ``RateLimitError`` on 429.

    When *raise_on_error* is ``True`` (the default), also raises ``ApiError``
    for any remaining non-2xx response — use this for structural or
    list-based requests where a failure means the entire operation cannot
    proceed.

    When *raise_on_error* is ``False``, returns the response as-is so the
    caller can inspect ``status_code``, log a meaningful message, and skip
    the individual item.

    Args:
        url: The URL to GET.
        source: The API source, used in error messages.
        headers: HTTP headers to include in the request.
        auth: Optional ``(username, password)`` tuple for HTTP Basic Auth.
        params: Optional query-string parameters to append to the URL.
        timeout: Request timeout in seconds. Defaults to 30.
        raise_on_error: If ``True``, raise ``ApiError`` for any non-2xx
            response not already handled by ``raise_if_auth_error`` or
            ``raise_if_rate_limit_error``. If ``False``, return the response
            regardless of status code.

    Returns:
        The HTTP response.

    Raises:
        AuthError: If the response status is 401 or 403.
        RateLimitError: If the response status is 429.
        ApiError: If the response status is >= 400 and *raise_on_error*
            is ``True``.
    """
    response = requests.get(
        url, headers=headers, auth=auth, params=params, timeout=timeout
    )
    raise_if_auth_error(response, source)
    raise_if_rate_limit_error(response, source)
    if raise_on_error:
        raise_if_api_error(response, source)
    return response
