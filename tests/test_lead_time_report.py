"""Unit tests for LeadTimeReport and LeadTimeResult."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import date
import pandas as pd
import matplotlib.pyplot as plt
import sqlite3

from dora_lead_time.lead_time_report import LeadTimeReport, LeadTimeResult


def test_init(tmp_path):
    """Test initialization stores sqlite_path."""
    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    assert report.sqlite_path == str(db_path)


@patch('sqlite3.connect')
def test_get_connection(mock_connect, tmp_path):
    """Test that _get_connection calls sqlite3.connect."""
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    conn = report._get_connection()

    mock_connect.assert_called_once()
    assert conn == mock_conn


@patch('sqlite3.connect')
def test_calculate_lead_time(mock_connect, tmp_path):
    """Test calculate_lead_time returns a populated LeadTimeResult."""
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn
    mock_cursor.fetchall.return_value = [(10.5, 5)]

    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    project_keys = ["TEST1", "TEST2"]
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)
    result = report.calculate_lead_time(project_keys, start_date, end_date)

    assert isinstance(result, LeadTimeResult)
    assert result.average_lead_time == 10.5
    assert result.number_of_releases == 5
    assert result.project_keys == project_keys
    assert result.start_date == start_date
    assert result.end_date == end_date


@patch('sqlite3.connect')
def test_calculate_lead_time_error(mock_connect, tmp_path):
    """Test calculate_lead_time returns safe defaults on database error."""
    mock_connect.side_effect = sqlite3.Error("Test error")

    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    result = report.calculate_lead_time(
        ["TEST1", "TEST2"], date(2023, 1, 1), date(2023, 12, 31)
    )

    assert result.average_lead_time == 0.0
    assert result.number_of_releases == 0


@patch.object(LeadTimeReport, 'calculate_lead_time')
def test_monthly_lead_time_report(mock_calculate_lead_time, tmp_path):
    """Test monthly_lead_time_report produces a DataFrame with correct values."""
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

    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    result_df = report.monthly_lead_time_report(
        ["TEST1", "TEST2"], date(2023, 1, 1), date(2023, 3, 31)
    )

    assert isinstance(result_df, pd.DataFrame)
    assert len(result_df) == 3
    assert list(result_df.columns) == ["Month", "Lead Time", "Releases"]
    assert list(result_df["Lead Time"]) == [10, 20, 30]
    assert list(result_df["Releases"]) == [1, 2, 3]


def test_show_plot(tmp_path):
    """Test _create_plot returns a non-None plot object."""
    data = {
        "Month": ["Jan", "Feb", "Mar", "Apr"],
        "Lead Time": [10, 15, 12, 8],
        "Releases": [5, 8, 6, 10]
    }
    df = pd.DataFrame(data)

    plt.close('all')
    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    plot = report._create_plot(df, title="Test Plot")
    assert plot is not None
    plt.close('all')


def test_lead_time_result():
    """Test LeadTimeResult stores all fields correctly."""
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

    assert result.project_keys == project_keys
    assert result.start_date == start_date
    assert result.end_date == end_date
    assert result.average_lead_time == average_lead_time
    assert result.number_of_releases == number_of_releases
