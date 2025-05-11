"""Main module of the application."""

import os
import logging
import json
import argparse
from datetime import date, datetime
import pathlib
from typing import NamedTuple
from dotenv import load_dotenv
from dora_lead_time.database_processor import DatabaseProcessor
from dora_lead_time.atlassian_requests import AtlassianRequests
from dora_lead_time.github_requests import GitHubRequests
from dora_lead_time.outlier_reports import OutlierReports
from dora_lead_time.lead_time_report import LeadTimeReport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
)
logger = logging.getLogger(__name__)


class LeadTimeConfiguration(NamedTuple):
    """Configuration for lead time analysis."""
    sqlite_path: str
    build_database: bool
    start_date: date
    end_date: date
    github_org_tokens_map: dict[str, str]


def load_lead_time_configuration() -> LeadTimeConfiguration:
    """Load lead time configuration from environment variables.

    Loads and validates configuration settings for lead time analysis from
    environment variables, including database path, dates, and GitHub tokens.

    Returns:
        LeadTimeConfiguration: A named tuple containing the configuration
            settings for lead time analysis.

    Raises:
        ValueError: If required environment variables are missing or invalid.
    """

    load_dotenv(dotenv_path=".env.params")
    load_dotenv()

    # Get database path
    sqlite_path = os.getenv("SQLITE_PATH")
    if not sqlite_path:
        raise ValueError("SQLITE_PATH environment variable not set")

    # Get date range
    try:
        start_date = date.fromisoformat(os.getenv("START_DATE", ""))
        end_date = date.fromisoformat(os.getenv("END_DATE", ""))
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "START_DATE and END_DATE must be valid ISO format dates"
        ) from exc

    # Get GitHub organization tokens map
    github_org_tokens_json = os.getenv("GITHUB_ORG_TOKENS_MAP", "{}")
    try:
        github_org_tokens_map = json.loads(github_org_tokens_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Invalid GITHUB_ORG_TOKENS_MAP format"
        ) from exc

    # Check if build flag is set
    build_database = os.getenv("BUILD_DATABASE", "False").lower() == "true"

    return LeadTimeConfiguration(
        sqlite_path,
        build_database,
        start_date,
        end_date,
        github_org_tokens_map
    )


def create_releases_database(config: LeadTimeConfiguration):
    """Coordinate the creation of the releases database.

    Args:
        build_database (bool): Flag to determine whether to build the database
        start_date (date): Start date for release search (inclusive)
        end_date (date): End date for release search (inclusive)
        org_to_env_var_map (dict[str, str]): Mapping from GitHub org to env var
    """
    logger.info(
        "Creating releases database between %s and %s",
        config.start_date,
        config.end_date
    )
    # Initialize clients
    atlassian_client = AtlassianRequests()
    github_client = GitHubRequests(config.github_org_tokens_map)

    # Initialize database processor
    db_processor = DatabaseProcessor(config.sqlite_path)

    if not config.build_database:
        db_processor.print_summary()
        return

    # Step 1: Create schema
    logger.info("-- 1. Creating releases database schema")
    db_processor.create_schema()
    db_processor.print_summary()

    # Step 2: Get and save projects
    logger.info("-- 2. Getting projects from Atlassian Jira")
    projects = atlassian_client.get_projects()
    db_processor.save_projects(projects)

    # Step 3: Get and save releases
    logger.info(
        "-- 3. Getting releases between %s and %s from Atlassian Jira",
        config.start_date,
        config.end_date
    )
    releases = atlassian_client.get_releases(
        config.start_date,
        config.end_date
    )
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
    db_processor.print_summary()


def save_outlier_reports(config: LeadTimeConfiguration):
    """Save all outlier reports as CSV files.

    Creates a new directory named "outlier_reports_yyyy-mm-dd-hh-mm-ss"
    and saves each outlier report as a CSV file within this directory.

    Returns:
        str: Path to the created reports directory
    """
    logger.info("Generating and saving outlier reports")

    # Create timestamp for directory name
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    reports_dir = pathlib.Path(f"outlier_reports_{timestamp}")
    reports_dir.mkdir(exist_ok=True)

    logger.info("Created reports directory: %s", reports_dir)

    # Initialize outlier reports
    outlier_reports = OutlierReports(config.sqlite_path)

    # Dictionary mapping report functions to file names
    report_mapping = {
        "projects_without_releases":
            outlier_reports.report_projects_without_releases,
        "releases_with_open_stories":
            outlier_reports.report_releases_with_open_stories,
        "stories_in_multiple_releases":
            outlier_reports.report_stories_in_multiple_releases,
        "releases_with_open_pull_requests":
            outlier_reports.report_releases_with_open_pull_requests,
        "counts_of_stories_without_pull_requests":
            outlier_reports.report_counts_of_stories_without_pull_requests,
        "stories_without_pull_requests":
            outlier_reports.report_stories_without_pull_requests,
        "pull_requests_with_old_commits":
            outlier_reports.report_pull_requests_with_old_commits,
        "zero_or_negative_lead_times":
            outlier_reports.report_zero_or_negative_lead_times
    }

    # Generate and save each report
    for report_name, report_func in report_mapping.items():
        logger.info("Generating report: %s", report_name)
        df = report_func()

        if not df.empty:
            file_path = reports_dir / f"{report_name}.csv"
            df.to_csv(file_path, index=False)
            logger.info("Saved report to %s (%d rows)", file_path, len(df))
        else:
            logger.info(
                "Report %s is empty, skipping CSV creation",
                report_name
            )

    logger.info(
        "Outlier reports saved to directory: %s",
        reports_dir.absolute()
    )
    return reports_dir


