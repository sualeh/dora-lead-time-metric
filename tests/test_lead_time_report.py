"""Unit tests for LeadTimeReport and LeadTimeResult."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import date
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import sqlite3

from dora_lead_time.database_processor import DatabaseProcessor
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


@patch.object(LeadTimeReport, '_load_lead_times_dataframe')
def test_calculate_lead_time(mock_load_lead_times, tmp_path):
    """Test calculate_lead_time returns a populated LeadTimeResult."""
    mock_load_lead_times.return_value = pd.DataFrame(
        {"release_date": ["2023-01-01", "2023-01-02"], "lead_time": [10, 11]}
    )

    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    project_keys = ["TEST1", "TEST2"]
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)
    result = report.calculate_lead_time(project_keys, start_date, end_date)

    assert isinstance(result, LeadTimeResult)
    assert result.mean_lead_time == 10.5
    assert result.median_lead_time == 10.5
    assert result.pull_request_count == 2
    assert result.project_keys == project_keys
    assert result.start_date == start_date
    assert result.end_date == end_date


@patch.object(LeadTimeReport, '_load_lead_times_dataframe')
def test_calculate_lead_time_error(mock_load_lead_times, tmp_path):
    """Test calculate_lead_time returns safe defaults on database error."""
    mock_load_lead_times.side_effect = sqlite3.Error("Test error")

    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    result = report.calculate_lead_time(
        ["TEST1", "TEST2"], date(2023, 1, 1), date(2023, 12, 31)
    )

    assert result.mean_lead_time == 0.0
    assert result.median_lead_time == 0.0
    assert result.pull_request_count == 0


def test_calculate_lead_time_deduplicates_same_pr_linked_to_two_stories(
    tmp_path,
):
    """A PR linked via two stories in one release should count once."""
    db_path = tmp_path / "lead_time_dedup.db"

    processor = DatabaseProcessor(str(db_path))
    processor.create_schema()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO projects (
            id, project_internal_id, project_key, project_title, project_type
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (1, "P-1", "TEST", "Test Project", "software"),
    )
    cursor.execute(
        """
        INSERT INTO releases (
            id, release_internal_id, release_title, release_description,
            release_date, project_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, "R-1", "Release 1", "", "2024-01-10", 1),
    )

    cursor.executemany(
        """
        INSERT INTO stories (
            id, story_internal_id, story_key, story_title, story_type,
            story_created, story_resolved
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "S-1", "TEST-1", "Story 1", "Story", "2024-01-01", "2024-01-09"),
            (2, "S-2", "TEST-2", "Story 2", "Story", "2024-01-02", "2024-01-09"),
        ],
    )
    cursor.executemany(
        """
        INSERT INTO releases_stories (release_id, story_id)
        VALUES (?, ?)
        """,
        [(1, 1), (1, 2)],
    )

    cursor.executemany(
        """
        INSERT INTO pull_requests (
            id, pr_title, pr_owner, pr_repository, pr_number, pr_open, pr_close,
            commit_count, earliest_commit_date, latest_commit_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "Shared PR", "acme", "repo", "1", "2024-01-03", "2024-01-08",
             2, "2024-01-05", "2024-01-08"),
            (2, "Unique PR", "acme", "repo", "2", "2024-01-01", "2024-01-09",
             3, "2024-01-01", "2024-01-09"),
        ],
    )
    cursor.executemany(
        """
        INSERT INTO stories_pull_requests (story_id, pr_id)
        VALUES (?, ?)
        """,
        [(1, 1), (2, 1), (1, 2)],
    )

    conn.commit()
    conn.close()

    report = LeadTimeReport(str(db_path))
    result = report.calculate_lead_time(
        ["TEST"], date(2024, 1, 1), date(2024, 1, 31)
    )

    # PR 1 lead time = 5 days, PR 2 lead time = 9 days.
    assert result.mean_lead_time == pytest.approx(7.0)
    assert result.median_lead_time == pytest.approx(7.0)
    assert result.pull_request_count == 2


