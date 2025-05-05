"""Test configuration for the project."""

import os
import sys
import pytest

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock required environment variables for tests."""
    monkeypatch.setenv("JIRA_INSTANCE", "test.atlassian.net")
    monkeypatch.setenv("EMAIL", "test@example.com")
    monkeypatch.setenv("ATLASSIAN_TOKEN", "test-token")
    monkeypatch.setenv("SQLITE_PATH", ":memory:")
