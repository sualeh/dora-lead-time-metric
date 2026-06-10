"""Unit tests for SQL-backed outlier reports."""

import sqlite3
from datetime import date, timedelta

import pytest

from dora_lead_time.database_processor import DatabaseProcessor
from dora_lead_time.outlier_reports import OutlierReports


def _iso(days_ago: int) -> str:
    """Return an ISO date string relative to today."""
    return (date.today() - timedelta(days=days_ago)).isoformat()


@pytest.fixture
def seeded_db_path(tmp_path) -> str:
    """Create a temp SQLite DB and seed data for outlier report tests."""
    db_file = tmp_path / "test_outlier_reports.db"
    db_path = str(db_file)

    processor = DatabaseProcessor(sqlite_path=db_path)
    processor.create_schema()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executemany(
        """
        INSERT INTO projects (id, project_internal_id, project_key,
                              project_title, project_type)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (1, "P-1", "PACT", "Project Active", "software"),
            (2, "P-2", "POLD", "Project Old", "software"),
            (3, "P-3", "PNRL", "Project No Releases", "software"),
        ],
    )

    cursor.executemany(
        """
        INSERT INTO releases (id, release_internal_id, release_title,
                              release_description, release_date, project_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "R-1", "Release Recent 1", "", _iso(10), 1),
            (2, "R-2", "Release Recent 2", "", _iso(5), 1),
            (3, "R-3", "Release Old", "", _iso(120), 2),
        ],
    )

    cursor.executemany(
        """
        INSERT INTO stories (id, story_internal_id, story_key, story_title,
                             story_type, story_created, story_resolved)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "JIRA-1", "B-1", "Open Story At Release", "Story",
             _iso(20), _iso(5)),
            (2, "JIRA-2", "DUP-1", "Duplicate Story", "Story",
             _iso(15), _iso(9)),
            (3, "JIRA-4", "NOPR-1", "No PR Story", "Story",
             _iso(12), _iso(8)),
            (4, "JIRA-5", "OPENPR-1", "Open PR On Release", "Story",
             _iso(15), _iso(9)),
            (5, "JIRA-6", "OLDCOMMIT-1", "Old Commit Story", "Story",
             _iso(12), _iso(4)),
            (6, "JIRA-7", "NEG-1", "Negative Lead Story", "Story",
             _iso(10), _iso(4)),
            (7, "JIRA-8", "POSTREL-1", "Story Created After Release",
             "Story", _iso(8), _iso(7)),
        ],
    )

    # DUP-1 belongs to both Release 1 and Release 2 (many-to-many)
    cursor.executemany(
        """
        INSERT INTO releases_stories (story_id, release_id)
        VALUES (?, ?)
        """,
        [
            (1, 1),  # B-1 → Release Recent 1
            (2, 1),  # DUP-1 → Release Recent 1
            (2, 2),  # DUP-1 → Release Recent 2  (multi-release)
            (3, 1),  # NOPR-1 → Release Recent 1
            (4, 1),  # OPENPR-1 → Release Recent 1
            (5, 2),  # OLDCOMMIT-1 → Release Recent 2
            (6, 2),  # NEG-1 → Release Recent 2
            (7, 1),  # POSTREL-1 → Release Recent 1 after release date
        ],
    )

    cursor.executemany(
        """
        INSERT INTO pull_requests (id, pr_title, pr_owner, pr_repository,
                                   pr_number, pr_open, pr_close, commit_count,
                                   earliest_commit_date, latest_commit_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "PR Open On Release", "acme", "repo", "1",
             _iso(12), _iso(10), 3, _iso(15), _iso(11)),
            (2, "PR With Old Commits", "acme", "repo", "2",
             _iso(2), _iso(1), 5, _iso(15), _iso(3)),
            (3, "PR Negative Lead", "acme", "repo", "3",
             _iso(3), _iso(2), 2, _iso(4), _iso(3)),
            (4, "PR Older Multi Story", "acme", "repo", "4",
             _iso(8), _iso(7), 2, _iso(9), _iso(8)),
        ],
    )

    cursor.executemany(
        """
        INSERT INTO stories_pull_requests (story_id, pr_id)
        VALUES (?, ?)
        """,
        [
            (4, 1),
            (1, 2),
            (5, 2),
            (6, 3),
            (1, 4),
            (5, 4),
        ],
    )

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def reports(seeded_db_path) -> OutlierReports:
    """Create OutlierReports over a seeded temporary database."""
    return OutlierReports(seeded_db_path)


