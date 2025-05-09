import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import date
import pandas as pd
import matplotlib.pyplot as plt
import sqlite3

from dora_lead_time.lead_time_report import LeadTimeReport, LeadTimeResult


def test_init():
    # Test initialization with explicit path
    test_db_path = "test_database.db"
    report = LeadTimeReport(test_db_path)
    assert report.sqlite_path == test_db_path

    # Test initialization with environment variable
    with patch.dict(os.environ, {"SQLITE_PATH": "env_db_path.db"}):
        report = LeadTimeReport()
        assert report.sqlite_path == "env_db_path.db"


@patch('sqlite3.connect')
def test_get_connection(mock_connect):
    # Setup mock connection
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    # Call the method
    report = LeadTimeReport("test_db_path")
    conn = report._get_connection()

    # Check if connect was called
    mock_connect.assert_called_once()
    assert conn == mock_conn


@patch('sqlite3.connect')
def test_calculate_lead_time(mock_connect):
    # Setup mock cursor and connection
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    # Setup mock query result
    mock_cursor.fetchall.return_value = [(10.5, 5)]

    # Call the method
    report = LeadTimeReport("test_db_path")
    project_keys = ["TEST1", "TEST2"]
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)
    result = report.calculate_lead_time(project_keys, start_date, end_date)

    # Verify the result
    assert isinstance(result, LeadTimeResult)
    assert result.average_lead_time == 10.5
    assert result.number_of_releases == 5
    assert result.project_keys == project_keys
    assert result.start_date == start_date
    assert result.end_date == end_date


@patch('sqlite3.connect')
def test_calculate_lead_time_error(mock_connect):
    # Setup mock to raise exception
    mock_connect.side_effect = sqlite3.Error("Test error")

    report = LeadTimeReport("test_db_path")
    project_keys = ["TEST1", "TEST2"]
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)

    # Call should handle the error gracefully
    result = report.calculate_lead_time(project_keys, start_date, end_date)

    # Should return default values
    assert result.average_lead_time == 0.0
    assert result.number_of_releases == 0


@patch.object(LeadTimeReport, 'calculate_lead_time')
def test_monthly_lead_time_report(mock_calculate_lead_time):
    # Setup mock return values for different months
    def mock_lead_time(project_keys, start_date, end_date):
        month = start_date.month
        return LeadTimeResult(
            project_keys=project_keys,
            start_date=start_date,
            end_date=end_date,
            average_lead_time=10.0 * month,
            number_of_releases=month
        )

    mock_calculate_lead_time.side_effect = mock_lead_time

    report = LeadTimeReport("test_db_path")
    project_keys = ["TEST1", "TEST2"]
    start_date = date(2023, 1, 1)
    end_date = date(2023, 3, 31)
    result_df = report.monthly_lead_time_report(project_keys, start_date, end_date)

    # Verify the DataFrame structure and contents
    assert isinstance(result_df, pd.DataFrame)
    assert len(result_df) == 3  # 3 months
    assert list(result_df.columns) == ["Month", "Lead Time", "Releases"]
    assert list(result_df["Lead Time"]) == [10, 20, 30]
    assert list(result_df["Releases"]) == [1, 2, 3]


def test_show_plot():
    # Create a sample DataFrame
    data = {
        "Month": ["Jan", "Feb", "Mar", "Apr"],
        "Lead Time": [10, 15, 12, 8],
        "Releases": [5, 8, 6, 10]
    }
    df = pd.DataFrame(data)

    plt.close('all')  # Close any existing plots
    report = LeadTimeReport("test_db_path")

    plot = report.show_plot(df, title="Test Plot")
    assert plot is not None
    plt.close('all')


def test_lead_time_result():
    # Test creating a LeadTimeResult instance
    project_keys = ["TEST1", "TEST2"]
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)
    average_lead_time = 10.5
    number_of_releases = 5

    result = LeadTimeResult(
        project_keys=project_keys,
        start_date=start_date,
        end_date=end_date,
        average_lead_time=average_lead_time,
        number_of_releases=number_of_releases
    )

    # Verify the attributes
    assert result.project_keys == project_keys
    assert result.start_date == start_date
    assert result.end_date == end_date
    assert result.average_lead_time == average_lead_time
    assert result.number_of_releases == number_of_releases
