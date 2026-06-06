"""Unit tests for exceptions and error-handling helpers."""

import time
import pytest
from unittest.mock import MagicMock

from dora_lead_time.exceptions import (
    ApiSource,
    AuthError,
    RateLimitError,
    raise_if_auth_error,
    raise_if_rate_limit_error,
)


def _mock_response(status_code, headers=None):
    """Build a minimal mock HTTP response."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    return response


# ---------------------------------------------------------------------------
# raise_if_auth_error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status_code", [401, 403])
def test_raise_if_auth_error_raises(status_code):
    """401 and 403 responses raise AuthError."""
    response = _mock_response(status_code)
    with pytest.raises(AuthError):
        raise_if_auth_error(response, ApiSource.GITHUB)


def test_raise_if_auth_error_message_contains_description():
    """AuthError message identifies the API source."""
    response = _mock_response(401)
    with pytest.raises(AuthError, match="GitHub"):
        raise_if_auth_error(response, ApiSource.GITHUB)


@pytest.mark.parametrize("status_code", [200, 404, 429, 500])
def test_raise_if_auth_error_no_raise(status_code):
    """Non-401/403 responses do not raise AuthError."""
    response = _mock_response(status_code)
    raise_if_auth_error(response, ApiSource.GITHUB)  # should not raise


# ---------------------------------------------------------------------------
# raise_if_rate_limit_error — basic behaviour
# ---------------------------------------------------------------------------

def test_raise_if_rate_limit_error_raises_on_429():
    """429 response raises RateLimitError."""
    response = _mock_response(429)
    with pytest.raises(RateLimitError):
        raise_if_rate_limit_error(response, ApiSource.ATLASSIAN)


def test_raise_if_rate_limit_error_message_contains_source():
    """RateLimitError message identifies the API source."""
    response = _mock_response(429)
    with pytest.raises(RateLimitError, match="GitHub"):
        raise_if_rate_limit_error(response, ApiSource.GITHUB)


@pytest.mark.parametrize("status_code", [200, 401, 403, 404, 500])
def test_raise_if_rate_limit_error_no_raise(status_code):
    """Non-429 responses do not raise RateLimitError."""
    response = _mock_response(status_code)
    raise_if_rate_limit_error(response, ApiSource.ATLASSIAN)  # should not raise


# ---------------------------------------------------------------------------
# raise_if_rate_limit_error — Retry-After header (seconds)
# ---------------------------------------------------------------------------

def test_raise_if_rate_limit_error_retry_after_in_message():
    """Retry-After header value is reflected in the error message."""
    response = _mock_response(429, headers={"Retry-After": "60"})
    with pytest.raises(RateLimitError, match="60 seconds"):
        raise_if_rate_limit_error(response, ApiSource.ATLASSIAN)


def test_raise_if_rate_limit_error_retry_after_timestamp_in_message():
    """Retry-After header produces a UTC timestamp in the error message."""
    response = _mock_response(429, headers={"Retry-After": "120"})
    with pytest.raises(RateLimitError, match="UTC"):
        raise_if_rate_limit_error(response, ApiSource.ATLASSIAN)


# ---------------------------------------------------------------------------
# raise_if_rate_limit_error — x-ratelimit-reset header (Unix timestamp)
# ---------------------------------------------------------------------------

def test_raise_if_rate_limit_error_ratelimit_reset_in_message():
    """x-ratelimit-reset header produces a UTC reset time in the error message."""
    reset_ts = int(time.time()) + 300
    response = _mock_response(
        429, headers={"x-ratelimit-reset": str(reset_ts)}
    )
    with pytest.raises(RateLimitError, match="UTC"):
        raise_if_rate_limit_error(response, ApiSource.GITHUB)


def test_raise_if_rate_limit_error_no_headers_unknown():
    """429 with no retry headers includes 'unknown' in the error message."""
    response = _mock_response(429)
    with pytest.raises(RateLimitError, match="unknown"):
        raise_if_rate_limit_error(response, ApiSource.ATLASSIAN)


def test_raise_if_rate_limit_error_prefers_retry_after_over_reset():
    """Retry-After takes precedence over x-ratelimit-reset when both present."""
    reset_ts = int(time.time()) + 300
    response = _mock_response(
        429,
        headers={
            "Retry-After": "30",
            "x-ratelimit-reset": str(reset_ts),
        },
    )
    with pytest.raises(RateLimitError, match="30 seconds"):
        raise_if_rate_limit_error(response, ApiSource.ATLASSIAN)
