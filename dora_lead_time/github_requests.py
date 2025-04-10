"""GitHub API requests."""

import logging
import os
from datetime import datetime

import requests
from dotenv import load_dotenv
from dora_lead_time.models import PullRequestIdentifier, PullRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
)
logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30  # Timeout in seconds for HTTP requests


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

    def get_pull_request_details(
        self, pull_requests: list[PullRequestIdentifier]
    ) -> list[PullRequest]:
        """
        Retrieves detailed information about each GitHub pull request.

        Args:
            pull_requests (list[PullRequestIdentifier]): A list of
                PullRequestIdentifier

        Returns:
            list[PullRequest]: A list of PullRequest

        Raises:
            ValueError: If GitHub token is not provided
            requests.RequestException: If there's an error connecting to GitHub
        """
        if not pull_requests:
            return []
        if not self.github_token_map:
            raise ValueError("No GitHub tokens available in token map")

        pr_details = []

        pr_processed = 0
        for pr in pull_requests:
            owner = pr.pr_owner
            repo = pr.pr_repository
            pr_number = pr.pr_number

            github_token = self.github_token_map.get(owner)
            if not github_token:
                logger.error(
                    "No GitHub token found for organization: %s", owner
                )
                continue

            headers = {"Authorization": f"token {github_token}"}

            api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
            response = requests.get(
                api_url, headers=headers, timeout=self.request_timeout
            )
            if response.status_code != 200:
                logger.error(
                    "ERROR: Could not fetch PR details for: "
                    "%s/%s/%s. Status code: %s",
                    owner, repo, pr_number, response.status_code
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
            commits_response = requests.get(
                commits_url, headers=headers, timeout=self.request_timeout
            )
            if commits_response.status_code != 200:
                commits = []
            else:
                commits = commits_response.json()

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
            closed_date = (
                datetime.fromisoformat(
                    pr_data["closed_at"].replace("Z", "+00:00")
                ).date()
                if pr_data["closed_at"]
                else None
            )

            # Replace tuple creation with named tuple
            pr_detail = PullRequest(
                id=pr.id,
                pr_title=pr_data["title"],
                open_date=created_date,
                close_date=closed_date,
                commit_count=len(commits),
                earliest_commit_date=earliest_commit_date,
                latest_commit_date=latest_commit_date,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
            )
            pr_details.append(pr_detail)

            # Log progress
            pr_processed = pr_processed + 1
            if pr_processed % 25 == 0:
                logger.info(
                    "Processed %d/%d PRs", pr_processed, len(pull_requests)
                )
        logger.info("Processed %d/%d PRs", pr_processed, len(pull_requests))

        return pr_details


def main():
    """Main entry point of the application."""
    # Prevent loading
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
