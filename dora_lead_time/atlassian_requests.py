"""Atlassian API requests to Jira."""

import logging
import os
import textwrap
from datetime import date, datetime
from typing import Dict, List, cast
from dotenv import load_dotenv

from dora_lead_time.api_client import (
    ApiSource,
    api_get,
)
from dora_lead_time.models import (
    Project,
    Release,
    Story,
    PullRequestIdentifier,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
)
logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when required application configuration is missing."""


class AtlassianRequests:
    """Atlassian API requests to Jira."""

    def __init__(
        self, jira_instance=None, email=None, request_timeout=30
    ):
        """Initialize the Atlassian API client with credentials.

        Args:
            jira_instance (str, optional): Jira instance URL.
                Defaults to environmental variable value for
                JIRA_INSTANCE.
            email (str, optional): Atlassian account email.
                Defaults to environmental variable value for
                EMAIL.
            request_timeout (int, optional): HTTP request timeout in seconds.
                Defaults to 30.

        Raises:
            ConfigurationError: If required credentials cannot be found
            AuthError: If Atlassian authentication fails
        """
        load_dotenv()

        jira_instance_value = jira_instance or os.getenv("JIRA_INSTANCE")
        email_value = email or os.getenv("EMAIL")
        token_value = os.getenv("ATLASSIAN_TOKEN")
        self.request_timeout = request_timeout

        if not all([jira_instance_value, email_value, token_value]):
            raise ConfigurationError(
                "Missing required credentials. "
                "Ensure JIRA_INSTANCE, EMAIL, and ATLASSIAN_TOKEN "
                "are provided or set as environment variables."
            )

        self.jira_instance = cast(str, jira_instance_value)
        self.email = cast(str, email_value)
        self.token = cast(str, token_value)

        self._verify_authentication()

    def _verify_authentication(self) -> dict:
        """Verify Jira credentials and log the authenticated identity."""

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        auth = (self.email, self.token)
        myself_url = f"https://{self.jira_instance}/rest/api/3/myself"
        response = api_get(
            myself_url,
            ApiSource.ATLASSIAN,
            headers,
            auth=auth,
            timeout=self.request_timeout,
        )

        user_info = response.json()
        logger.info(
            "Authenticated Jira user: (name=%s, url=%s)",
            user_info.get("displayName"),
            user_info.get("self"),
        )
        return user_info

    def get_projects(self) -> List[Project]:
        """Get all projects from Jira.

        Returns:
            List[Project]: List of Project named tuples containing
                (project_internal_id, project_key, project_title, project_type)

        Raises:
            ConfigurationError: If Jira returns no visible software projects.
            AuthError: If authentication fails (HTTP 401/403).
            RateLimitError: If rate limit is exceeded (HTTP 429).
            ApiError: If Jira returns an unrecoverable 4xx/5xx response.
            requests.RequestException: If there's an error connecting to Jira
        """

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        auth = (self.email, self.token)
        projects_url = f"https://{self.jira_instance}/rest/api/3/project"
        response = api_get(
            projects_url, ApiSource.ATLASSIAN, headers,
            auth=auth, timeout=self.request_timeout,
        )
        all_projects = response.json()

        projects = [
            Project(
                id=None,
                project_internal_id=project["id"],
                project_key=project["key"],
                project_title=project["name"],
                project_type=project["projectTypeKey"],
            )
            for project in all_projects
            if project.get("projectTypeKey") == "software"
        ]
        if not projects:
            raise ConfigurationError(
                "Atlassian returned no visible software projects. "
                "Verify project access and configuration."
            )
        projects = sorted(projects, key=lambda x: x.project_title)
        return projects

    def get_releases(
        self,
        start_date: date,
        end_date: date,
        projects: list[Project] | None = None,
    ) -> List[Release]:
        """Get all released versions between two dates for specified projects.

        Args:
            start_date (date): Start date for release search (inclusive)
            end_date (date): End date for release search (inclusive)
            projects (list[Project] | None): Pre-fetched Jira projects.
                Required. Projects are not fetched in this method.

        Returns:
            List[Release]: List of Release named tuples

        Raises:
            ConfigurationError: If projects is missing or has no
                software projects.
            AuthError: If authentication fails (HTTP 401/403).
            RateLimitError: If rate limit is exceeded (HTTP 429).
            requests.RequestException: If there's an error connecting to Jira
        """

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        auth = (self.email, self.token)
        jira_base_url = f"https://{self.jira_instance}/rest/api/3"

        if projects is None:
            raise ConfigurationError(
                "Projects are required to retrieve releases"
            )

        project_keys = [
            project.project_key
            for project in projects
            if project.project_type == "software"
        ]

        if not project_keys:
            raise ConfigurationError(
                "No software projects available to retrieve releases"
            )

        releases = []
        for project_key in project_keys:
            url = f"{jira_base_url}/project/{project_key}/versions"
            response = api_get(
                url, ApiSource.ATLASSIAN, headers,
                auth=auth, timeout=self.request_timeout,
                raise_on_error=False,
            )
            if response.status_code != 200:
                logger.warning(
                    "Could not fetch versions for project %s "
                    "(HTTP %s); skipping",
                    project_key, response.status_code
                )
                continue

            versions = response.json()
            for version in versions:
                if "releaseDate" in version and version.get("released", False):
                    release_date = datetime.fromisoformat(
                        version["releaseDate"].replace("Z", "+00:00")
                    ).date()
                    if start_date <= release_date <= end_date:
                        release = Release(
                            id=None,
                            release_internal_id=version["id"],
                            release_title=version["name"],
                            release_description=version.get("description"),
                            release_date=release_date,
                            project_key=project_key,
                        )
                        releases.append(release)

        unique_releases = list(set(releases))

        return unique_releases

    def get_stories(
        self, releases: list[str],
    ) -> List[Story]:
        """Retrieve stories by fix version IDs from Jira.

        Args:
            releases: List of Jira fix version IDs as strings

        Returns:
            List[Story]: List of Story named tuples containing:
            (story_key, story_title, story_type, story_created, story_resolved,
            release_id)

        Raises:
            TypeError: If releases parameter is not a list or does not
                contain strings
            ValueError: If releases list is empty or contains empty strings
            requests.RequestException: If there's an error connecting to Jira
        """
        # Validate input
        if not isinstance(releases, list):
            raise TypeError("releases must be a list")
        if not releases:
            raise ValueError("releases cannot be empty")
        if not all(isinstance(v, str) for v in releases):
            raise TypeError("all releases must be strings")
        if not all(v.strip() for v in releases):
            raise ValueError("releases cannot be empty strings")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        auth = (self.email, self.token)
        url = f"https://{self.jira_instance}/rest/api/3/search/jql"
        releases_str = ",".join(releases)
        jql_query = f"""
        fixVersion IN ({releases_str})
        AND issuetype NOT IN ('Sub-task', "Feature", "Epic")
        """

        # Initialize variables for pagination
        start_at = 0
        max_results = 25
        all_stories = []
        is_last = False
        next_page_token = None

        # Fetch all pages of results
        while not is_last:
            params = {
                "jql": jql_query,
                "maxResults": max_results,
                "nextPageToken": next_page_token,
                "fields": (
                    "fixVersions,key,summary,issuetype,"
                    "created,resolutiondate"
                ),
            }

            logger.info("Fetching stories batch starting at %s", start_at)
            response = api_get(
                url, ApiSource.ATLASSIAN, headers,
                auth=auth, params=params, timeout=self.request_timeout,
            )

            data = response.json()
            is_last = data.get("isLast", False)
            next_page_token = data.get("nextPageToken")

            # Process current batch of issues
            for issue in data["issues"]:
                created = datetime.fromisoformat(
                    issue["fields"]["created"].replace("Z", "+00:00")
                )
                resolved = (
                    datetime.fromisoformat(
                        issue["fields"]["resolutiondate"].replace(
                            "Z", "+00:00"
                        )
                    )
                    if issue["fields"]["resolutiondate"]
                    else None
                )
                for release in issue["fields"]["fixVersions"]:
                    if release["id"] in releases:
                        story_details = Story(
                            id=None,
                            story_key=issue["key"],
                            story_title=issue["fields"]["summary"],
                            story_type=issue["fields"]["issuetype"]["name"],
                            story_created=created,
                            story_resolved=resolved,
                            release_id=release["id"],
                        )
                        all_stories.append(story_details)

            # Move to next batch
            start_at += len(data["issues"])
            logger.info(
                textwrap.dedent("""
                    Retrieved %d stories, for batch starting at %d
                    (Story counts may not match if they are part of
                    more than one release)
                    Total stories retrieved: %d
                """).strip(),
                len(data["issues"]),
                start_at,
                len(all_stories)
            )

            # Safety check - if we got an empty batch but haven't reached
            # total, something is wrong
            if len(data["issues"]) == 0 and next_page_token is not None:
                logger.warning(
                    "Received empty batch but more stories are expected"
                )
                break

        logger.info("Total stories retrieved: %d", len(all_stories))
        return all_stories

    def get_story_pull_requests(
        self, story_numbers: list[str],
    ) -> Dict[str, List[PullRequestIdentifier]]:
        """
        Retrieves GitHub pull request information associated with given Jira
        story numbers.

        Queries Jira's development information API to find all GitHub pull
        requests linked to the specified stories.

        Args:
            story_numbers: List of Jira story identifiers
                (e.g., ['SRTN-864', 'SRTN-865'])

        Returns:
            Dict[str, List[PullRequestIdentifier]]: A dictionary mapping
            story numbers to lists of associated GitHub pull request objects.
            Each PR is represented as a PullRequestIdentifier named tuple
            of PullRequestIdentifier.
            Empty list is returned for stories with no PRs or if there are
            API errors.

        Raises:
            ValueError: If story_numbers is empty or contains empty strings
        """
        # Validate input
        if not story_numbers:
            raise ValueError("story_numbers list cannot be empty")

        invalid_stories = [s for s in story_numbers if not s]
        if invalid_stories:
            raise ValueError("Story numbers cannot be empty strings")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        auth = (self.email, self.token)

        stories_processed = 0
        stories_processed_without_prs = 0
        story_to_pr_urls = {}
        for story in story_numbers:
            # First get the issue id
            issue_url = (
                f"https://{self.jira_instance}/rest/api/3/issue/"
                f"{story}?fields=id"
            )
            issue_response = api_get(
                issue_url, ApiSource.ATLASSIAN, headers,
                auth=auth, timeout=self.request_timeout,
                raise_on_error=False,
            )

            if issue_response.status_code != 200:
                logger.error(
                    "Error getting issue %s: %s - %s",
                    story,
                    issue_response.status_code,
                    issue_response.text,
                )
                story_to_pr_urls[story] = []
                continue

            issue_data = issue_response.json()
            issue_id = issue_data["id"]

            # Then get development information using the issue id
            dev_url = (
                "https://"
                f"{self.jira_instance}/rest/dev-status/latest/issue/detail"
                f"?issueId={issue_id}"
                f"&applicationType=GitHub"
                f"&dataType=pullrequest"
            )
            dev_response = api_get(
                dev_url, ApiSource.ATLASSIAN, headers,
                auth=auth, timeout=self.request_timeout,
                raise_on_error=False,
            )

            if dev_response.status_code != 200:
                logger.error(
                    "Error getting development info for %s: %s - %s",
                    story,
                    dev_response.status_code,
                    dev_response.text,
                )
                story_to_pr_urls[story] = []
                continue

            dev_data = dev_response.json()
            pr_urls = []

            # Extract PR URLs from development data
            detail = dev_data.get("detail", [])
            for repository in detail:
                for pr in repository.get("pullRequests", []):
                    if "url" in pr:
                        # Parse URL to get owner, repo, and PR number
                        parts = pr["url"].split("/")
                        owner = parts[3]
                        repo = parts[4]
                        pr_number = str(int(parts[6]))
                        pull_request = PullRequestIdentifier(
                            id=None,
                            pr_owner=owner,
                            pr_repository=repo,
                            pr_number=pr_number
                        )
                        pr_urls.append(pull_request)

            story_to_pr_urls[story] = pr_urls

            # Log progress
            stories_processed += 1
            if not pr_urls:
                stories_processed_without_prs += 1
            if stories_processed % 25 == 0:
                logger.info(
                    "Processed %d stories, %d without PRs",
                    stories_processed,
                    stories_processed_without_prs,
                )
        logger.info(
            "Processed %d stories, %d without PRs",
            stories_processed,
            stories_processed_without_prs,
        )

        return story_to_pr_urls


def main():
    """Main entry point of the application."""
    # Prevent loading
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
