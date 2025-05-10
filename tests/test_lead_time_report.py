import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock
from datetime import date
import pandas as pd
import matplotlib.pyplot as plt
import sqlite3
from pathlib import Path

from dora_lead_time.lead_time_report import LeadTimeReport, LeadTimeResult


@pytest.fixture
def temp_db_file():
    """Fixture to create a temporary database file."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
        db_path = temp_file.name

    # Make sure the file exists for the test
    Path(db_path).touch()

    yield db_path

    # Cleanup the temporary file
    if os.path.exists(db_path):
        os.remove(db_path)


def test_init(temp_db_file):
    # Test initialization with explicit path
    report = LeadTimeReport(temp_db_file)
    assert report.sqlite_path == temp_db_file


@patch('sqlite3.connect')
def test_get_connection(mock_connect, temp_db_file):
    # Setup mock connection
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    # Call the method
    report = LeadTimeReport(temp_db_file)
    conn = report._get_connection()

    # Check if connect was called
    mock_connect.assert_called_once()
    assert conn == mock_conn


@patch('sqlite3.connect')
def test_calculate_lead_time(mock_connect, temp_db_file):
    # Setup mock cursor and connection
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    # Setup mock query result
    mock_cursor.fetchall.return_value = [(10.5, 5)]

    # Call the method
    report = LeadTimeReport(temp_db_file)
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
def test_calculate_lead_time_error(mock_connect, temp_db_file):
    # Setup mock to raise exception
    mock_connect.side_effect = sqlite3.Error("Test error")

    report = LeadTimeReport(temp_db_file)
    project_keys = ["TEST1", "TEST2"]
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)

    # Call should handle the error gracefully
    result = report.calculate_lead_time(project_keys, start_date, end_date)

    # Should return default values
    assert result.average_lead_time == 0.0
    assert result.number_of_releases == 0


@patch.object(LeadTimeReport, 'calculate_lead_time')
def test_monthly_lead_time_report(mock_calculate_lead_time, temp_db_file):
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

    report = LeadTimeReport(temp_db_file)
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


def test_show_plot(temp_db_file):
    # Create a sample DataFrame
    data = {
        "Month": ["Jan", "Feb", "Mar", "Apr"],
        "Lead Time": [10, 15, 12, 8],
        "Releases": [5, 8, 6, 10]
    }
    df = pd.DataFrame(data)

    plt.close('all')  # Close any existing plots
    report = LeadTimeReport(temp_db_file)

    plot = report._create_plot(df, title="Test Plot")
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