@patch.object(LeadTimeReport, '_load_lead_times_dataframe')
def test_monthly_lead_time_report(mock_load_lead_times, tmp_path):
    """Test monthly_lead_time_report includes mean and median metrics."""
    mock_load_lead_times.return_value = pd.DataFrame(
        {
            "release_date": [
                "2023-01-05",
                "2023-01-20",
                "2023-02-03",
                "2023-02-10",
            ],
            "lead_time": [10, 20, 5, 9],
        }
    )

    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    result_df = report.monthly_lead_time_report(
        ["TEST1", "TEST2"], date(2023, 1, 1), date(2023, 3, 31)
    )

    assert isinstance(result_df, pd.DataFrame)
    assert len(result_df) == 3
    assert list(result_df.columns) == [
        "Month", "Median Lead Time", "Mean Lead Time"
    ]
    assert list(result_df["Mean Lead Time"]) == [15, 7, 0]
    assert list(result_df["Median Lead Time"]) == [15, 7, 0]


@patch.object(LeadTimeReport, '_create_plot')
@patch.object(LeadTimeReport, 'monthly_lead_time_report')
@patch.object(LeadTimeReport, 'calculate_lead_time')
def test_create_lead_time_chart_uses_median_caption_and_summary(
    mock_calculate_lead_time,
    mock_monthly_lead_time_report,
    mock_create_plot,
    tmp_path,
):
    """Test chart caption and footer use the simplified median-first text."""
    mock_calculate_lead_time.return_value = LeadTimeResult(
        project_keys=["TEST1"],
        start_date=date(2023, 1, 1),
        end_date=date(2023, 1, 31),
        mean_lead_time=10.2,
        median_lead_time=9.4,
        pull_request_count=5,
    )
    mock_monthly_lead_time_report.return_value = pd.DataFrame(
        {
            "Month": ["2023-01"],
            "Median Lead Time": [9],
            "Mean Lead Time": [10],
        }
    )
    mock_create_plot.return_value = MagicMock(spec=Figure)

    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    report.create_lead_time_chart(
        ["TEST1"], date(2023, 1, 1), date(2023, 1, 31), "Test Plot"
    )

    assert mock_create_plot.call_count == 1
    assert mock_create_plot.call_args.kwargs["title"] == (
        "Lead Time between Jan 1, 2023 to Jan 31, 2023"
    )
    assert mock_create_plot.call_args.kwargs["footer"] == (
        "Median lead time: 9 days · 5 pull requests"
    )


def test_show_plot(tmp_path):
    """Test _create_plot returns a matplotlib Figure and no extra figure."""
    data = {
        "Month": ["Jan", "Feb", "Mar", "Apr"],
        "Median Lead Time": [9, 11, 10, 7],
        "Mean Lead Time": [10, 15, 12, 8],
    }
    df = pd.DataFrame(data)

    plt.close('all')
    db_path = tmp_path / "test.db"
    db_path.touch()
    report = LeadTimeReport(str(db_path))
    fig = report._create_plot(df, title="Test Plot")
    assert isinstance(fig, Figure)
    assert len(plt.get_fignums()) == 1
    assert [
        text.get_text() for text in fig.axes[0].get_legend().get_texts()
    ] == ["Median Lead Time", "Mean Lead Time"]
    plt.close('all')


def test_lead_time_result():
    """Test LeadTimeResult stores all fields correctly."""
    project_keys = ["TEST1", "TEST2"]
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)
    mean_lead_time = 10.5
    median_lead_time = 9.0
    pull_request_count = 5

    result = LeadTimeResult(
        project_keys=project_keys,
        start_date=start_date,
        end_date=end_date,
        mean_lead_time=mean_lead_time,
        median_lead_time=median_lead_time,
        pull_request_count=pull_request_count
    )

    assert result.project_keys == project_keys
    assert result.start_date == start_date
    assert result.end_date == end_date
    assert result.mean_lead_time == mean_lead_time
    assert result.median_lead_time == median_lead_time
    assert result.pull_request_count == pull_request_count
