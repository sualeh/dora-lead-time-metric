"""Test fixtures and configuration for dora_lead_time tests."""

import pytest
import os

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock required environment variables for tests."""
    monkeypatch.setenv("JIRA_INSTANCE", "test.atlassian.net")
    monkeypatch.setenv("EMAIL", "test@example.com")
    monkeypatch.setenv("ATLASSIAN_TOKEN", "test-token")
