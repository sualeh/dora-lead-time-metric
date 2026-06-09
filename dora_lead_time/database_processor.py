"""Database operations to create releases database."""

import logging
import os
import pathlib
import sqlite3
from datetime import date, datetime
from dora_lead_time.models import (
    PullRequestIdentifier,
    Project,
    StoryInRelease,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
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

    def retrieve_all_projects(self) -> list[Project]:
        """Gets all projects from the database.

        Returns:
            list[Project]: List of Project named tuples

        Raises:
            Exception: If there's an error querying the database
        """
        conn = None
        projects = []

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

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
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.error(
                """
                %s
                Could not retrieve projects from the database
                """,
                e
            )
            if conn:
                conn.rollback()
            raise DatabaseOperationError(
                "Could not retrieve projects from the database"
            ) from e
        finally:
            if conn:
                conn.close()

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
        conn = None
        try:
            # When creating a schema,
            # we don't want to check if the database exists
            conn = self._get_connection(check_exists=False)
            cursor = conn.cursor()

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
            conn.commit()

            logger.info("Schema created")
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.error(
                """
                Could not create schema
                %s
                """,
                e
            )
            if conn:
                conn.rollback()
            raise DatabaseOperationError("Could not create schema") from e
        finally:
            if conn:
                conn.close()

    def save_projects(self, projects):
        """Save projects to the database.

        Args:
            projects: List of project tuples to save

        Raises:
            Exception: If there's an error saving projects to the database
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

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

            conn.commit()
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.error(
                """
                %s
                Could not save projects
                """,
                e
            )
            if conn:
                conn.rollback()
            raise DatabaseOperationError("Could not save projects") from e
        finally:
            if conn:
                conn.close()

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
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

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
            conn.commit()
            logger.info(
                "Updated project type to '%s' for %d projects",
                project_type,
                affected_rows,
            )

        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.error("Database error while updating project types: %s", e)
            if conn:
                conn.rollback()
            raise DatabaseOperationError(
                "Could not update project types"
            ) from e
        finally:
            if conn:
                conn.close()

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
        conn = None
        try:
            # Create new list of tuples without the id field
            releases = [release[1:] for release in releases]

            logger.info("Saving %d releases", len(releases))

            conn = self._get_connection()
            cursor = conn.cursor()

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

            conn.commit()

        except (
            sqlite3.OperationalError,
            sqlite3.DatabaseError,
            ValueError
        ) as e:
            logger.error(
                """
                %s
                Could not save releases.
                """,
                e
            )
            if conn:
                conn.rollback()
            raise DatabaseOperationError("Could not save releases") from e
        finally:
            if conn:
                conn.close()

    def retrieve_releases_without_stories(self) -> list[str]:
        """Get releases without associated stories from the database.

        Returns:
            list[str]: List of release internal IDs that don't have any
                associated stories

        Raises:
            Exception: If there's an error querying the database
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    releases.release_internal_id
                FROM
                    releases
                    LEFT JOIN releases_stories
                        ON releases.id = releases_stories.release_id
                WHERE
                    releases_stories.story_id IS NULL
                """
            )

            release_ids = cursor.fetchall()
            release_ids = [release_id[0] for release_id in release_ids]
            logger.info("%d releases without stories", len(release_ids))
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.error(
                """
                %s
                Could not get releases without stories
                """,
                e
            )
            release_ids = []
            if conn:
                conn.rollback()
            raise DatabaseOperationError(
                "Could not get releases without stories"
            ) from e
        finally:
            if conn:
                conn.close()

        return release_ids

    def save_stories(self, stories: list[StoryInRelease]) -> None:
        """Saves stories to the database.

        Args:
            stories: List of flattened StoryInRelease rows to save. Each
                story is inserted once by story_internal_id uniqueness, then
                linked to its release via the releases_stories join table.

        Raises:
            Exception: If there's an error saving stories to the database
        """
        conn = None
        try:
            logger.info("Saving %d story-release pairs", len(stories))

            conn = self._get_connection()
            cursor = conn.cursor()

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

            conn.commit()
        except (
            sqlite3.OperationalError,
            sqlite3.DatabaseError,
            ValueError
        ) as e:
            logger.error(
                """
                %s
                Could not save stories
                """,
                e
            )
            if conn:
                conn.rollback()
            raise DatabaseOperationError("Could not save stories") from e
        finally:
            if conn:
                conn.close()

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
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = f"""
                SELECT
                    stories.story_key,
                    stories.story_internal_id
                FROM
                    stories
                    LEFT OUTER JOIN stories_pull_request_counts
                        ON (
                            stories.id
                            = stories_pull_request_counts.story_id
                        )
                WHERE
                    stories_pull_request_counts.story_id IS NULL
                LIMIT {limit}
                """

            cursor.execute(query)

            stories = cursor.fetchall()
            logger.info("%d stories without PRs", len(stories))
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.error(
                """
                %s
                Could not load stories without pull requests
                """,
                e
            )
            stories = []
            if conn:
                conn.rollback()
            raise DatabaseOperationError(
                "Could not load stories without pull requests"
            ) from e
        finally:
            if conn:
                conn.close()

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
        conn = None
        try:
            # Count total PRs across all stories (keyed by story_key for now;
            # resolved to story_id during insert below)
            stories_pull_request_counts_by_key = {
                story: len(urls)
                for story, urls in stories_pull_requests_map.items()
            }
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

            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                DROP TABLE IF EXISTS stage_stories_pull_requests
                """
            )

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

            # Insert PRs
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

            # Insert into to PR mapping table
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

            cursor.executemany(
                """
                INSERT OR IGNORE INTO stories_pull_request_counts (
                    story_id,
                    pr_count
                )
                SELECT stories.id, ?
                FROM stories
                WHERE stories.story_key = ?
                """,
                [
                    (count, key)
                    for key, count
                    in stories_pull_request_counts_by_key.items()
                ],
            )
            logger.info(
                "Inserted %d story PR counts, "
                "to register that the PRs have been retrieved, even if zero",
                cursor.rowcount,
            )

            conn.commit()
        except (
            sqlite3.OperationalError,
            sqlite3.DatabaseError,
            ValueError
        ) as e:
            logger.error(
                """
                %s
                Could not save stories to PR URL mapping
                """,
                e
            )
            if conn:
                conn.rollback()
            raise DatabaseOperationError(
                "Could not save stories to PR URL mapping"
            ) from e
        finally:
            if conn:
                conn.close()

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
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = f"""
                SELECT
                    pull_requests.id,
                    pull_requests.pr_owner,
                    pull_requests.pr_repository,
                    pull_requests.pr_number
                FROM
                    pull_requests
                WHERE
                    pull_requests.pr_title IS NULL
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
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.error(
                """
                %s
                Could not load PRs from the database
                """,
                e
            )
            pull_requests = []
            if conn:
                conn.rollback()
            raise DatabaseOperationError(
                "Could not load PRs from the database"
            ) from e
        finally:
            if conn:
                # Close the connection
                conn.close()

        return pull_requests

    def save_pull_request_details(
        self, pull_request_details
    ) -> None:
        """Saves detailed information about each GitHub pull request to the
            database.

        Args:
            pull_request_details: List of PullRequest objects with details

        Raises:
            Exception: If there's an error saving data to the database
        """
        conn = None
        try:
            logger.info(
                "Saving details for %d pull requests",
                len(pull_request_details)
            )

            conn = self._get_connection()
            cursor = conn.cursor()

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

            conn.commit()
        except (
            sqlite3.OperationalError,
            sqlite3.DatabaseError,
            ValueError
        ) as e:
            logger.error(
                """
                %s
                Could not update PR details
                """,
                e
            )
            if conn:
                conn.rollback()
            raise DatabaseOperationError(
                "Could not update PR details"
            ) from e
        finally:
            if conn:
                conn.close()

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
        conn = None
        try:
            database_name = (
                self.sqlite_path
                if self.sqlite_path == ":memory:"
                else pathlib.Path(self.sqlite_path).name
            )

            conn = self._get_connection()
            cursor = conn.cursor()

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

        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.error("Failed to retrieve summary data: %s", e)
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()


def main():
    """Main entry point of the application."""
    # Prevent loading
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
