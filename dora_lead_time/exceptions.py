"""Custom exceptions and shared error-handling helpers."""

import requests


class AuthError(Exception):
    """Raised when an API request fails due to an authentication error.

    Attributes:
        message: Explanation of which token failed and why.
    """


def raise_if_auth_error(
    response: requests.Response, token_description: str
) -> None:
    """Raise AuthError if the response indicates an authentication failure.

    Args:
        response: The HTTP response to inspect.
        token_description: Human-readable description of the credential that
            was used (e.g. "GitHub token for MyOrg" or "Atlassian token").

    Raises:
        AuthError: If the response status code is 401 or 403.
    """
    if response.status_code in (401, 403):
        raise AuthError(
            f"Authentication failed for {token_description} "
            f"(HTTP {response.status_code}). "
            "Please check that your API token is valid and has not expired."
        )
