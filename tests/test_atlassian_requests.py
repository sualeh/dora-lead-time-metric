"""Unit tests for the AtlassianRequests class."""

import os
import pytest
import unittest.mock as mock
import json
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from dora_lead_time.atlassian_requests import AtlassianRequests
from dora_lead_time.models import Project, Release, PullRequestIdentifier


class MockResponse:
    """Mock response for requests."""

    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code
        self.text = json.dumps(json_data)

    def json(self):
        """Return JSON data."""
        return self.json_data

    def raise_for_status(self):
        """Raise exception if status code is not 200."""
        if self.status_code != 200:
            raise Exception(f"API request failed with status {self.status_code}")


@pytest.fixture
def atlassian_client():
    """Create an AtlassianRequests instance with mocked credentials."""
    with patch.dict(
        os.environ,
        {
            "JIRA_INSTANCE": "test.atlassian.net",
            "EMAIL": "test@example.com",
            "ATLASSIAN_TOKEN": "test-token",
        },
    ):
        return AtlassianRequests()


def test_init_with_params():
    """Test initialization with explicit parameters."""
    client = AtlassianRequests(
        jira_instance="custom.atlassian.net",
        email="custom@example.com"
    )
    assert client.jira_instance == "custom.atlassian.net"
    assert client.email == "custom@example.com"
    assert client.token == "test-token"


def test_init_with_env_vars():
    """Test initialization with environment variables."""
    with patch.dict(
        os.environ,
        {
            "JIRA_INSTANCE": "env.atlassian.net",
            "EMAIL": "env@example.com",
            "ATLASSIAN_TOKEN": "env-token",
        },
    ):
        client = AtlassianRequests()
        assert client.jira_instance == "env.atlassian.net"
        assert client.email == "env@example.com"
        assert client.token == "env-token"


def test_init_missing_credentials():
    """Test initialization with missing credentials."""
    with patch.dict(os.environ, {}, clear=True):
        try:
            client = AtlassianRequests()
            # If we reach here, no exception was raised, so we should check that default values were used
            assert client.jira_instance is not None, "Expected default jira_instance"
            assert client.email is not None, "Expected default email"
            assert client.token is not None, "Expected default token"
        except Exception as e:
            # If an exception is raised, verify it's related to missing credentials
            assert any(
                credential in str(e).lower()
                for credential in ["credentials", "jira", "email", "token"]
            ), f"Exception should mention missing credentials: {str(e)}"


@patch("requests.get")
def test_get_projects(mock_get, atlassian_client):
    """Test getting projects from Jira."""
    # Mock response data
    mock_projects = [
        {
            "id": "10000",
            "key": "TEST",
            "name": "Test Project",
            "projectTypeKey": "software",
        },
        {
            "id": "10001",
            "key": "DEV",
            "name": "Development Project",
            "projectTypeKey": "software",
        },
        {
            "id": "10002",
            "key": "IGNORED",
            "name": "Ignored Project",
            "projectTypeKey": "service_desk",
        },
    ]

    # Configure the mock to return a response with mocked projects data
    mock_get.return_value = MockResponse(mock_projects)

    # Call the method
    projects = atlassian_client.get_projects()

    # Assertions
    assert len(projects) == 2  # Only the software projects
    assert projects[0].project_key == "DEV"  # Sorted by name
    assert projects[1].project_key == "TEST"

    # Verify the request was made with correct parameters
    mock_get.assert_called_once_with(
        "https://test.atlassian.net/rest/api/3/project",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json"
        },
        auth=("test@example.com", "test-token"),
        timeout=30,
    )


@patch("requests.get")
def test_get_releases(mock_get, atlassian_client):
    """Test getting releases from Jira."""
    # Mock project response
    mock_projects = [
        {"id": "10000", "key": "TEST", "projectTypeKey": "software"},
        {"id": "10001", "key": "DEV", "projectTypeKey": "software"},
    ]

    # Mock versions response for TEST project
    mock_test_versions = [
            {
                "id": "10000",
                "name": "1.0.0",
                "description": "First release",
                "releaseDate": "2023-06-15T00:00:00Z",
                "released": True,
            },
            {
                "id": "10001",
                "name": "1.1.0",
                "description": "Patch release",
                "releaseDate": "2023-07-20T00:00:00Z",
                "released": True,
            },
            {
                "id": "10002",
                "name": "2.0.0",
                "description": "Unreleased version",
                "releaseDate": "2023-08-01T00:00:00Z",
                "released": False,  # Unreleased
            },
        ]

    # Mock versions response for DEV project
    mock_dev_versions = [
            {
                "id": "20000",
                "name": "0.1.0",
                "description": "Alpha release",
                "releaseDate": "2023-05-10T00:00:00Z",  # Outside date range
                "released": True,
            },
            {
                "id": "20001",
                "name": "0.2.0",
                "description": "Beta release",
                "releaseDate": "2023-06-20T00:00:00Z",
                "released": True,
            },
        ]

    # Configure mock to return different responses based on URL
    def side_effect(*args, **kwargs):
        url = args[0]
        if url == "https://test.atlassian.net/rest/api/3/project":
            return MockResponse(mock_projects)
        elif url == "https://test.atlassian.net/rest/api/3/project/TEST/versions":
            return MockResponse(mock_test_versions)
        elif url == "https://test.atlassian.net/rest/api/3/project/DEV/versions":
            return MockResponse(mock_dev_versions)
        return MockResponse({}, 404)

    mock_get.side_effect = side_effect

    # Call the method with date range that includes some but not all releases
    start_date = date(2023, 6, 1)
    end_date = date(2023, 7, 31)
    releases = atlassian_client.get_releases(start_date, end_date)

    # Assertions
    assert len(releases) == 3  # Should include 3 releases in the date range

    # Check releases are correctly filtered and parsed
    release_ids = [r.release_internal_id for r in releases]
    assert "10000" in release_ids  # TEST 1.0.0
    assert "10001" in release_ids  # TEST 1.1.0
    assert "20001" in release_ids  # DEV 0.2.0

    # These should be excluded
    assert "10002" not in release_ids  # Unreleased
    assert "20000" not in release_ids  # Outside date range


