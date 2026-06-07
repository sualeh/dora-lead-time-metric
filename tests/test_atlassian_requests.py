"""Unit tests for the AtlassianRequests class."""

import os
import pytest
import unittest.mock as mock
import json
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from dora_lead_time.atlassian_requests import (
    AtlassianRequests,
    ConfigurationError,
)
from dora_lead_time.api_client import ApiError, AuthError, RateLimitError
from dora_lead_time.database_processor import DatabaseOperationError
from dora_lead_time.models import Project, Release, PullRequestIdentifier


class MockResponse:
    """Mock response for requests."""

    def __init__(self, json_data, status_code=200, headers=None):
        self.json_data = json_data
        self.status_code = status_code
        self.text = json.dumps(json_data)
        self.headers = headers or {}

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
        with patch("requests.get") as mock_get:
            mock_get.return_value = MockResponse({"accountId": "12345"})
            return AtlassianRequests()


def test_init_with_params():
    """Test initialization with explicit parameters."""
    with patch("requests.get") as mock_get:
        mock_get.return_value = MockResponse({"accountId": "12345"})
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
        with patch("requests.get") as mock_get:
            mock_get.return_value = MockResponse({"accountId": "12345"})
            client = AtlassianRequests()
        assert client.jira_instance == "env.atlassian.net"
        assert client.email == "env@example.com"
        assert client.token == "env-token"


def test_init_missing_credentials():
    """Test initialization with missing credentials."""
    with patch.dict(os.environ, {}, clear=True), patch(
        "dora_lead_time.atlassian_requests.load_dotenv"
    ):
        with pytest.raises(ConfigurationError):
            AtlassianRequests()


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
        params=None,
        timeout=30,
    )


@patch("requests.get")
def test_get_projects_raises_auth_error_when_zero_projects_and_unauthorized(
    mock_get, atlassian_client
):
    """Fail fast when Jira projects endpoint returns 401/403."""

    mock_get.return_value = MockResponse({}, status_code=401)

    with pytest.raises(AuthError, match="Authentication failed"):
        atlassian_client.get_projects()


@patch("requests.get")
def test_get_projects_empty_raises_configuration_error(
    mock_get, atlassian_client
):
    """No visible software projects should be a configuration error."""
    mock_get.return_value = MockResponse([])

    with pytest.raises(ConfigurationError, match="no visible software"):
        atlassian_client.get_projects()


