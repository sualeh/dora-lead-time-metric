"""Database queries for outlier analysis reports."""

import logging
import os
from datetime import date, datetime
import pathlib
import sqlite3
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
)
logger = logging.getLogger(__name__)


class OutlierReports:
    """Database queries for generating outlier analysis reports.

    This class provides methods to identify potential issues or anomalies
    in the DORA lead time data, such as releases with open pull requests,
    stories without pull requests, etc.

    Attributes:
        sqlite_path: Path to the SQLite database file.
        sql_dir: Directory path where SQL query files are stored.
    """

    def __init__(self, sqlite_path: str):
        """Initialize the database processor with database path.

        Args:
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value from SQLITE_PATH environment variable.
        """
        if not sqlite_path or not os.path.exists(sqlite_path):
            raise ValueError("SQLite location not set")
        self.sqlite_path = sqlite_path

        # Create a directory for SQL files if it doesn't exist
        sql_dir = pathlib.Path(__file__).parent / "outlier_reports"
        sql_dir.mkdir(exist_ok=True)
        self.sql_dir = sql_dir

    def _get_connection(self):
        """Get a SQLite connection with proper type handling.

        Creates a connection to the SQLite database with appropriate type
        converters for dates and timestamps.

        Returns:
            sqlite3.Connection: A connection to the SQLite database with
            properly configured type handling.
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

    def _read_sql_file(self, filename: str) -> str:
        """Read SQL query from a file.

        Args:
            filename: Name of the SQL file (without directory path)
                The .sql extension will be added if not present.

        Returns:
            The SQL query content as a string.

        Raises:
            FileNotFoundError: If the SQL file doesn't exist.
        """
        if not filename.endswith(".sql"):
            filename += ".sql"
        sql_path = self.sql_dir / filename
        if not sql_path.exists():
            raise FileNotFoundError(f"SQL file {sql_path} not found")

        with open(sql_path, "r", encoding="utf-8") as f:
            return f.read()

    def execute_query(
        self,
        sql: str,
        params: dict = None
    ) -> pd.DataFrame:
        """Execute SQL query and return results as DataFrame.

        Args:
            sql: SQL query to execute.
            params: Optional parameters to substitute in the query.

        Returns:
            Query results as a pandas DataFrame.

        Raises:
            sqlite3.Error: If query execution fails.
        """
        conn = None
        try:
            conn = self._get_connection()

            # Default to empty dict if params is None
            params = params or {}

            # Execute query and convert to DataFrame
            df = pd.read_sql_query(sql, conn, params=params)
            logger.debug("Query returned %d rows", len(df))
            return df

        except sqlite3.Error as e:
            logger.error("Error executing query: %s", e)
            # Return empty DataFrame on error
            return pd.DataFrame()
        finally:
            if conn:
                conn.close()

    def report_projects_without_releases(self) -> pd.DataFrame:
        """Get projects that have no releases in the recent time period.

        Identifies projects that haven't had any releases in the past 60 days,
        which may indicate stalled projects or incomplete data.

        Returns:
            DataFrame containing projects without releases in the
            recent period.
        """
        sql = self._read_sql_file("A_projects_without_releases")
        return self.execute_query(sql)

    def report_releases_with_open_stories(self) -> pd.DataFrame:
        """Get releases with stories that weren't resolved at release time.

        Identifies potential quality issues where releases went out with
        unresolved stories, which could indicate process problems.

        Returns:
            DataFrame of releases with stories that were not closed/resolved
            at the time of release, showing story details and days_open.
        """
        sql = self._read_sql_file("B_releases_with_open_stories")
        return self.execute_query(sql)

    def report_stories_in_multiple_releases(self) -> pd.DataFrame:
        """Get stories that appear in multiple releases.

        Identifies stories that are counted in more than one release, which
        could skew lead time metrics or indicate process issues.

        Returns:
            DataFrame of stories included in more than one release,
            with details about which releases they appear in.
        """
        sql = self._read_sql_file("C_stories_in_multiple_releases")
        return self.execute_query(sql)

    def report_releases_with_open_pull_requests(self) -> pd.DataFrame:
        """Get releases with pull requests that were still open at release.

        Identifies releases where code changes were not fully merged before
        the release was published, which could indicate process issues.

        Returns:
            DataFrame of releases with pull requests that were still open
            at the time of release, with details about days_open.
        """
        sql = self._read_sql_file("D_releases_with_open_pull_requests")
        return self.execute_query(sql)

    def report_counts_of_stories_without_pull_requests(self) -> pd.DataFrame:
        """Get counts of stories without associated pull requests by project.

        Provides a summary of projects with stories that don't have
        associated code changes, which could indicate process issues
        or incomplete data.

        Returns:
            DataFrame with a summary count of stories without pull requests
            grouped by project, including percentage calculations.
        """
        sql = self._read_sql_file("E_counts_of_stories_without_pull_requests")
        return self.execute_query(sql)

    def report_stories_without_pull_requests(self) -> pd.DataFrame:
        """Get detailed list of stories without associated pull requests.

        Provides the specific stories that don't have any associated
        code changes, which could indicate process issues or incomplete data.

        Returns:
            DataFrame with detailed information about stories that don't have
            pull requests linked to them.
        """
        sql = self._read_sql_file("E_stories_without_pull_requests")
        return self.execute_query(sql)

    def report_pull_requests_with_old_commits(self) -> pd.DataFrame:
        """Get pull requests with significantly old commits.

        Identifies pull requests where the earliest commit is much older
        than the PR open date, which could indicate long-lived branches or
        code that sat unmerged for extended periods.

        Returns:
            DataFrame with pull requests where commits are significantly older
            than the PR creation date, ordered by the age difference.
        """
        sql = self._read_sql_file("F_pull_requests_with_old_commits")
        return self.execute_query(sql)

    def report_zero_or_negative_lead_times(self) -> pd.DataFrame:
        """Get pull requests with zero or negative lead times.

        Identifies pull requests where the lead time (time between first commit
        and merge) is zero or negative, which indicates potential data quality
        issues or timestamp problems.

        Returns:
            DataFrame with pull requests having zero or negative lead times,
            ordered by lead time (ascending) and project key.
        """
        sql = self._read_sql_file("G_zero_or_negative_lead_times")
        return self.execute_query(sql)


def main():
    """Main entry point of the application."""
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
