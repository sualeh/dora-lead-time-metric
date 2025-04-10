"""Database operations to create releases database."""

import logging
import os
from datetime import date, datetime
import sqlite3
from dotenv import load_dotenv
from dora_lead_time.models import PullRequestIdentifier, Project

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
)
logger = logging.getLogger(__name__)


class DatabaseProcessor:
    """Database operations to create releases database."""

    def __init__(self, sqlite_path=None):
        """Initialize the database processor with database path.

        Args:
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.
        """
        load_dotenv()
        self.sqlite_path = sqlite_path or os.getenv("SQLITE_PATH")
        if not self.sqlite_path:
            logger.info("SQLite location not set")

    def _get_connection(self):
        """Get a SQLite connection with proper type handling.

        Args:
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.

        Returns:
            sqlite3.Connection: A connection to the SQLite database
        """
        sqlite_path = self.sqlite_path

        # Register adapters for Python objects to SQLite types
        sqlite3.register_adapter(date, lambda val: val.isoformat())
        sqlite3.register_adapter(datetime, lambda val: val.isoformat())

        # Register converters from SQLite types to Python objects
        sqlite3.register_converter(
            "date",
            lambda val: date.fromisoformat(val.decode())
        )
        sqlite3.register_converter(
            "timestamp",
            lambda val: datetime.fromisoformat(val.decode())
        )

        conn = sqlite3.connect(
            sqlite_path,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        logger.debug("Connected to %s", sqlite_path)

        return conn

    def retrieve_all_projects(self) -> list[Project]:
        """Gets all projects from the database.

        Args:
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.

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

        Args:
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.

        Raises:
            Exception: If there's an error creating the schema
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            schema_script = """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_internal_id VARCHAR(1024),
                    project_key VARCHAR(1024),
                    project_title VARCHAR(1024),
                    project_type VARCHAR(1024),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_internal_id),
                    UNIQUE(project_key)
                );

                CREATE TABLE IF NOT EXISTS releases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    release_internal_id VARCHAR(1024),
                    release_title VARCHAR(1024),
                    release_description VARCHAR(2048),
                    release_date VARCHAR(1024), -- DATE
                    project_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(release_internal_id, project_id),
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                );

                CREATE TABLE IF NOT EXISTS stories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    story_key VARCHAR(1024),
                    story_title VARCHAR(1024),
                    story_type VARCHAR(1024),
                    story_created VARCHAR(1024), -- DATE
                    story_resolved VARCHAR(1024), -- DATE
                    release_id VARCHAR(1024),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(story_key, release_id),
                    FOREIGN KEY (release_id) REFERENCES releases (id)
                );

                CREATE TABLE IF NOT EXISTS pull_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pr_title VARCHAR(1024),
                    pr_owner VARCHAR(1024),
                    pr_repository VARCHAR(1024),
                    pr_number VARCHAR(1024),
                    pr_open VARCHAR(1024), -- DATE
                    pr_close VARCHAR(1024), -- DATE
                    commit_count INTEGER,
                    earliest_commit_date VARCHAR(1024), -- DATE
                    latest_commit_date VARCHAR(1024), -- DATE
                    pr_url VARCHAR(1024) GENERATED ALWAYS
                      AS (
                        'https://github.com/' || pr_owner || '/' ||
                        pr_repository || '/pull/' || pr_number
                      ) VIRTUAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(pr_owner, pr_repository, pr_number)
                );

                CREATE TABLE IF NOT EXISTS stories_pull_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    story_id INTEGER,
                    pr_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(story_id, pr_id),
                    FOREIGN KEY (story_id) REFERENCES stories (id),
                    FOREIGN KEY (pr_id) REFERENCES pull_requests (id)
                );

                CREATE TABLE IF NOT EXISTS stories_pull_request_counts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    story_key VARCHAR(1024),
                    pr_count INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(story_key),
                    FOREIGN KEY (story_key) REFERENCES stories (story_key)
                );

                DROP VIEW IF EXISTS lead_times;

                CREATE VIEW lead_times AS
                SELECT
                    releases.id
                    AS release_id,
                    releases.release_date,
                    projects.project_key,
                    pull_requests.id
                    AS pr_id,
                    pull_requests.pr_title,
                    pull_requests.pr_owner,
                    pull_requests.pr_repository,
                    pull_requests.pr_number,
                    pull_requests.earliest_commit_date,
                    julianday(releases.release_date) -
                      julianday(pull_requests.earliest_commit_date) + 1
                      AS lead_time
                FROM
                    releases
                    JOIN projects
                    ON releases.project_id = projects.id
                    JOIN stories
                    ON stories.release_id = releases.id
                    JOIN stories_pull_requests
                    ON stories_pull_requests.story_id = stories.id
                    JOIN pull_requests
                    ON stories_pull_requests.pr_id = pull_requests.id;
            """

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
        finally:
            if conn:
                conn.close()

    def save_projects(self, projects):
        """Save projects to the database.

        Args:
            projects: List of project tuples to save
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.

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
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.
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
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.

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
                CREATE TABLE IF NOT EXISTS stage_releases (
                    release_internal_id VARCHAR(1024),
                    release_title VARCHAR(1024),
                    release_description VARCHAR(2048),
                    release_date VARCHAR(1024), -- DATE
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
        finally:
            if conn:
                conn.close()

    def retrieve_releases_without_stories(self) -> list[str]:
        """Get releases without associated stories from the database.

        Args:
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.

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
                    LEFT JOIN stories
                    ON releases.id = stories.release_id
                WHERE
                    stories.release_id IS NULL
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
        finally:
            if conn:
                conn.close()

        return release_ids

    def save_stories(self, stories) -> None:
        """Saves stories to the database.

        Args:
            stories: List of story tuples to save
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.

        Raises:
            Exception: If there's an error saving stories to the database
        """
        conn = None
        try:
            # Create new list of tuples without the id field
            stories = [story[1:] for story in stories]

            logger.info("Saving %d stories", len(stories))

            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stage_stories (
                    story_key VARCHAR(1024),
                    story_title VARCHAR(1024),
                    story_type VARCHAR(1024),
                    release_internal_id VARCHAR(1024),
                    story_created VARCHAR(1024), -- DATETIME
                    story_resolved VARCHAR(1024), -- DATETIME
                    UNIQUE(story_key, release_internal_id)
                )
                """
            )

            cursor.executemany(
                """
                INSERT INTO stage_stories (
                story_key,
                story_title,
                story_type,
                story_created,
                story_resolved,
                release_internal_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                stories,
            )
            logger.info("Staged %d stories", cursor.rowcount)

            cursor.execute(
                """
                INSERT INTO stories
                (
                story_key,
                story_title,
                story_type,
                story_created,
                story_resolved,
                release_id
                )
                SELECT
                stage_stories.story_key,
                stage_stories.story_title,
                stage_stories.story_type,
                stage_stories.story_created,
                stage_stories.story_resolved,
                releases.id AS release_id
                FROM
                stage_stories
                JOIN releases
                    ON stage_stories.release_internal_id = releases.release_internal_id
                """
            )
            logger.info("Inserted %d stories", cursor.rowcount)

            cursor.execute(
                """
                DROP TABLE IF EXISTS stage_stories
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
                Could not save stories
                """,
                e
            )
        finally:
            if conn:
                conn.close()

    def retrieve_stories_without_pull_requests(
        self,
        limit: int = 0,
    ) -> list[str]:
        """Retrieves story keys that don't have associated pull requests for
            given projects and date range.

        Args:
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.

        Returns:
            List of story keys that don't have pull requests mapped to them

        Raises:
            Exception: If there's an error querying the database
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(f"""
                SELECT
                    stories.story_key
                FROM
                    stories
                    LEFT OUTER JOIN stories_pull_request_counts
                        ON stories.story_key = stories_pull_request_counts.story_key
                WHERE
                    stories_pull_request_counts.story_key IS NULL
                LIMIT {limit}
                """
            )

            story_keys = cursor.fetchall()
            story_keys = [story_key[0] for story_key in story_keys]
            logger.info("%d stories without PRs", len(story_keys))
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logger.error(
                """
                %s
                Could not load stories without pull requests
                """,
                e
            )
            story_keys = []
        finally:
            if conn:
                conn.close()

        return story_keys

    def save_story_pull_requests(
        self, stories_pull_requests_map
    ) -> None:
        """Saves GitHub pull request mappings for Jira stories to the database.

        Args:
            stories_pull_requests: Mapping of story keys to pull request URLs
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.

        Raises:
            Exception: If there's an error saving data to the database
        """
        conn = None
        try:
            # Count total PRs across all stories
            stories_pull_request_counts = [
                (
                    story,
                    len(urls)
                )
                for story, urls in stories_pull_requests_map.items()
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

            conn = self._get_connection()
            cursor = conn.cursor()

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
                INSERT INTO stories_pull_requests(
				  story_id,
                  pr_id
                )
                SELECT
                  stories.id,
                  pull_requests.id
                FROM
                  stage_stories_pull_requests
                  JOIN stories
                    ON stage_stories_pull_requests.story_key = stories.story_key
                  JOIN pull_requests
                    ON (
                      stage_stories_pull_requests.pr_owner = pull_requests.pr_owner
                      AND stage_stories_pull_requests.pr_repository = pull_requests.pr_repository
                      AND stage_stories_pull_requests.pr_number = pull_requests.pr_number
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
                    story_key,
                    pr_count
                )
                VALUES (?, ?)
                """,
                stories_pull_request_counts,
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
        finally:
            if conn:
                conn.close()

    def retrieve_pull_requests_without_details(
        self,
        limit: int = 0,
    ) -> list[PullRequestIdentifier]:
        """Gets pull request URLs that have no details from the database.

        Args:
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value set in constructor.

        Returns:
            list[PullRequestIdentifier]: List of PullRequestIdentifier objects

        Raises:
            Exception: If there's an error querying the database
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                f"""
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
            )

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
        finally:
            if conn:
                # Close the connection
                conn.close()

        return pull_requests

    def save_pull_request_details(
        self, pull_request_details, sqlite_path=None
    ) -> None:
        """Saves detailed information about each GitHub pull request to the
            database.

        Args:
            pull_request_details: List of PullRequest objects with details
            sqlite_path (str, optional): The path to the SQLite database file.
                Defaults to the value set in constructor.

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


def main():
    """Main entry point of the application."""
    # Prevent loading
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
