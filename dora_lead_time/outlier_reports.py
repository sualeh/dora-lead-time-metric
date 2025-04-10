"""Database queries for outlier analysis reports."""

import logging
import os
from datetime import date, datetime
import pathlib
import sqlite3
from dotenv import load_dotenv
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
)
logger = logging.getLogger(__name__)


class OutlierReports:
    """Database queries for outlier analysis reports."""

    def __init__(self, sqlite_path: str = None):
        """Initialize the database processor with database path.

        Args:
            sqlite_path (str, optional): Path to SQLite database file.
                Defaults to the value from SQLITE_PATH environment variable.
        """
        load_dotenv()
        self.sqlite_path = sqlite_path or os.getenv("SQLITE_PATH")
        if not self.sqlite_path:
            logger.warning("SQLite location not set")

        # Create a directory for SQL files if it doesn't exist
        sql_dir = pathlib.Path(__file__).parent / "outlier_reports_sql"
        sql_dir.mkdir(exist_ok=True)
        self.sql_dir = sql_dir

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

    def _read_sql_file(self, filename: str) -> str:
        """Read SQL query from a file.

        Args:
            filename: Name of the SQL file (without directory path)

        Returns:
            str: The SQL query as a string

        Raises:
            FileNotFoundError: If the SQL file doesn't exist
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
            sql: SQL query to execute
            params: Optional parameters to substitute in the query

        Returns:
            pd.DataFrame: Query results as a DataFrame

        Raises:
            sqlite3.Error: If query execution fails
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
        """Get projects that have no releases in the specified time period.

        Returns:
            pd.DataFrame: Projects without releases in the specified time
                period
        """
        sql = self._read_sql_file("A_projects_without_releases")
        return self.execute_query(sql)

    def report_releases_with_open_stories(self) -> pd.DataFrame:
        """Get releases with stories that aren't resolved at release time.

        Returns:
            pd.DataFrame: Releases with stories that are not closed/resolved
                at the time of release
        """
        sql = self._read_sql_file("B_releases_with_open_stories")
        return self.execute_query(sql)

    def report_stories_in_multiple_releases(self) -> pd.DataFrame:
        """Get stories that appear in multiple releases.

        Returns:
            pd.DataFrame: Stories that are included in more than one release
        """
        sql = self._read_sql_file("C_stories_in_multiple_releases")
        return self.execute_query(sql)

    def report_releases_with_open_pull_requests(self) -> pd.DataFrame:
        """Get releases with pull requests that were still open at
            release time.

        Returns:
            pd.DataFrame: Releases with pull requests that were still open
                at the time of release
        """
        sql = self._read_sql_file("D_releases_with_open_pull_requests")
        return self.execute_query(sql)

    def report_counts_of_stories_without_pull_requests(self) -> pd.DataFrame:
        """Get counts of stories without associated pull requests.

        Returns:
            pd.DataFrame: A summary count of stories without pull requests
                grouped by relevant dimensions
        """
        sql = self._read_sql_file("E_counts_of_stories_without_pull_requests")
        return self.execute_query(sql)

    def report_stories_without_pull_requests(self) -> pd.DataFrame:
        """Get detailed list of stories without associated pull requests.

        Returns:
            pd.DataFrame: Detailed information about stories that don't have
                pull requests linked to them
        """
        sql = self._read_sql_file("E_stories_without_pull_requests")
        return self.execute_query(sql)


def main():
    """Main entry point of the application."""
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
