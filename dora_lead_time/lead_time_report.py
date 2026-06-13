"""Database operations to create releases database."""

import logging
import os
from typing import NamedTuple
from datetime import date
import sqlite3
import pandas as pd
from pandas import DataFrame
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np
from dora_lead_time.database_processor import make_sqlite_connection
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
        mean_lead_time: The mean lead time (in days) for the specified period.
        median_lead_time: The median lead time (in days) for the period.
        pull_request_count: Number of pull requests included in the metric.
    """

    project_keys: list[str]
    start_date: date
    end_date: date
    # Results
    mean_lead_time: float
    median_lead_time: float
    pull_request_count: int


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
        conn = make_sqlite_connection(self.sqlite_path)

        return conn

    def calculate_lead_time(
        self,
        project_keys: list[str],
        start_date: date,
        end_date: date
    ) -> LeadTimeResult:
        """Calculate lead time for project releases between two dates.

        Calculates mean and median lead times plus pull-request count for the
        specified projects within the given date range.

        Args:
            project_keys: List of project keys to include (e.g., ['PR', 'TS']).
            start_date: Start date for the time period (inclusive).
            end_date: End date for the time period (inclusive).

        Returns:
            A LeadTimeResult named tuple containing mean lead time, median
            lead time, pull-request count, and input parameters.

        Raises:
            sqlite3.Error: If there's an error querying the database.
        """
        try:
            lead_times_df = self._load_lead_times_dataframe(
                project_keys,
                start_date,
                end_date
            )
            if lead_times_df.empty:
                return LeadTimeResult(
                    project_keys=project_keys,
                    start_date=start_date,
                    end_date=end_date,
                    mean_lead_time=0.0,
                    median_lead_time=0.0,
                    pull_request_count=0,
                )

            return LeadTimeResult(
                project_keys=project_keys,
                start_date=start_date,
                end_date=end_date,
                mean_lead_time=float(lead_times_df["lead_time"].mean()),
                median_lead_time=float(lead_times_df["lead_time"].median()),
                pull_request_count=int(lead_times_df["lead_time"].count()),
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
                project_keys=project_keys,
                start_date=start_date,
                end_date=end_date,
                mean_lead_time=0.0,
                median_lead_time=0.0,
                pull_request_count=0,
            )

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
            A pandas DataFrame with columns for Month, Mean Lead Time, and
            Median Lead Time containing monthly metrics for the period.
        """
        month_names = [
            f"{year}-{month}"
            for year, month in DateUtility.get_months_between(
                start_date, end_date
            )
        ]
        monthly_frame = pd.DataFrame({"Month": month_names})

        lead_times_df = self._load_lead_times_dataframe(
            project_keys,
            start_date,
            end_date
        )
        if lead_times_df.empty:
            monthly_frame["Mean Lead Time"] = 0
            monthly_frame["Median Lead Time"] = 0
            return monthly_frame

        lead_times_df["release_date"] = pd.to_datetime(
            lead_times_df["release_date"]
        )
        lead_times_df["Month"] = (
            lead_times_df["release_date"].dt.year.astype(str)
            + "-"
            + lead_times_df["release_date"].dt.month.astype(str)
        )

        grouped_metrics = (
            lead_times_df
            .groupby("Month")["lead_time"]
            .agg(["mean", "median"])
            .reset_index()
        )
        monthly_frame = monthly_frame.merge(
            grouped_metrics,
            on="Month",
            how="left"
        ).fillna(0)
        monthly_frame["Mean Lead Time"] = (
            monthly_frame["mean"].round().astype(int)
        )
        monthly_frame["Median Lead Time"] = (
            monthly_frame["median"].round().astype(int)
        )

        return monthly_frame[["Month", "Mean Lead Time", "Median Lead Time"]]

    def _load_lead_times_dataframe(
        self,
        project_keys: list[str],
        start_date: date,
        end_date: date
    ) -> DataFrame:
        """Load lead-time rows into a pandas DataFrame for aggregation."""
        conn = None
        try:
            conn = self._get_connection()
            project_keys_placeholders = ", ".join(["?"] * len(project_keys))
            query = f"""
            SELECT
                lead_times.release_date,
                lead_times.lead_time
            FROM
                lead_times
            WHERE
                lead_times.project_key
                    IN ({project_keys_placeholders})
                AND lead_times.lead_time > 0
                AND lead_times.release_date
                    BETWEEN ? AND ?
            """
            return pd.read_sql_query(
                query,
                conn,
                params=project_keys + [start_date, end_date]
            )
        finally:
            if conn:
                conn.close()

    def _create_plot(
        self,
        df: pd.DataFrame,
        title: str = "",
        footer: str = ""
    ) -> Figure:
        """
        Create a plot of lead time data.

        Generates a matplotlib plot visualization of the lead time data.

        Args:
            df: A pandas DataFrame with at least one column for the x-axis
                (typically "Month") and one or more data series columns.
            title: Optional title for the plot. Defaults to empty string.

        Returns:
            A matplotlib Figure object representing the plot.
        """
        colors = ["blue", "cyan", "red", "pink"]

        # plt.style.use("fivethirtyeight")

        fig, ax = plt.subplots(figsize=(16, 9))
        fig.patch.set_facecolor('whitesmoke')
        ax.set_facecolor('whitesmoke')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color('gray')
        ax.spines['left'].set_color('gray')
        ax.set_box_aspect(9/16)
        ax.tick_params(axis='both', colors='gray')

        xlabel = df.columns[0]
        ax.set_xlabel(xlabel, color='gray')
        ax.set_ylabel("Values", color='gray')
        ax.set_title(title, pad=20)

        for idx, column in enumerate(df.columns[1:]):
            x = np.arange(len(df[xlabel]))
            y = df[column]

            if idx % 2 == 0:
                linestyle = "-"
            else:
                linestyle = "--"
            ax.plot(
                x, y,
                label=column,
                linestyle=linestyle, marker="o",
                color=colors[idx]
            )

        x = np.arange(len(df[xlabel]))
        ax.set_xticks(x)
        ax.set_xticklabels(df[xlabel], rotation=45)
        legend = ax.legend(
            fontsize=9,
            facecolor="whitesmoke",
            frameon=False
        )
        for text in legend.get_texts():
            text.set_color("gray")

        # Add footer
        fig.text(
            0.5, 0.1,  # x, y position (centered, bottom)
            footer,
            ha='center',  # horizontal alignment
            fontsize=9
        )
        # Add extra space at the bottom for the footer
        fig.subplots_adjust(bottom=0.3)

        return fig

    def create_lead_time_chart(
        self,
        project_keys: list[str],
        start_date: date,
        end_date: date,
        title: str
    ) -> Figure | None:
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
            f"Mean lead time: {round(lead_time.mean_lead_time)} days · " \
            f"Median lead time: {round(lead_time.median_lead_time)} days · " \
            f"{lead_time.pull_request_count} pull requests"

        # Generate monthly lead time report
        df = self.monthly_lead_time_report(
            project_keys, start_date, end_date
        )
        if (
            not df.empty
            and (
                df["Mean Lead Time"].sum() > 0
                or df["Median Lead Time"].sum() > 0
            )
        ):
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