def _save_lead_time_chart(
    lead_time_report: LeadTimeReport,
    project_keys: list[str],
    start_date: date,
    end_date: date,
    title: str,
    file_path: pathlib.Path = None
):
    """
    Saves a lead time chart as an image file.

    This function generates a lead time chart using the provided parameters
    and saves it to the specified file path in PNG format.

    Args:
        lead_time_report (LeadTimeReport): An instance of LeadTimeReport used
            to create the chart.
        project_keys (list[str]): A list of project keys to include
            in the chart.
        start_date (date): The start date for the lead time data.
        end_date (date): The end date for the lead time data.
        title (str): The title of the chart.
        file_path (pathlib.Path, optional): The file path where the chart
            will be saved.
            If not provided, a default path should be specified by the caller.

    Raises:
        ValueError: If any of the input parameters are invalid.
        IOError: If there is an issue saving the file.

    Side Effects:
        Saves the chart as a PNG file at the specified location.
        Logs the save operation.

    """

    plot = lead_time_report.create_lead_time_chart(
        project_keys,
        start_date,
        end_date,
        title
    )
    if plot is None:
        return

    image_format = "png"
    # Save plot
    plot.savefig(
        file_path.with_suffix(f".{image_format}"),
        dpi=600,
        format=image_format
    )
    plot.close()  # Close plot to free memory
    logger.info("Saved '%s' to %s", title, file_path)


def save_lead_time_charts(config: LeadTimeConfiguration):
    """Generate and save lead time charts as PNG files.

    Creates a new directory named "lead_times_yyyy-mm-dd-hh-mm-ss"
    and saves lead time charts for each project, each project type,
    and an overall chart.

    Args:
        start_date (date): Start date for lead time calculations (inclusive)
        end_date (date): End date for lead time calculations (inclusive)

    Returns:
        str: Path to the created charts directory
    """
    logger.info("Generating and saving lead time charts")

    # Create timestamp for directory name
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    charts_dir = pathlib.Path(f"lead_times_{timestamp}")
    charts_dir.mkdir(exist_ok=True)

    logger.info("Created charts directory: %s", charts_dir)

    db_processor = DatabaseProcessor(config.sqlite_path)
    lead_time_report = LeadTimeReport(config.sqlite_path)

    # Get all projects
    all_projects = db_processor.retrieve_all_projects()

    # Group projects by type
    projects_by_type = {}
    all_project_keys = []

    for project in all_projects:
        project_key = project.project_key
        all_project_keys.append(project_key)

        project_type = project.project_type or "unknown"
        if project_type not in projects_by_type:
            projects_by_type[project_type] = []

        projects_by_type[project_type].append(project_key)

    # Generate chart for each individual project
    for project in all_projects:
        project_key = project.project_key
        project_title = project.project_title
        title = f"Lead Time for {project_title}"
        _save_lead_time_chart(
            lead_time_report,
            [project_key],
            config.start_date,
            config.end_date,
            title,
            charts_dir / f"project_{project_key}"
        )

    # Generate chart for each project type
    for project_type, project_keys in projects_by_type.items():
        if not project_keys:
            continue

        title = f"Lead Time for {project_type.capitalize()} Projects"
        _save_lead_time_chart(
            lead_time_report,
            project_keys,
            config.start_date,
            config.end_date,
            title,
            charts_dir / f"type_{project_type}"
        )

    # Generate overall chart
    _save_lead_time_chart(
        lead_time_report,
        all_project_keys,
        config.start_date,
        config.end_date,
        "Overall Lead Time",
        charts_dir / "_overall"
    )

    logger.info(
        "Lead time charts saved to directory: %s",
        charts_dir.absolute()
    )
    return charts_dir


def main():
    """Main entry point of the application."""
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="DORA Lead Time Metrics"
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build a new database, or update the existing one"
    )
    parser.add_argument(
        "--reports",
        action="store_true",
        help="Generate outlier reports"
    )
    parser.add_argument(
        "--charts",
        action="store_true",
        help="Generate lead time charts"
    )
    args = parser.parse_args()

    # If no arguments are provided, show help
    if not args.build and not args.reports and not args.charts:
        parser.print_help()
        return

    config = load_lead_time_configuration()

    # If build flag is set, create the database
    build_database = args.build and config.build_database
    if build_database:
        create_releases_database(config)

    # Generate reports if flag is set
    if args.reports:
        save_outlier_reports(config)

    # Generate lead time charts if flag is set
    if args.charts:
        save_lead_time_charts(config)


if __name__ == "__main__":
    main()