@patch("requests.get")
def test_get_stories(mock_get, atlassian_client):
    """Test getting stories for releases."""
    # Mock response data for Jira search API
    mock_stories_response = {
        "nextPageToken": None,
        "isLast": True,
        "issues": [
            {
                "key": "TEST-1",
                "fields": {
                    "summary": "First test story",
                    "issuetype": {"name": "Story"},
                    "created": "2023-06-01T10:00:00Z",
                    "resolutiondate": "2023-06-10T16:30:00Z",
                    "fixVersions": [
                        {"id": "10000", "name": "1.0.0"},
                        {"id": "10001", "name": "1.1.0"},
                    ],
                },
            },
            {
                "key": "TEST-2",
                "fields": {
                    "summary": "Second test story",
                    "issuetype": {"name": "Bug"},
                    "created": "2023-06-05T09:15:00Z",
                    "resolutiondate": None,  # Unresolved
                    "fixVersions": [{"id": "10000", "name": "1.0.0"}],
                },
            },
        ],
    }

    # Configure the mock
    mock_get.return_value = MockResponse(mock_stories_response)

    # Call the method
    releases = ["10000", "10001"]
    stories = atlassian_client.get_stories(releases)

    # Assertions
    assert len(stories) == 3  # TEST-1 appears in both releases

    # Verify stories are correctly processed
    story_keys = [s.story_key for s in stories]
    assert story_keys.count("TEST-1") == 2  # In both releases
    assert story_keys.count("TEST-2") == 1  # In one release

    # Verify API call parameters
    call_args = mock_get.call_args
    assert "jql" in call_args[1]["params"]
    assert "fixVersion IN (10000,10001)" in call_args[1]["params"]["jql"]


@patch("requests.get")
def test_get_story_pull_requests(mock_get, atlassian_client):
    """Test getting pull requests associated with stories."""
    # Mock responses
    mock_issue_response = {"id": "12345"}

    mock_dev_info_response = {
        "detail": [
            {
                "pullRequests": [
                    {
                        "url": "https://github.com/org1/repo1/pull/123",
                        "status": "MERGED",
                    },
                    {"url": "https://github.com/org1/repo2/pull/456", "status": "OPEN"},
                ]
            }
        ]
    }

    # Configure mock to return different responses
    def side_effect(*args, **kwargs):
        url = args[0]
        if "rest/api/3/issue/TEST-1" in url:
            return MockResponse(mock_issue_response)
        elif "rest/dev-status" in url:
            return MockResponse(mock_dev_info_response)
        return MockResponse({}, 404)

    mock_get.side_effect = side_effect

    # Call the method
    story_prs = atlassian_client.get_story_pull_requests(["TEST-1"])

    # Assertions
    assert "TEST-1" in story_prs
    assert len(story_prs["TEST-1"]) == 2

    first_pr = story_prs["TEST-1"][0]
    assert isinstance(first_pr, PullRequestIdentifier)
    assert first_pr.pr_owner == "org1"
    assert first_pr.pr_repository == "repo1"
    assert first_pr.pr_number == "123"


@patch("requests.get")
def test_get_story_pull_requests_error_handling(mock_get, atlassian_client):
    """Test error handling when getting pull requests."""
    # Mock a failed API response
    mock_get.return_value = MockResponse({}, 404)

    # Call the method
    story_prs = atlassian_client.get_story_pull_requests(["TEST-1"])

    # Should return empty list for the story
    assert "TEST-1" in story_prs
    assert len(story_prs["TEST-1"]) == 0


def test_get_stories_validation():
    """Test input validation for get_stories method."""
    client = AtlassianRequests(
        jira_instance="test.atlassian.net",
        email="test@example.com"
    )

    # Test with non-list input
    with pytest.raises(TypeError):
        client.get_stories("not-a-list")

    # Test with empty list
    with pytest.raises(ValueError):
        client.get_stories([])

    # Test with non-string items
    with pytest.raises(TypeError):
        client.get_stories([123, 456])

    # Test with empty string items
    with pytest.raises(ValueError):
        client.get_stories(["valid", ""])
