"""Database operations to create releases database."""

import logging
import os
from typing import NamedTuple
from datetime import date, datetime
import sqlite3
from dotenv import load_dotenv
import pandas as pd
from pandas import DataFrame
import matplotlib.pyplot as plt
import numpy as np
from dora_lead_time.date_utility import DateUtility

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
)
logger = logging.getLogger(__name__)


class LeadTimeResult(NamedTuple):
    """Result of a lead time calculation for a specific time period.

    Represents the aggregated lead time metrics for a set of projects
    over a specified time period.

    Attributes:
        project_keys: A list of project keys for which the calculation
            was performed.
        start_date: The start date of the period for which lead time
            was calculated.
        end_date: The end date of the period for which lead time
            was calculated.
        average_lead_time: The average lead time (in days) for the
            specified period.
        number_of_releases: The total number of releases during the
            specified period.
    """

    project_keys: list[str]
    start_date: date
    end_date: date
    # Results
    average_lead_time: float
    number_of_releases: int


class LeadTimeReport:
    """Lead time calculation and reporting for DORA metrics.

    Provides methods to calculate and visualize lead time metrics for
    project releases according to the DORA (DevOps Research and Assessment)
    methodology.

    Attributes:
        sqlite_path: Path to the SQLite database file containing release data.
    """

    def __init__(self, sqlite_path=None):
        """Initialize the report generator with database path.

        Args:
            sqlite_path: Path to SQLite database file.
                Defaults to the value from the SQLITE_PATH
                environment variable.
        """
        load_dotenv()
        self.sqlite_path = sqlite_path or os.getenv("SQLITE_PATH")
        if not self.sqlite_path:
            logger.info("SQLite location not set")

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

    def calculate_lead_time(
        self, project_keys: list[str], start_date: date, end_date: date
    ) -> LeadTimeResult:
        """Calculate lead time for project releases between two dates.

        Calculates the average lead time and number of releases for the
        specified projects within the given date range.

        Args:
            project_keys: List of project keys to include (e.g., ['PR', 'TS']).
            start_date: Start date for the time period (inclusive).
            end_date: End date for the time period (inclusive).

        Returns:
            A LeadTimeResult named tuple containing the average lead time,
            number of releases, and input parameters.

        Raises:
            sqlite3.Error: If there's an error querying the database.
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Prepare the SQL query with placeholders for the IN clause
            # and date range
            project_keys_placeholders = ", ".join(["?"] * len(project_keys))
            query = f"""
            SELECT
                CASE WHEN COUNT(lead_times.lead_time) = 0
                    THEN 0
                    ELSE AVG(lead_times.lead_time)
                END
                AS average_lead_time,
                COUNT(lead_times.lead_time) AS number_of_releases
            FROM
                lead_times
            WHERE
                lead_times.project_key
                    IN ({project_keys_placeholders})
                AND lead_times.release_date
                    BETWEEN ? AND ?
            """

            cursor.execute(query, project_keys + [start_date, end_date])

            avg_lead_time, num_releases = cursor.fetchall()[0]
            return LeadTimeResult(
                project_keys=project_keys,
                start_date=start_date,
                end_date=end_date,
                average_lead_time=avg_lead_time,
                number_of_releases=num_releases,
            )
        except sqlite3.Error as e:
            logger.error(
                """
                %s
                Could not calculate lead times for projects:
                %s
                """,
                e,
                project_keys,
            )
            return LeadTimeResult(
                average_lead_time=0.0,
                number_of_releases=0,
                project_keys=project_keys,
                start_date=start_date,
                end_date=end_date,
            )
        finally:
            if conn:
                conn.close()

    def monthly_lead_time_report(
        self, project_keys: list[str], start_date: date, end_date: date
    ) -> DataFrame:
        """Generate a monthly lead time report for the given projects.

        Creates a report with monthly lead time metrics for the specified
        projects within the given date range.

        Args:
            project_keys: List of project keys to include in the report.
            start_date: Start date for the report period (inclusive).
            end_date: End date for the report period (inclusive).

        Returns:
            A pandas DataFrame with columns for Month, Lead Time, and Releases,
            containing the monthly metrics for the specified time period.
        """

        month_names = []
        lead_times = []
        number_of_releases = []

        months = DateUtility.get_months_between(start_date, end_date)
        for year, month in months:
            month_details = DateUtility.get_month_start_end(year, month)
            lead_time = self.calculate_lead_time(
                project_keys, month_details.start_date, month_details.end_date
            )
            month_names.append(f"{year}-{month}")
            lead_times.append(int(lead_time.average_lead_time))
            number_of_releases.append(lead_time.number_of_releases)

        lead_times_frame = {}
        lead_times_frame["Month"] = month_names
        lead_times_frame["Lead Time"] = lead_times
        lead_times_frame["Releases"] = number_of_releases

        monthly_lead_time_report_data_frame = pd.DataFrame(lead_times_frame)
        return monthly_lead_time_report_data_frame

    def show_plot(
        self,
        df: pd.DataFrame,
        title: str = "",
        show_trend: bool = False,
    ) -> plt.Figure:
        """Create a plot of lead time data.

        Generates a matplotlib plot visualization of the lead time data,
        optionally including trend lines.

        Args:
            df: A pandas DataFrame with at least one column for the x-axis
                (typically "Month") and one or more data series columns.
            title: Optional title for the plot. Defaults to empty string.
            show_trend: Whether to display trend lines for each series.
                Defaults to False.

        Returns:
            A matplotlib Figure object representing the plot.
        """
        colors = ["blue", "cyan", "red", "pink"]

        plt.figure(figsize=(10, 5))

        xlabel = df.columns[0]
        plt.xlabel(xlabel)
        plt.ylabel("Values")
        plt.title(title)

        for idx, column in enumerate(df.columns[1:]):
            x = np.arange(len(df[xlabel]))
            y = df[column]

            if idx % 2 == 0:
                linestyle = "-"
            else:
                linestyle = "--"
            plt.plot(
                x, y,
                label=column,
                linestyle=linestyle, marker="o",
                color=colors[idx]
            )

            if show_trend:
                # Fit a trend line
                z = np.polyfit(x, y, 1)
                p = np.poly1d(z)
                plt.plot(x, p(x), linestyle="--")

        x = np.arange(len(df[xlabel]))
        plt.xticks(x, df[xlabel], rotation=45)

        plt.legend()

        return plt


def main():
    """Main entry point of the application."""
    # Prevent loading
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
