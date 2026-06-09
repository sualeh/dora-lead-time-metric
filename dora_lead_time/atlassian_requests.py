"""Atlassian API requests to Jira."""

import logging
import os
import textwrap
from datetime import date, datetime
from urllib.parse import urlparse
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

JIRA_PAGE_SIZE = 25
PROGRESS_LOG_INTERVAL = 25


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

    def _build_dev_detail_query_variants(
        self,
        issue_id: str,
    ) -> list[str]:
        """Build ordered detail query variants for GitHub integrations."""

        query_variants = [
            (
                f"issueId={issue_id}&applicationType=GitHub"
                "&dataType=pullrequest"
            ),
            (
                "issueId="
                f"{issue_id}&applicationType="
                "oAuth-com.github.integration.production"
                "&dataType=pullrequest"
            ),
            (
                f"issueId={issue_id}&applicationType=GitHub"
                "&applicationId=oAuth-com.github.integration.production"
                "&dataType=pullrequest"
            ),
        ]

        return list(dict.fromkeys(query_variants))

    def _to_pull_request_identifier(
        self, pr_url: str
    ) -> PullRequestIdentifier | None:
        """Convert a GitHub PR URL to PullRequestIdentifier."""

        parsed = urlparse(pr_url)
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 4 or path_parts[2] != "pull":
            logger.warning("Skipping unsupported pull request URL: %s", pr_url)
            return None

        owner = path_parts[0]
        repo = path_parts[1]
        pr_number = path_parts[3]
        if not pr_number.isdigit():
            logger.warning(
                "Skipping pull request URL with invalid id: %s",
                pr_url,
            )
            return None

        return PullRequestIdentifier(
            id=None,
            pr_owner=owner,
            pr_repository=repo,
            pr_number=pr_number,
        )

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
    ) -> List[tuple]:
        """Retrieve stories by fix version IDs from Jira.

        Args:
            releases: List of Jira fix version IDs as strings

        Returns:
            List[tuple]: List of (Story, release_internal_id) pairs where
            Story contains (story_key, story_title, story_type,
            story_created, story_resolved) and release_internal_id is the
            Jira fix version ID that links the story to a release.

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
        issues_processed = 0
        max_results = JIRA_PAGE_SIZE
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

            logger.info(
                "Fetching next issues batch after %s issues processed",
                issues_processed,
            )
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
                            story_internal_id=issue["id"],
                            story_key=issue["key"],
                            story_title=issue["fields"]["summary"],
                            story_type=issue["fields"]["issuetype"]["name"],
                            story_created=created,
                            story_resolved=resolved,
                        )
                        all_stories.append((story_details, release["id"]))

            # Move to next batch
            issues_processed += len(data["issues"])
            logger.info(
                textwrap.dedent("""
                    Retrieved %d issues in current batch
                    Issues processed so far: %d
                    (Story-release pair count may exceed unique issues
                    when stories belong to more than one release)
                    Total story-release pairs retrieved: %d
                """).strip(),
                len(data["issues"]),
                issues_processed,
                len(all_stories),
            )

            # Safety check - if we got an empty batch but haven't reached
            # total, something is wrong
            if len(data["issues"]) == 0 and next_page_token is not None:
                logger.warning(
                    "Received empty batch but more issues are expected"
                )
                break

        logger.info("Total story rows retrieved: %d", len(all_stories))
        return all_stories

    def get_story_pull_requests(
        self,
        story_numbers: list[tuple[str, str | None]],
    ) -> Dict[str, List[PullRequestIdentifier]]:
        """
        Retrieves GitHub pull request information associated with given Jira
        story numbers.

        Queries Jira's development information API to find all GitHub pull
        requests linked to the specified stories.

        Args:
            story_numbers: List of story records as tuples
                (story_key, story_internal_id), e.g.
                [('SRTN-864', '12345'), ('SRTN-865', '12346')]

        Returns:
            Dict[str, List[PullRequestIdentifier]]: A dictionary mapping
            story numbers to lists of associated GitHub pull request objects.
            Each PR is represented as a PullRequestIdentifier named tuple
            of PullRequestIdentifier.
            Empty list is returned for stories with no PRs or if there are
            API errors.

        Raises:
            ValueError: If story_numbers is empty or contains empty strings
            TypeError: If story entries are invalid
        """
        # Validate input
        if not story_numbers:
            raise ValueError("story_numbers list cannot be empty")

        for story in story_numbers:
            if not isinstance(story, tuple) or len(story) != 2:
                raise TypeError(
                    "story entries must be (story_key, story_internal_id) "
                    "tuples"
                )

        invalid_story_keys = [
            story_key
            for story_key, _ in story_numbers
            if not isinstance(story_key, str) or not story_key.strip()
        ]
        if invalid_story_keys:
            raise ValueError("Story numbers cannot be empty strings")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        auth = (self.email, self.token)

        total_stories = len(story_numbers)
        stories_attempted = 0
        stories_processed = 0
        stories_processed_without_prs = 0
        failed_story_requests = 0
        story_to_pr_urls = {}
        for story, issue_id in story_numbers:
            stories_attempted += 1

            if issue_id is None:
                logger.error(
                    "Missing story_internal_id for story %s; skipping",
                    story,
                )
                failed_story_requests += 1
                story_to_pr_urls[story] = []
                continue

            # Then get development information using the issue id.
            # Jira Cloud tenants can require different combinations here.
            query_variants = self._build_dev_detail_query_variants(
                issue_id=issue_id,
            )

            dev_data = {"detail": []}
            detail_found = False
            for query in query_variants:
                dev_url = (
                    "https://"
                    f"{self.jira_instance}/rest/dev-status/latest/issue/"
                    f"detail?{query}"
                )
                dev_response = api_get(
                    dev_url,
                    ApiSource.ATLASSIAN,
                    headers,
                    auth=auth,
                    timeout=self.request_timeout,
                    raise_on_error=False,
                )

                # Only stop once pull request detail is found.
                try:
                    dev_data = dev_response.json()
                except ValueError:
                    dev_data = {"detail": []}

                if dev_data.get("detail"):
                    detail_found = True
                    break

            if not detail_found:
                logger.info(
                    "No pull request detail returned for %s (issueId=%s)",
                    story,
                    issue_id,
                )

            pr_urls = []

            # Extract PR URLs from development data
            detail = dev_data.get("detail", [])
            for repository in detail:
                for pr in repository.get("pullRequests", []):
                    if "url" in pr:
                        pull_request = self._to_pull_request_identifier(
                            pr["url"]
                        )
                        if pull_request is not None:
                            pr_urls.append(pull_request)

            story_to_pr_urls[story] = pr_urls

            # Log progress
            stories_processed += 1
            if not pr_urls:
                stories_processed_without_prs += 1
            if (
                stories_attempted % PROGRESS_LOG_INTERVAL == 0
                or stories_attempted == total_stories
            ):
                logger.info(
                    "Attempted %d/%d stories; %d successful lookups, "
                    "%d failed lookups, %d stories without PRs",
                    stories_attempted,
                    total_stories,
                    stories_processed,
                    failed_story_requests,
                    stories_processed_without_prs,
                )
        logger.info(
            "Completed story PR lookup: %d/%d attempted, %d successful, "
            "%d failed, %d without PRs",
            stories_attempted,
            total_stories,
            stories_processed,
            failed_story_requests,
            stories_processed_without_prs,
        )

        return story_to_pr_urls


def main():
    """Main entry point of the application."""
    # Prevent loading
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
