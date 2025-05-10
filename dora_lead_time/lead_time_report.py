"""Database operations to create releases database."""

import logging
import os
from typing import NamedTuple
from datetime import date, datetime
import sqlite3
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

    def __init__(self, sqlite_path: str):
        """Initialize the report generator with database path.

        Args:
            sqlite_path: Path to SQLite database file.
                Defaults to the value from the SQLITE_PATH
                environment variable.
        """
        if not sqlite_path or not os.path.exists(sqlite_path):
            raise ValueError(f"SQLite database file not found: {sqlite_path}")

        self.sqlite_path = sqlite_path

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
        self,
        project_keys: list[str],
        start_date: date,
        end_date: date
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

    def _create_plot(
        self,
        df: pd.DataFrame,
        title: str = "",
        footer: str = ""
    ) -> plt.Figure:
        """
        Create a plot of lead time data.

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

        # plt.style.use("fivethirtyeight")

        plt.figure(figsize=(16, 9))
        fig, ax = plt.subplots()
        fig.patch.set_facecolor('whitesmoke')
        ax.set_facecolor('whitesmoke')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color('gray')
        ax.spines['left'].set_color('gray')
        ax.set_box_aspect(9/16)
        ax.tick_params(axis='both', colors='gray')

        xlabel = df.columns[0]
        plt.xlabel(xlabel, color='gray')
        plt.ylabel("Values", color='gray')
        plt.title(title, pad=20)

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

        x = np.arange(len(df[xlabel]))
        plt.xticks(x, df[xlabel], rotation=45)
        legend = plt.legend(
            fontsize=9,
            facecolor="whitesmoke",
            frameon=False
        )
        for text in legend.get_texts():
            text.set_color("gray")

        # Add footer
        plt.figtext(
            0.5, 0.1,  # x, y position (centered, bottom)
            footer,
            ha='center',  # horizontal alignment
            fontsize=9
        )
        # Add extra space at the bottom for the footer
        plt.subplots_adjust(bottom=0.3)

        return plt

    def create_lead_time_chart(
        self,
        project_keys: list[str],
        start_date: date,
        end_date: date,
        title: str
    ) -> plt.Figure:
        """Generate and save a lead time chart.

        Args:
            project_keys (list): List of project keys to include in the chart
            title (str): Title for the chart
            filename (str): Filename to save the chart (without extension)
        """
        logger.info("Generating chart: %s", title)

        lead_time = self.calculate_lead_time(
            project_keys,
            start_date,
            end_date
        )
        lead_time_summary = \
            "Lead time for changes is " \
            f"{int(lead_time.average_lead_time)} days average " \
            f"over {lead_time.number_of_releases} releases"

        # Generate monthly lead time report
        df = self.monthly_lead_time_report(
            project_keys, start_date, end_date
        )
        if not df.empty and df["Lead Time"].sum() > 0:
            plot = self._create_plot(
                df,
                title=title,
                footer=lead_time_summary
            )
            return plot
        else:
            logger.warning(
                "No lead time data for %s, skipping chart creation",
                title
            )
            return None


def main():
    """Main entry point of the application."""
    # Prevent loading
    raise RuntimeError("This script should not be run directly")


if __name__ == "__main__":
    main()
