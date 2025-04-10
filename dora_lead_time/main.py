"""Main module of the application."""

import os
import logging
import json
from datetime import date
from dotenv import load_dotenv
from dora_lead_time.database_processor import DatabaseProcessor
from dora_lead_time.atlassian_requests import AtlassianRequests
from dora_lead_time.github_requests import GitHubRequests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
)
logger = logging.getLogger(__name__)


def create_releases_database(
        start_date: date,
        end_date: date,
        org_to_env_var_map: dict[str, str]
):
    """Coordinate the creation of the releases database.

    Args:
        start_date (date): Start date for release search (inclusive)
        end_date (date): End date for release search (inclusive)
    """
    logger.info(
        "Creating releases database between %s and %s", start_date, end_date
    )
    # Initialize clients
    atlassian_client = AtlassianRequests()
    github_client = GitHubRequests(org_to_env_var_map)

    # Initialize database processor
    db_processor = DatabaseProcessor()

    # Step 1: Create schema
    logger.info("-- 1. Creating releases database schema")
    db_processor.create_schema()

    # Step 2: Get and save projects
    logger.info("-- 2. Getting projects from Atlassian Jira")
    projects = atlassian_client.get_projects()
    db_processor.save_projects(projects)

    # Step 3: Get and save releases
    logger.info(
        "-- 3. Getting releases between %s and %s from Atlassian Jira",
        start_date,
        end_date
    )
    releases = atlassian_client.get_releases(start_date, end_date)
    db_processor.save_releases(releases)

    # Step 4: Find releases without stories, get stories and save them
    logger.info("-- 4. Getting stories for releases from Atlassian Jira")
    logger.info("Finding releases without stories")
    release_ids = db_processor.retrieve_releases_without_stories()
    if release_ids:
        logger.info("Getting stories for %d releases", len(release_ids))
        stories = atlassian_client.get_stories(release_ids)
        db_processor.save_stories(stories)

    # Step 5: Find stories without pull requests, get PRs and save them
    logger.info("-- 5. Getting pull requests for stories from Atlassian Jira")
    logger.info("Finding stories without pull requests")
    while True:
        story_keys = db_processor.retrieve_stories_without_pull_requests(
            limit=100
        )
        if story_keys:
            logger.info(
                "Getting pull requests for %d stories",
                len(story_keys)
            )
            story_pull_requests = atlassian_client.get_story_pull_requests(
                story_keys
            )
            db_processor.save_story_pull_requests(story_pull_requests)
        else:
            break

    # Step 6: Find pull requests without details, get details and save them
    logger.info("-- 6. Getting details for pull requests from GitHub")
    logger.info("Finding pull requests without details")
    while True:
        pull_requests = db_processor.retrieve_pull_requests_without_details(
            limit=100
        )
        if pull_requests:
            logger.info(
                "Getting details for %d pull requests",
                len(pull_requests)
            )
            pr_details = github_client.get_pull_request_details(pull_requests)
            db_processor.save_pull_request_details(pr_details)
        else:
            break

    logger.info("-- 7. Release database creation completed successfully")


def main():
    """Main entry point of the application."""

    load_dotenv(dotenv_path=".env.params")
    load_dotenv()

    # Read the GitHub organization to environment variable mapping
    org_tokens_json = os.getenv("GITHUB_ORG_TOKENS_MAP", "{}")
    try:
        org_to_env_var_map = json.loads(org_tokens_json)
    except json.JSONDecodeError:
        logger.error("Invalid GITHUB_ORG_TOKENS_MAP format. Using empty map.")
        org_to_env_var_map = {}

    create_releases_database(
        date.fromisoformat(os.getenv("START_DATE")),
        date.fromisoformat(os.getenv("END_DATE")),
        org_to_env_var_map=org_to_env_var_map
    )


if __name__ == "__main__":
    main()
