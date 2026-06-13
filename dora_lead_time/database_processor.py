"""Database operations to create releases database."""

import logging
import os
import pathlib
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from dora_lead_time.models import (
    PullRequestIdentifier,
    Project,
    StoryInRelease,
)

logger = logging.getLogger(__name__)

PULL_REQUEST_BATCH_SIZE = 100


def make_sqlite_connection(
    sqlite_path: str,
    check_exists: bool = True,
) -> sqlite3.Connection:
    """Create a SQLite connection with configured date/time conversion.

    Args:
        sqlite_path (str): Path to SQLite database file.
        check_exists (bool, optional): When True, ensure the database file
            exists before connecting. Defaults to True.

    Returns:
        sqlite3.Connection: A configured SQLite connection.

    Raises:
        FileNotFoundError: If the database file does not exist and
            ``check_exists`` is True.
    """
    if check_exists and not os.path.exists(sqlite_path):
        raise FileNotFoundError(
            f"Database file does not exist: {sqlite_path}"
        )

    sqlite3.register_adapter(date, lambda val: val.isoformat())
    sqlite3.register_adapter(datetime, lambda val: val.isoformat())

    sqlite3.register_converter(
        "date",
        lambda val: date.fromisoformat(val.decode())
    )
    sqlite3.register_converter(
        "datetime",
        lambda val: datetime.fromisoformat(val.decode())
    )

    conn = sqlite3.connect(
        sqlite_path,
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    logger.debug("Connected to %s", sqlite_path)

    return conn


class DatabaseOperationError(Exception):
    """Raised when a database read or write operation fails unrecoverably."""


class DatabaseProcessor:
    """Database operations to create releases database."""

    def __init__(self, sqlite_path: str):
        """Initialize the database processor with database path.

        Args:
            sqlite_path (str): Path to SQLite database file.
        """
        if not sqlite_path:
            raise ValueError("SQLite location not set")
        self.sqlite_path = sqlite_path

    def _get_connection(self, check_exists=True):
        """Get a SQLite connection with proper type handling.

        Args:
            check_exists (bool, optional): If True, checks if the database
                file exists before connecting. Defaults to True.

        Returns:
            sqlite3.Connection: A connection to the SQLite database

        Raises:
            FileNotFoundError: If the database file does not exist
                and check_exists is True
        """
        conn = make_sqlite_connection(
            self.sqlite_path,
            check_exists=check_exists,
        )

        return conn

    @contextmanager
    def _transaction(self, operation: str, check_exists: bool = True):
        """Context manager for database transactions.

        Handles connection setup, commit, rollback, and cleanup for all
        database operations. Ensures proper error handling and resource
        management.

        Args:
            operation: A description of the operation being performed
                (used in error messages and logging).
            check_exists: If True, verify the database file exists before
                connecting. Defaults to True. Set to False for schema
                creation.

        Yields:
            sqlite3.Cursor: A database cursor for executing SQL statements.

        Raises:
            DatabaseOperationError: If the operation encounters a database
                error.
        """
        conn = make_sqlite_connection(self.sqlite_path, check_exists)
        try:
            yield conn.cursor()
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.DatabaseError, ValueError) as e:
            conn.rollback()
            logger.error("%s: %s", operation, e)
            raise DatabaseOperationError(operation) from e
        finally:
            conn.close()

    def retrieve_all_projects(self) -> list[Project]:
        """Gets all projects from the database.

        Returns:
            list[Project]: List of Project named tuples

        Raises:
            DatabaseOperationError: If there's an error querying the database
        """
        projects = []
        try:
            with self._transaction("retrieve all projects") as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        project_internal_id,
                        project_key,
                        project_title,
                        project_type
                    FROM
                        projects
                    """
                )
                rows = cursor.fetchall()
                projects = [
                    Project(
                        id=row[0],
                        project_internal_id=row[1],
                        project_key=row[2],
                        project_title=row[3],
                        project_type=row[4]
                    )
                    for row in rows
                ]
                logger.debug("Retrieved %d projects", len(projects))
        except DatabaseOperationError:
            raise
        return projects

    def create_schema(self):
        """Create database schema for lead time calculation.

        Creates tables for projects, releases, stories, pull requests, commits,
        and their relationships. Also creates views for pull request summary
        and lead times.
        The schema follows a structure where:
        1. Projects contain releases
        2. Releases contain stories
        3. Stories are associated with pull requests
        4. Pull requests contain commit information

        Raises:
            Exception: If there's an error creating the schema
        """
        with self._transaction("create schema", check_exists=False) as cursor:
            schema_dir = pathlib.Path(__file__).parent / "schema"
            schema_dir.mkdir(exist_ok=True)
            schema_script_path = schema_dir / "schema.sql"
            if not schema_script_path.exists():
                raise FileNotFoundError(
                    f"SQL file {schema_script_path} not found"
                )

            schema_script = ""
            with open(schema_script_path, "r", encoding="utf-8") as f:
                schema_script = f.read()

            cursor.executescript(schema_script)

            logger.info("Schema created")

    def save_projects(self, projects):
        """Save projects to the database.

        Args:
            projects: List of project tuples to save

        Raises:
            Exception: If there's an error saving projects to the database
        """
        with self._transaction("save projects") as cursor:
            # Create new list of tuples without the id field
            projects = [project[1:] for project in projects]

            cursor.executemany(
                """
                INSERT OR IGNORE INTO projects (
                    project_internal_id,
                    project_key,
                    project_title,
                    project_type
                )
                VALUES (?, ?, ?, ?)
                """,
                projects,
            )
            logger.info("Inserted %d projects", cursor.rowcount)

    def update_project_types(
        self,
        project_keys: list[str],
        project_type: str
    ):
        """Update project type for given project keys in the database.

        Args:
            project_keys (list[str]): List of project keys to update
            project_type (str): Project type to set (e.g., 'app', 'mobile')

        Raises:
            Exception: If there's an error updating project types
        """
        with self._transaction("update project types") as cursor:
            params = [(project_type, key) for key in project_keys]

            cursor.executemany(
                """
                UPDATE projects
                SET project_type = ?
                WHERE project_key = ?
                """,
                params,
            )

            affected_rows = cursor.rowcount
            logger.info(
                "Updated project type to '%s' for %d projects",
                project_type,
                affected_rows,
            )

    def save_releases(
        self,
        releases
    ) -> None:
        """Saves releases to the database.

        Args:
            releases: List of release tuples to save

        Raises:
            Exception: If there's an error saving releases to the database
        """
        # Create new list of tuples without the id field
        releases = [release[1:] for release in releases]

        logger.info("Saving %d releases", len(releases))

        with self._transaction("save releases") as cursor:
            cursor.execute(
                """
                DROP TABLE IF EXISTS stage_releases
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stage_releases (
                    release_internal_id VARCHAR(1024),
                    release_title VARCHAR(1024),
                    release_description VARCHAR(2048),
                    release_date DATE,
                    project_key VARCHAR(1024),
                    UNIQUE(release_internal_id)
                )
            """
            )

            cursor.executemany(
                """
                INSERT INTO stage_releases (
                    release_internal_id,
                    release_title,
                    release_description,
                    release_date,
                    project_key
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                releases,
            )
            logger.info("Staged %d releases", cursor.rowcount)

            # CAUTION: This ignores errors and constraints
            cursor.execute(
                """
                INSERT OR IGNORE INTO releases
                (
                    release_internal_id,
                    release_title,
                    release_description,
                    release_date,
                    project_id
                )
                SELECT
                    stage_releases.release_internal_id,
                    stage_releases.release_title,
                    stage_releases.release_description,
                    stage_releases.release_date,
                    projects.id as project_id
                FROM
                    stage_releases
                JOIN projects
                    ON stage_releases.project_key = projects.project_key
                """
            )
            logger.info("Inserted %d releases", cursor.rowcount)

            cursor.execute(
                """
                DROP TABLE IF EXISTS stage_releases
                """
            )

    def retrieve_releases_without_stories(self) -> list[str]:
        """Get releases without associated stories from the database.

        Returns:
            list[str]: List of release internal IDs that don't have any
                associated stories

        Raises:
            Exception: If there's an error querying the database
        """
        with self._transaction("retrieve releases without stories") as cursor:
            cursor.execute(
                """
                SELECT
                    releases.release_internal_id
                FROM
                    releases
                    LEFT JOIN releases_stories
                        ON releases.id = releases_stories.release_id
                    LEFT JOIN releases_without_stories
                        ON releases.id = releases_without_stories.release_id
                WHERE
                    releases_stories.story_id IS NULL
                    AND releases_without_stories.release_id IS NULL
                    AND releases.release_date < date('now', 'localtime')
                """
            )

            release_ids = cursor.fetchall()
            release_ids = [release_id[0] for release_id in release_ids]
            logger.info("%d releases without stories", len(release_ids))

        return release_ids

    def save_releases_without_stories(
        self,
        release_internal_ids: list[str],
    ) -> None:
        """Mark releases as processed when no stories are found.

        Args:
            release_internal_ids: Release internal IDs confirmed to have
                no stories at fetch time.

        Raises:
            DatabaseOperationError: If there's an error saving markers.
        """
        if not release_internal_ids:
            return

        with self._transaction("save releases without stories") as cursor:
            cursor.executemany(
                """
                INSERT OR IGNORE INTO releases_without_stories (
                    release_id
                )
                SELECT releases.id
                FROM releases
                WHERE releases.release_internal_id = ?
                """,
                [(release_id,) for release_id in release_internal_ids],
            )
            logger.info(
                "Inserted %d releases without stories markers",
                cursor.rowcount,
            )

    def save_stories(self, stories: list[StoryInRelease]) -> None:
        """Saves stories to the database.

        Args:
            stories: List of flattened StoryInRelease rows to save. Each
                story is inserted once by story_internal_id uniqueness, then
                linked to its release via the releases_stories join table.

        Raises:
            Exception: If there's an error saving stories to the database
        """
        logger.info("Saving %d story-release pairs", len(stories))

        with self._transaction("save stories") as cursor:
            cursor.execute("DROP TABLE IF EXISTS stage_stories")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stage_stories (
                    story_internal_id VARCHAR(1024),
                    story_key VARCHAR(1024),
                    story_title VARCHAR(1024),
                    story_type VARCHAR(1024),
                    story_created DATETIME,
                    story_resolved DATETIME,
                    release_internal_id VARCHAR(1024),
                    UNIQUE(story_internal_id, release_internal_id),
                    UNIQUE(story_key, release_internal_id)
                )
                """
            )

            staging_rows = [
                (
                    story_release.story_internal_id,
                    story_release.story_key,
                    story_release.story_title,
                    story_release.story_type,
                    story_release.story_created,
                    story_release.story_resolved,
                    story_release.release_internal_id,
                )
                for story_release in stories
            ]

            cursor.executemany(
                """
                INSERT INTO stage_stories (
                    story_internal_id,
                    story_key,
                    story_title,
                    story_type,
                    story_created,
                    story_resolved,
                    release_internal_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                staging_rows,
            )
            logger.info("Staged %d story-release pairs", cursor.rowcount)

            cursor.execute(
                """
                INSERT OR IGNORE INTO stories
                (
                    story_internal_id,
                    story_key,
                    story_title,
                    story_type,
                    story_created,
                    story_resolved
                )
                SELECT DISTINCT
                    stage_stories.story_internal_id,
                    stage_stories.story_key,
                    stage_stories.story_title,
                    stage_stories.story_type,
                    stage_stories.story_created,
                    stage_stories.story_resolved
                FROM
                    stage_stories
                """
            )
            logger.info("Inserted %d canonical stories", cursor.rowcount)

            cursor.execute(
                """
                INSERT OR IGNORE INTO releases_stories
                (
                    release_id,
                    story_id
                )
                SELECT
                    releases.id AS release_id,
                    stories.id AS story_id
                FROM
                    stage_stories
                    JOIN releases
                        ON (
                            stage_stories.release_internal_id
                            = releases.release_internal_id
                        )
                    JOIN stories
                        ON (
                            stage_stories.story_internal_id
                            = stories.story_internal_id
                        )
                """
            )
            logger.info(
                "Inserted %d story-release links", cursor.rowcount
            )

            cursor.execute("DROP TABLE IF EXISTS stage_stories")

    def retrieve_stories_without_pull_requests(
        self,
        limit: int = PULL_REQUEST_BATCH_SIZE,
    ) -> list[tuple[str, str | None]]:
        """Retrieves story keys that don't have associated pull requests for
            given projects and date range.

        Args:
            limit (int, optional): Maximum number of records to retrieve.
                Defaults to PULL_REQUEST_BATCH_SIZE.

        Returns:
            List[tuple[str, str | None]]: (story key, story internal id)
                pairs that don't have pull requests mapped to them.

        Raises:
            Exception: If there's an error querying the database
        """
        with self._transaction("retrieve stories without pull requests") as cursor:
            query = f"""
                SELECT
                    DISTINCT stories.story_key,
                    stories.story_internal_id
                FROM
                    stories
                    LEFT OUTER JOIN stories_without_pull_requests
                        ON (
                            stories.id
                            = stories_without_pull_requests.story_id
                        )
                    LEFT OUTER JOIN stories_pull_requests
                        ON stories.id = stories_pull_requests.story_id
                WHERE
                    stories_without_pull_requests.story_id IS NULL
                    AND stories_pull_requests.story_id IS NULL
                LIMIT {limit}
                """

            cursor.execute(query)

            stories = cursor.fetchall()
            logger.info("%d stories without PRs", len(stories))

        return stories

    def save_story_pull_requests(
        self, stories_pull_requests_map
    ) -> None:
        """Saves GitHub pull request mappings for Jira stories to the database.

        Args:
            stories_pull_requests_map: Mapping of story keys to pull
                request URLs

        Raises:
            Exception: If there's an error saving data to the database
        """
        zero_pr_story_keys = [
            story
            for story, urls in stories_pull_requests_map.items()
            if not urls
        ]
        stories_pull_requests = [
            (
                story,
                *url[1:]
            )
            for story, urls in stories_pull_requests_map.items()
            for url in urls
        ]
        total_prs = len(stories_pull_requests)

        logger.info(
            "Saving %d pull requests across %d stories",
            total_prs,
            len(stories_pull_requests_map),
        )

        with self._transaction("save story pull requests") as cursor:
            cursor.execute(
                """
                DROP TABLE IF EXISTS stage_stories_pull_requests
                """
            )

            if stories_pull_requests:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS stage_stories_pull_requests (
                        story_key VARCHAR(1024),
                        pr_owner VARCHAR(1024),
                        pr_repository VARCHAR(1024),
                        pr_number VARCHAR(1024)
                    )
                    """
                )

                cursor.executemany(
                    """
                    INSERT INTO stage_stories_pull_requests (
                        story_key,
                        pr_owner,
                        pr_repository,
                        pr_number
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    stories_pull_requests,
                )
                logger.info("Staged %d PRs for stories", cursor.rowcount)

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO pull_requests
                    (
                        pr_owner,
                        pr_repository,
                        pr_number
                    )
                    SELECT
                        stage_stories_pull_requests.pr_owner,
                        stage_stories_pull_requests.pr_repository,
                        stage_stories_pull_requests.pr_number
                    FROM
                        stage_stories_pull_requests
                    """
                )
                logger.info("Inserted %d PRs", cursor.rowcount)

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO stories_pull_requests(
                                            story_id,
                                            pr_id
                    )
                    SELECT
                        stories.id,
                        pull_requests.id
                    FROM
                        stage_stories_pull_requests
                        JOIN stories
                            ON (
                                stage_stories_pull_requests.story_key
                                = stories.story_key
                            )
                        JOIN pull_requests
                            ON (
                                stage_stories_pull_requests.pr_owner
                                = pull_requests.pr_owner
                                AND stage_stories_pull_requests.pr_repository
                                = pull_requests.pr_repository
                                AND stage_stories_pull_requests.pr_number
                                = pull_requests.pr_number
                            )
                    """
                )
                logger.info("Inserted %d PRs for stories", cursor.rowcount)

                cursor.execute(
                    """
                    DROP TABLE IF EXISTS stage_stories_pull_requests
                    """
                )

            if zero_pr_story_keys:
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO stories_without_pull_requests (
                        story_id
                    )
                    SELECT stories.id
                    FROM stories
                    WHERE stories.story_key = ?
                    """,
                    [(key,) for key in zero_pr_story_keys],
                )
                logger.info(
                    "Inserted %d stories with zero pull requests",
                    cursor.rowcount,
                )

    def retrieve_pull_requests_without_details(
        self,
        limit: int = PULL_REQUEST_BATCH_SIZE,
    ) -> list[PullRequestIdentifier]:
        """Gets pull request URLs that have no details from the database.

        Args:
            limit (int, optional): Maximum number of records to retrieve.
                Defaults to 0.

        Returns:
            list[PullRequestIdentifier]: List of PullRequestIdentifier objects

        Raises:
            Exception: If there's an error querying the database
        """
        with self._transaction("retrieve pull requests without details") as cursor:
            query = f"""
                SELECT
                    pull_requests.id,
                    pull_requests.pr_owner,
                    pull_requests.pr_repository,
                    pull_requests.pr_number
                FROM
                    pull_requests
                LEFT JOIN
                    pull_requests_fetch_failures
                    ON pull_requests.id = pull_requests_fetch_failures.pr_id
                WHERE
                    pull_requests.pr_title IS NULL
                    AND pull_requests_fetch_failures.pr_id IS NULL
                LIMIT {limit}
                """

            cursor.execute(query)

            rows = cursor.fetchall()
            pull_requests = [
                PullRequestIdentifier(
                    id=row[0],
                    pr_owner=row[1],
                    pr_repository=row[2],
                    pr_number=row[3]
                )
                for row in rows
            ]
            logger.info("%d PRs without details", len(pull_requests))

        return pull_requests

    def save_pull_request_details(
        self, pull_request_details, pull_request_fetch_failures_404=None
    ) -> None:
        """Saves detailed information about each GitHub pull request to the
            database.

        Args:
            pull_request_details: List of PullRequest objects with details
            pull_request_fetch_failures_404: List of PR IDs that failed to
                fetch with 404 errors (optional)

        Raises:
            Exception: If there's an error saving data to the database
        """
        if pull_request_fetch_failures_404 is None:
            pull_request_fetch_failures_404 = []

        logger.info(
            "Saving details for %d pull requests",
            len(pull_request_details)
        )

        with self._transaction("save pull request details") as cursor:
            # Update to use the fields from PullRequest
            cursor.executemany(
                """
                UPDATE pull_requests
                SET
                    pr_title = ?,
                    pr_open = ?,
                    pr_close = ?,
                    commit_count = ?,
                    earliest_commit_date = ?,
                    latest_commit_date = ?
                WHERE
                    id = ?
                """,
                [(
                    pr.pr_title,
                    pr.open_date,
                    pr.close_date,
                    pr.commit_count,
                    pr.earliest_commit_date,
                    pr.latest_commit_date,
                    pr.id
                ) for pr in pull_request_details]
            )
            logger.info("Updated %d pull requests", cursor.rowcount)

            # Insert PR fetch failures (404s)
            if pull_request_fetch_failures_404:
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO pull_requests_fetch_failures
                    (pr_id)
                    VALUES (?)
                    """,
                    [(pr_id,) for pr_id in pull_request_fetch_failures_404]
                )
                logger.info(
                    "Recorded %d pull request fetch failures",
                    len(pull_request_fetch_failures_404)
                )

    def retrieve_projects_by_type(
        self,
        project_types: list[str] = None
    ) -> dict[str, str]:
        """Retrieves projects from the database filtered by project types.

        Args:
            project_types: List of project types to include
                e.g. ['software', 'infra']

        Returns:
            A dictionary mapping project keys to project titles
        """
        projects_dict = {}
        projects = self.retrieve_all_projects()
        for project in projects:
            if project.project_type in project_types:
                project_key = project.project_key
                project_title = project.project_title
                projects_dict[project_key] = project_title

        logger.debug("Retrieved %d projects", len(projects_dict))
        return projects_dict

    def print_summary(self):
        """Print summary data from the database.

        Displays statistics for releases, stories, and pull requests including:
        - Total count for each entity
        - Date ranges (earliest/ latest)

        Raises:
            Exception: If there's an error querying the database
        """
        database_name = (
            self.sqlite_path
            if self.sqlite_path == ":memory:"
            else pathlib.Path(self.sqlite_path).name
        )

        try:
            with self._transaction("print summary") as cursor:
                cursor.execute(
                    """
                    SELECT
                        type,
                        count,
                        earliest_date,
                        latest_date
                    FROM
                        summary
                    ORDER BY
                        id
                    """
                )

                rows = cursor.fetchall()

                if not rows:
                    logger.info(
                        "No summary data available in database: %s",
                        database_name,
                    )
                    return

                summary_lines = [
                    f"Database: {database_name}",
                    "Data summary:",
                ]
                for row in rows:
                    entity_type, count, earliest_date, latest_date = row
                    summary_lines.append(
                        f"    - {'{:5,}'.format(count)}"
                        f" {'{:15}'.format(entity_type)}"
                        f" from {earliest_date} to {latest_date}"
                    )

                logger.info("\n".join(summary_lines))

        except DatabaseOperationError:
            logger.error("Failed to retrieve summary data")


def main():
    """Main entry point of the application."""
    # Prevent loading
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
