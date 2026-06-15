"""GitHub API requests."""

import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from dora_lead_time.api_client import ApiSource, api_get
from dora_lead_time.models import PullRequestIdentifier, PullRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
)
logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30  # Timeout in seconds for HTTP requests
PROGRESS_LOG_INTERVAL = 25


class GitHubRequests:
    """GitHub API requests."""

    def __init__(
        self, org_to_env_var_map: dict[str, str], request_timeout: int = 30
    ):
        """
        Initialize with a mapping of organizations to environment variable
            names.

        Args:
            org_to_env_var_map (dict[str, str]): Mapping of organization names
                to environment variable names that contain GitHub tokens
            request_timeout (int, optional): Timeout in seconds for
                HTTP requests.
                Defaults to 30.
        """
        load_dotenv()

        self.github_token_map = {}
        self.request_timeout = request_timeout

        # Look up token values from environment variables
        for org, env_var_name in org_to_env_var_map.items():
            token = os.getenv(env_var_name)
            if token:
                self.github_token_map[org] = token
            else:
                logger.warning(
                    "No GitHub token found for environment variable %s",
                    env_var_name
                )

        self._verify_authentication()

    def _verify_authentication(self) -> None:
        """Verify each configured GitHub token and log identity details."""
        if not self.github_token_map:
            return

        for org, github_token in self.github_token_map.items():
            headers = {"Authorization": f"token {github_token}"}
            user_response = api_get(
                "https://api.github.com/user",
                ApiSource.GITHUB,
                headers,
                timeout=self.request_timeout,
            )
            user_info = user_response.json()
            logger.info(
                "Authenticated GitHub user for %s: (name=%s, url=%s)",
                org,
                user_info.get("name"),
                user_info.get("html_url") or user_info.get("url"),
            )

    @staticmethod
    def _get_next_page_url(response) -> str | None:
        """Get the next pagination URL from a GitHub response."""
        link_header = response.headers.get("Link")
        if not link_header:
            return None

        for part in link_header.split(","):
            section = part.strip().split(";")
            if len(section) < 2:
                continue
            url_part = section[0].strip()
            rel_part = section[1].strip()
            if rel_part != 'rel="next"':
                continue
            if not url_part.startswith("<") or not url_part.endswith(">"):
                continue
            return url_part[1:-1]

        return None

    def _get_all_pr_commits(
        self,
        commits_url: str,
        headers: dict[str, str],
    ) -> list[dict]:
        """Fetch all PR commit pages from GitHub."""
        commits: list[dict] = []
        next_url = f"{commits_url}?per_page=100"

        while next_url:
            commits_response = api_get(
                next_url,
                ApiSource.GITHUB,
                headers,
                timeout=self.request_timeout,
                raise_on_error=False,
            )
            if commits_response.status_code != 200:
                logger.warning(
                    "Could not fetch commits for PR at %s (HTTP %s); commit "
                    "data will be incomplete",
                    next_url,
                    commits_response.status_code,
                )
                break

            page_commits = commits_response.json()
            commits.extend(page_commits)
            next_url = self._get_next_page_url(commits_response)

        return commits

    def get_pull_request_details(
        self, pull_requests: list[PullRequestIdentifier]
    ) -> tuple[list[PullRequest], list[int]]:
        """
        Retrieves detailed information about each GitHub pull request.

        Args:
            pull_requests (list[PullRequestIdentifier]): A list of
                PullRequestIdentifier

        Returns:
            tuple[list[PullRequest], list[int]]: A tuple containing:
                - A list of successfully fetched PullRequest objects
                - A list of PR IDs that failed with 404 errors

        Raises:
            ValueError: If GitHub token is not provided
            requests.RequestException: If there's an error connecting to GitHub
        """
        if not pull_requests:
            return [], []
        if not self.github_token_map:
            raise ValueError("No GitHub tokens available in token map")

        pr_details = []
        pr_fetch_failures_404 = []

        total_prs = len(pull_requests)
        prs_attempted = 0
        pr_processed = 0
        pr_failed = 0
        for pr in pull_requests:
            prs_attempted += 1

            owner = pr.pr_owner
            repo = pr.pr_repository
            pr_number = pr.pr_number

            github_token = self.github_token_map.get(owner)
            if not github_token:
                logger.error(
                    "No GitHub token found for organization: %s", owner
                )
                pr_failed += 1
                if (
                    prs_attempted % PROGRESS_LOG_INTERVAL == 0
                    or prs_attempted == total_prs
                ):
                    logger.info(
                        "Attempted %d/%d PRs; %d successful, %d failed",
                        prs_attempted,
                        total_prs,
                        pr_processed,
                        pr_failed,
                    )
                continue

            headers = {"Authorization": f"token {github_token}"}

            api_url = (
                f"https://api.github.com/repos/{owner}/{repo}/pulls/"
                f"{pr_number}"
            )
            response = api_get(
                api_url, ApiSource.GITHUB, headers,
                timeout=self.request_timeout, raise_on_error=False,
            )
            if response.status_code != 200:
                if response.status_code == 404:
                    pr_fetch_failures_404.append(pr.id)
                logger.warning(
                    "Could not fetch PR details for %s/%s/%s "
                    "(HTTP %s); skipping",
                    owner, repo, pr_number, response.status_code
                )
                pr_failed += 1
                if (
                    prs_attempted % PROGRESS_LOG_INTERVAL == 0
                    or prs_attempted == total_prs
                ):
                    logger.info(
                        "Attempted %d/%d PRs; %d successful, %d failed",
                        prs_attempted,
                        total_prs,
                        pr_processed,
                        pr_failed,
                    )
                continue
            pr_data = response.json()

            closed_date = (
                datetime.fromisoformat(
                    pr_data["closed_at"].replace("Z", "+00:00")
                ).date()
                if pr_data["closed_at"]
                else None
            )

            # Get commit data
            commits_url = f"{api_url}/commits"
            commits = self._get_all_pr_commits(commits_url, headers)

            # Get earliest and latest commit date
            commit_dates = []
            for commit in commits:
                commit_date = commit["commit"]["committer"]["date"]
                commit_dates.append(
                    datetime.fromisoformat(commit_date.replace("Z", "+00:00"))
                    .date()
                )
            earliest_commit_date = min(commit_dates) if commit_dates else None
            latest_commit_date = max(commit_dates) if commit_dates else None

            # Find PR open date from pr_data
            created_date = (
                datetime.fromisoformat(
                    pr_data["created_at"].replace("Z", "+00:00")
                ).date()
                if pr_data["created_at"]
                else None
            )

            # Replace tuple creation with named tuple
            pr_detail = PullRequest(
                id=pr.id,
                pr_title=pr_data["title"],
                open_date=created_date,
                close_date=closed_date,
                commit_count=len(commits),
                changed_files=pr_data.get("changed_files"),
                earliest_commit_date=earliest_commit_date,
                latest_commit_date=latest_commit_date,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
            )
            pr_details.append(pr_detail)

            # Log progress
            pr_processed = pr_processed + 1
            if (
                prs_attempted % PROGRESS_LOG_INTERVAL == 0
                or prs_attempted == total_prs
            ):
                logger.info(
                    "Attempted %d/%d PRs; %d successful, %d failed",
                    prs_attempted,
                    total_prs,
                    pr_processed,
                    pr_failed,
                )
        logger.info(
            "Completed PR detail lookup: %d/%d attempted, %d successful, "
            "%d failed",
            prs_attempted,
            total_prs,
            pr_processed,
            pr_failed,
        )

        return pr_details, pr_fetch_failures_404


def main():
    """Main entry point of the application."""
    # Prevent loading
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
