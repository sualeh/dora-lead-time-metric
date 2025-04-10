"""Unit tests for the GitHubRequests class."""

import os
import pytest
import unittest.mock as mock
import json
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from dora_lead_time.github_requests import GitHubRequests
from dora_lead_time.models import PullRequestIdentifier, PullRequest


class MockResponse:
    """Mock response for requests."""

    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code
        self.text = json.dumps(json_data)

    def json(self):
        """Return JSON data."""
        return self.json_data


@pytest.fixture
def github_client():
    """Create a GitHubRequests instance with mocked token mapping."""
    with patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN_ORG1": "test-token-org1",
            "GITHUB_TOKEN_ORG2": "test-token-org2",
        },
    ):
        return GitHubRequests({
            "Org1": "GITHUB_TOKEN_ORG1",
            "Org2": "GITHUB_TOKEN_ORG2"
        })


def test_init_with_token_map():
    """Test initialization with token map."""
    with patch.dict(
        os.environ,
        {
            "CUSTOM_TOKEN": "custom-token",
        },
    ):
        client = GitHubRequests({"CustomOrg": "CUSTOM_TOKEN"})
        assert "CustomOrg" in client.github_token_map
        assert client.github_token_map["CustomOrg"] == "custom-token"


def test_init_with_missing_token():
    """Test initialization with missing token in environment."""
    with patch.dict(os.environ, {}, clear=True):
        client = GitHubRequests({"MissingOrg": "MISSING_TOKEN"})
        assert "MissingOrg" not in client.github_token_map


def test_init_with_empty_map():
    """Test initialization with empty token map."""
    client = GitHubRequests({})
    assert client.github_token_map == {}


@patch("requests.get")
def test_get_pull_request_details(mock_get, github_client):
    """Test getting pull request details from GitHub."""
    # Mock PR data
    mock_pr_data = {
        "title": "Test PR",
        "created_at": "2023-01-01T10:00:00Z",
        "closed_at": "2023-01-02T15:30:00Z",
    }

    # Mock commit data
    mock_commits_data = [
        {
            "commit": {
                "committer": {
                    "date": "2022-12-30T08:45:00Z"
                }
            }
        },
        {
            "commit": {
                "committer": {
                    "date": "2023-01-01T09:30:00Z"
                }
            }
        },
    ]

    # Configure the mock to return different responses based on URL
    def side_effect(*args, **kwargs):
        url = args[0]
        if "pulls/123" in url and "/commits" not in url:
            return MockResponse(mock_pr_data)
        elif "pulls/123/commits" in url:
            return MockResponse(mock_commits_data)
        return MockResponse({}, 404)

    mock_get.side_effect = side_effect

    # Test data
    pull_requests = [
        PullRequestIdentifier(
            id=1,
            pr_owner="Org1",
            pr_repository="test-repo",
            pr_number="123"
        )
    ]

    # Call the method
    result = github_client.get_pull_request_details(pull_requests)

    # Assertions
    assert len(result) == 1
    pr = result[0]
    assert pr.id == 1
    assert pr.pr_title == "Test PR"
    assert pr.open_date == date(2023, 1, 1)
    assert pr.close_date == date(2023, 1, 2)
    assert pr.commit_count == 2
    assert pr.earliest_commit_date == date(2022, 12, 30)
    assert pr.latest_commit_date == date(2023, 1, 1)


@patch("requests.get")
def test_get_pull_request_details_api_error(mock_get, github_client):
    """Test handling API errors when getting pull request details."""
    # Mock failed API response
    mock_get.return_value = MockResponse({}, 404)

    # Test data
    pull_requests = [
        PullRequestIdentifier(
            id=1,
            pr_owner="Org1",
            pr_repository="test-repo",
            pr_number="123"
        )
    ]

    # Call the method
    result = github_client.get_pull_request_details(pull_requests)

    # Should return empty list
    assert len(result) == 0


@patch("requests.get")
def test_get_pull_request_details_commits_error(mock_get, github_client):
    """Test handling errors when getting commit details."""
    # Mock PR data success but commits failure
    mock_pr_data = {
        "title": "Test PR",
        "created_at": "2023-01-01T10:00:00Z",
        "closed_at": "2023-01-02T15:30:00Z",
    }

    # Configure the mock to return success for PR but fail for commits
    def side_effect(*args, **kwargs):
        url = args[0]
        if "pulls/123" in url and "/commits" not in url:
            return MockResponse(mock_pr_data)
        elif "pulls/123/commits" in url:
            return MockResponse({}, 404)
        return MockResponse({}, 404)

    mock_get.side_effect = side_effect

    # Test data
    pull_requests = [
        PullRequestIdentifier(
            id=1,
            pr_owner="Org1",
            pr_repository="test-repo",
            pr_number="123"
        )
    ]

    # Call the method
    result = github_client.get_pull_request_details(pull_requests)

    # Should still return the PR but with empty commit data
    assert len(result) == 1
    pr = result[0]
    assert pr.commit_count == 0
    assert pr.earliest_commit_date is None
    assert pr.latest_commit_date is None


def test_get_pull_request_details_no_token():
    """Test error when no GitHub token is available."""
    client = GitHubRequests({})  # Empty token map

    # Test data
    pull_requests = [
        PullRequestIdentifier(
            id=1,
            pr_owner="Org1",
            pr_repository="test-repo",
            pr_number="123"
        )
    ]

    with pytest.raises(ValueError):
        client.get_pull_request_details(pull_requests)


def test_get_pull_request_details_empty_list(github_client):
    """Test with empty pull requests list."""
    result = github_client.get_pull_request_details([])
    assert result == []


@patch("requests.get")
def test_get_pull_request_details_missing_token_for_org(mock_get, github_client):
    """Test handling missing token for a specific organization."""
    # Test data for an organization without a token
    pull_requests = [
        PullRequestIdentifier(
            id=1,
            pr_owner="UnknownOrg",
            pr_repository="test-repo",
            pr_number="123"
        )
    ]

    # Call the method
    result = github_client.get_pull_request_details(pull_requests)

    # Should return empty list since org has no token
    assert len(result) == 0
    assert mock_get.call_count == 0  # No API calls made
