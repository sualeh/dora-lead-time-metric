"""Shared test helpers for dora_lead_time test suite."""

import json


class MockResponse:
    """Reusable mock HTTP response used across multiple test modules."""

    def __init__(self, json_data, status_code=200, headers=None):
        self.json_data = json_data
        self.status_code = status_code
        self.text = json.dumps(json_data)
        self.headers = headers or {}

    def json(self):
        """Return JSON data."""
        return self.json_data

    def raise_for_status(self):
        """Raise if status code is not 2xx."""
        if self.status_code < 200 or self.status_code >= 300:
            raise Exception(
                f"API request failed with status {self.status_code}"
            )
