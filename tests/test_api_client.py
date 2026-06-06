"""Unit tests for api_client: exceptions, error-checking helpers, and api_get."""

import time
import pytest
from unittest.mock import MagicMock, patch

from dora_lead_time.api_client import (
    ApiSource,
    ApiError,
    AuthError,
    RateLimitError,
    api_get,
    raise_if_api_error,
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


# ---------------------------------------------------------------------------
# raise_if_api_error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status_code", [400, 404, 500, 503])
def test_raise_if_api_error_raises(status_code):
    """4xx and 5xx responses raise ApiError."""
    response = _mock_response(status_code)
    with pytest.raises(ApiError):
        raise_if_api_error(response, ApiSource.ATLASSIAN)


def test_raise_if_api_error_message_contains_source():
    """ApiError message identifies the API source."""
    response = _mock_response(500)
    with pytest.raises(ApiError, match="Atlassian"):
        raise_if_api_error(response, ApiSource.ATLASSIAN)


def test_raise_if_api_error_message_contains_status():
    """ApiError message includes the HTTP status code."""
    response = _mock_response(500)
    with pytest.raises(ApiError, match="500"):
        raise_if_api_error(response, ApiSource.ATLASSIAN)


@pytest.mark.parametrize("status_code", [200, 201, 204])
def test_raise_if_api_error_no_raise(status_code):
    """2xx responses do not raise ApiError."""
    response = _mock_response(status_code)
    raise_if_api_error(response, ApiSource.GITHUB)  # should not raise


# ---------------------------------------------------------------------------
# api_get
# ---------------------------------------------------------------------------

def _patched_get(mock_response):
    """Return a context manager that patches requests.get with mock_response."""
    return patch("dora_lead_time.api_client.requests.get", return_value=mock_response)


def test_api_get_200_returns_response():
    """200 response is returned when raise_on_error is True (default)."""
    mock = _mock_response(200)
    with _patched_get(mock):
        result = api_get("https://example.com", ApiSource.GITHUB, {})
    assert result is mock


def test_api_get_200_raise_on_error_false_returns_response():
    """200 response is returned when raise_on_error is False."""
    mock = _mock_response(200)
    with _patched_get(mock):
        result = api_get(
            "https://example.com", ApiSource.GITHUB, {}, raise_on_error=False
        )
    assert result is mock


def test_api_get_401_raises_auth_error():
    """401 response raises AuthError regardless of raise_on_error."""
    mock = _mock_response(401)
    with _patched_get(mock):
        with pytest.raises(AuthError):
            api_get("https://example.com", ApiSource.GITHUB, {})


def test_api_get_401_raise_on_error_false_raises_auth_error():
    """401 response raises AuthError even when raise_on_error is False."""
    mock = _mock_response(401)
    with _patched_get(mock):
        with pytest.raises(AuthError):
            api_get(
                "https://example.com", ApiSource.GITHUB, {}, raise_on_error=False
            )


def test_api_get_429_raises_rate_limit_error():
    """429 response raises RateLimitError regardless of raise_on_error."""
    mock = _mock_response(429)
    with _patched_get(mock):
        with pytest.raises(RateLimitError):
            api_get("https://example.com", ApiSource.GITHUB, {})


def test_api_get_500_raise_on_error_true_raises_api_error():
    """500 response raises ApiError when raise_on_error is True (default)."""
    mock = _mock_response(500)
    with _patched_get(mock):
        with pytest.raises(ApiError):
            api_get("https://example.com", ApiSource.ATLASSIAN, {})


def test_api_get_500_raise_on_error_false_returns_response():
    """500 response is returned (not raised) when raise_on_error is False."""
    mock = _mock_response(500)
    with _patched_get(mock):
        result = api_get(
            "https://example.com", ApiSource.ATLASSIAN, {}, raise_on_error=False
        )
    assert result is mock
    assert result.status_code == 500


def test_api_get_passes_arguments_to_requests():
    """All parameters are forwarded correctly to requests.get."""
    mock = _mock_response(200)
    with patch(
        "dora_lead_time.api_client.requests.get", return_value=mock
    ) as mock_get:
        api_get(
            "https://example.com",
            ApiSource.GITHUB,
            {"Authorization": "token abc"},
            timeout=10,
        )
    mock_get.assert_called_once_with(
        "https://example.com",
        headers={"Authorization": "token abc"},
        auth=None,
        params=None,
        timeout=10,
    )