@patch("requests.get")
def test_get_releases(mock_get, atlassian_client):
    """Test getting releases from Jira."""
    projects = [
        Project(
            id=None,
            project_internal_id="10000",
            project_key="TEST",
            project_title="Test",
            project_type="software",
        ),
        Project(
            id=None,
            project_internal_id="10001",
            project_key="DEV",
            project_title="Dev",
            project_type="software",
        ),
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
        if url == "https://test.atlassian.net/rest/api/3/project/TEST/versions":
            return MockResponse(mock_test_versions)
        if url == "https://test.atlassian.net/rest/api/3/project/DEV/versions":
            return MockResponse(mock_dev_versions)
        return MockResponse({}, 404)

    mock_get.side_effect = side_effect

    # Call the method with date range that includes some but not all releases
    start_date = date(2023, 6, 1)
    end_date = date(2023, 7, 31)
    releases = atlassian_client.get_releases(
        start_date,
        end_date,
        projects=projects,
    )

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
def test_get_releases_uses_prefetched_projects(mock_get, atlassian_client):
    """Use provided projects and skip additional Jira project lookup."""
    projects = [
        Project(
            id=None,
            project_internal_id="10000",
            project_key="TEST",
            project_title="Test Project",
            project_type="software",
        )
    ]
    mock_versions = [
        {
            "id": "10000",
            "name": "1.0.0",
            "description": "First release",
            "releaseDate": "2023-06-15T00:00:00Z",
            "released": True,
        },
    ]

    def side_effect(*args, **kwargs):
        url = args[0]
        if url == "https://test.atlassian.net/rest/api/3/project/TEST/versions":
            return MockResponse(mock_versions)
        return MockResponse({}, 404)

    mock_get.side_effect = side_effect

    releases = atlassian_client.get_releases(
        date(2023, 6, 1),
        date(2023, 7, 31),
        projects=projects,
    )

    assert len(releases) == 1
    requested_urls = [call.args[0] for call in mock_get.call_args_list]
    assert "https://test.atlassian.net/rest/api/3/project" not in requested_urls


def test_get_releases_empty_prefetched_projects_raises_database_error(
    atlassian_client,
):
    """Empty provided project list should fail as a database error."""
    with pytest.raises(DatabaseOperationError, match="No software projects"):
        atlassian_client.get_releases(
            date(2023, 6, 1),
            date(2023, 7, 31),
            projects=[],
        )


def test_get_releases_non_software_prefetched_projects_raises_database_error(
    atlassian_client,
):
    """Provided projects with no software type should fail."""
    projects = [
        Project(
            id=None,
            project_internal_id="10002",
            project_key="HELP",
            project_title="Help Desk",
            project_type="service_desk",
        )
    ]

    with pytest.raises(DatabaseOperationError, match="No software projects"):
        atlassian_client.get_releases(
            date(2023, 6, 1),
            date(2023, 7, 31),
            projects=projects,
        )


@patch("requests.get")
def test_get_releases_fetched_non_software_projects_raises_database_error(
    mock_get, atlassian_client
):
    """Missing projects input should fail for projects-only contract."""
    mock_get.return_value = MockResponse({})

    with pytest.raises(DatabaseOperationError, match="Projects are required"):
        atlassian_client.get_releases(date(2023, 6, 1), date(2023, 7, 31))


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
    with patch("requests.get") as mock_get:
        mock_get.return_value = MockResponse({"accountId": "12345"})
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


@pytest.mark.parametrize("status_code", [401, 403])
@patch("requests.get")
def test_get_projects_auth_error(mock_get, status_code, atlassian_client):
    """Test that 401/403 on get_projects raises AuthError."""
    mock_get.return_value = MockResponse({}, status_code)

    with pytest.raises(AuthError):
        atlassian_client.get_projects()


@pytest.mark.parametrize("status_code", [401, 403])
@patch("requests.get")
def test_get_releases_auth_error(mock_get, status_code, atlassian_client):
    """Test that 401/403 on versions request in get_releases raises AuthError."""
    mock_get.return_value = MockResponse({}, status_code)
    projects = [
        Project(
            id=None,
            project_internal_id="10000",
            project_key="TEST",
            project_title="Test",
            project_type="software",
        )
    ]

    with pytest.raises(AuthError):
        atlassian_client.get_releases(
            start_date=__import__("datetime").date(2023, 1, 1),
            end_date=__import__("datetime").date(2023, 12, 31),
            projects=projects,
        )


@pytest.mark.parametrize("status_code", [401, 403])
@patch("requests.get")
def test_get_releases_versions_auth_error(
    mock_get, status_code, atlassian_client
):
    """Test that 401/403 on per-project versions in get_releases raises AuthError."""
    projects = [
        Project(
            id=None,
            project_internal_id="10000",
            project_key="TEST",
            project_title="Test",
            project_type="software",
        )
    ]
    mock_get.return_value = MockResponse({}, status_code)

    with pytest.raises(AuthError):
        atlassian_client.get_releases(
            start_date=__import__("datetime").date(2023, 1, 1),
            end_date=__import__("datetime").date(2023, 12, 31),
            projects=projects,
        )


@pytest.mark.parametrize("status_code", [401, 403])
@patch("requests.get")
def test_get_stories_auth_error(mock_get, status_code, atlassian_client):
    """Test that 401/403 on get_stories raises AuthError."""
    mock_get.return_value = MockResponse({}, status_code)

    with pytest.raises(AuthError):
        atlassian_client.get_stories(["10000"])


@pytest.mark.parametrize("status_code", [401, 403])
@patch("requests.get")
def test_get_story_pull_requests_issue_auth_error(
    mock_get, status_code, atlassian_client
):
    """Test that 401/403 on issue lookup in get_story_pull_requests raises AuthError."""
    mock_get.return_value = MockResponse({}, status_code)

    with pytest.raises(AuthError):
        atlassian_client.get_story_pull_requests(["TEST-1"])


@pytest.mark.parametrize("status_code", [401, 403])
@patch("requests.get")
def test_get_story_pull_requests_dev_auth_error(
    mock_get, status_code, atlassian_client
):
    """Test that 401/403 on dev-status in get_story_pull_requests raises AuthError."""
    mock_issue_response = {"id": "12345"}

    def side_effect(*args, **kwargs):
        url = args[0]
        if "rest/api/3/issue" in url:
            return MockResponse(mock_issue_response)
        return MockResponse({}, status_code)

    mock_get.side_effect = side_effect

    with pytest.raises(AuthError):
        atlassian_client.get_story_pull_requests(["TEST-1"])


@patch("requests.get")
def test_get_projects_rate_limit_error(mock_get, atlassian_client):
    """Test that a 429 on get_projects raises RateLimitError."""
    mock_get.return_value = MockResponse(
        {}, 429, headers={"Retry-After": "60"}
    )
    with pytest.raises(RateLimitError):
        atlassian_client.get_projects()


@patch("requests.get")
def test_get_stories_rate_limit_error(mock_get, atlassian_client):
    """Test that a 429 on get_stories raises RateLimitError."""
    mock_get.return_value = MockResponse({}, 429)
    with pytest.raises(RateLimitError):
        atlassian_client.get_stories(["10000"])


@patch("requests.get")
def test_get_story_pull_requests_issue_rate_limit_error(
    mock_get, atlassian_client
):
    """Test that a 429 on issue lookup raises RateLimitError."""
    mock_get.return_value = MockResponse({}, 429)
    with pytest.raises(RateLimitError):
        atlassian_client.get_story_pull_requests(["TEST-1"])


@patch("requests.get")
def test_get_story_pull_requests_dev_rate_limit_error(
    mock_get, atlassian_client
):
    """Test that a 429 on dev-status raises RateLimitError."""
    mock_issue_response = {"id": "12345"}

    def side_effect(*args, **kwargs):
        url = args[0]
        if "rest/api/3/issue" in url:
            return MockResponse(mock_issue_response)
        return MockResponse({}, 429)

    mock_get.side_effect = side_effect

    with pytest.raises(RateLimitError):
        atlassian_client.get_story_pull_requests(["TEST-1"])


@pytest.mark.parametrize("status_code", [404, 500, 503])
@patch("requests.get")
def test_get_projects_api_error(mock_get, status_code, atlassian_client):
    """Test that 4xx/5xx on get_projects raises ApiError."""
    mock_get.return_value = MockResponse({}, status_code)
    with pytest.raises(ApiError):
        atlassian_client.get_projects()


@pytest.mark.parametrize("status_code", [404, 500, 503])
@patch("requests.get")
def test_get_releases_structural_api_error(
    mock_get, status_code, atlassian_client
):
    """Test that 4xx/5xx on versions request is skipped, not raised."""
    mock_get.return_value = MockResponse({}, status_code)
    projects = [
        Project(
            id=None,
            project_internal_id="10000",
            project_key="TEST",
            project_title="Test",
            project_type="software",
        )
    ]
    releases = atlassian_client.get_releases(
        start_date=__import__("datetime").date(2023, 1, 1),
        end_date=__import__("datetime").date(2023, 12, 31),
        projects=projects,
    )
    assert releases == []


@pytest.mark.parametrize("status_code", [404, 500, 503])
@patch("requests.get")
def test_get_stories_api_error(mock_get, status_code, atlassian_client):
    """Test that 4xx/5xx on get_stories raises ApiError."""
    mock_get.return_value = MockResponse({}, status_code)
    with pytest.raises(ApiError):
        atlassian_client.get_stories(["10000"])


@patch("requests.get")
def test_get_releases_versions_non_200_skips(mock_get, atlassian_client):
    """Test that per-project versions errors are skipped, not raised."""
    projects = [
        Project(
            id=None,
            project_internal_id="10000",
            project_key="TEST",
            project_title="Test",
            project_type="software",
        )
    ]
    mock_get.return_value = MockResponse({}, 404)

    # Should return empty list, not raise
    releases = atlassian_client.get_releases(
        start_date=__import__("datetime").date(2023, 1, 1),
        end_date=__import__("datetime").date(2023, 12, 31),
        projects=projects,
    )
    assert releases == []