def test_report_projects_without_releases(reports):
    """Projects without recent releases should be reported."""
    result = reports.report_projects_without_releases()

    assert not result.empty
    assert {"project_key", "project_title", "project_type"}.issubset(
        result.columns
    )
    project_keys = set(result["project_key"])
    assert "POLD" in project_keys
    assert "PNRL" in project_keys
    assert "PACT" not in project_keys


def test_report_releases_with_open_stories(reports):
    """Stories resolved too late after release should be reported."""
    result = reports.report_releases_with_open_stories()

    assert not result.empty
    assert "story_key" in result.columns
    assert "days_open" in result.columns
    assert "B-1" in set(result["story_key"])


def test_report_releases_modified_after_release_date(reports):
    """Stories created after release should be reported."""
    result = reports.report_releases_modified_after_release_date()

    assert not result.empty
    assert "story_key" in result.columns
    assert "days_after_release" in result.columns
    row = result[result["story_key"] == "POSTREL-1"].iloc[0]
    assert int(row["days_after_release"]) > 0


def test_report_stories_in_multiple_releases(reports):
    """Stories included in more than one release should be reported."""
    result = reports.report_stories_in_multiple_releases()

    assert not result.empty
    assert "story_key" in result.columns
    assert "DUP-1" in set(result["story_key"])


def test_report_releases_with_open_pull_requests(reports):
    """Releases with non-closed PRs at release should be reported."""
    result = reports.report_releases_with_open_pull_requests()

    assert not result.empty
    assert "story_key" in result.columns
    assert "OPENPR-1" in set(result["story_key"])


def test_report_counts_of_stories_without_pull_requests(reports):
    """Summary counts should include stories without pull requests."""
    result = reports.report_counts_of_stories_without_pull_requests()

    assert not result.empty
    assert "stories_without_prs" in result.columns
    active_rows = result[result["project_key"] == "PACT"]
    assert not active_rows.empty
    assert active_rows.iloc[0]["stories_without_prs"] >= 1


def test_report_stories_without_pull_requests(reports):
    """Detailed story rows without PR links should be reported."""
    result = reports.report_stories_without_pull_requests()

    assert not result.empty
    assert "story_key" in result.columns
    assert "NOPR-1" in set(result["story_key"])


def test_report_pull_requests_with_old_commits(reports):
    """PRs with old commits before open date should be reported."""
    result = reports.report_pull_requests_with_old_commits()

    assert not result.empty
    assert "story_key" in result.columns
    assert "days_between" in result.columns
    row = result[result["story_key"] == "OLDCOMMIT-1"].iloc[0]
    assert int(row["days_between"]) > 5


def test_report_pull_requests_in_multiple_stories(reports):
    """PRs linked to multiple distinct stories should be reported."""
    result = reports.report_pull_requests_in_multiple_stories()

    assert not result.empty
    assert {
        "pr_owner",
        "pr_repository",
        "pr_number",
        "pr_title",
        "pr_open",
        "pr_url",
        "story_count",
    }.issubset(result.columns)

    multi_story_prs = result[result["pr_number"] == "2"]
    assert not multi_story_prs.empty
    assert int(multi_story_prs.iloc[0]["story_count"]) >= 2

    single_story_prs = set(result["pr_number"])
    assert "1" not in single_story_prs
    assert "3" not in single_story_prs

    # Tie-break on PR creation date should put newer PRs first.
    assert list(result["pr_number"]) == ["2", "4"]


def test_report_zero_or_negative_lead_times(reports):
    """Zero or negative lead times should be reported."""
    result = reports.report_zero_or_negative_lead_times()

    assert not result.empty
    assert "story_key" in result.columns
    assert "lead_time" in result.columns
    row = result[result["story_key"] == "NEG-1"].iloc[0]
    assert float(row["lead_time"]) <= 0


def test_read_sql_file_raises_for_missing_file(reports):
    """Missing SQL files should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        reports._read_sql_file("missing_query")
