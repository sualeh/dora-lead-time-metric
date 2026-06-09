"""Unit tests for main module report ordering."""

from datetime import date, datetime as real_datetime

import pandas as pd

from dora_lead_time import main


class _FakeDateTime:
    """Deterministic datetime provider for test output paths."""

    @classmethod
    def now(cls):
        """Return a fixed datetime for repeatable directory names."""
        return real_datetime(2026, 1, 2, 3, 4, 5)


def test_save_outlier_reports_uses_requested_order(tmp_path, monkeypatch):
    """Outlier report generation should follow the configured sequence."""
    call_order = []

    class FakeOutlierReports:
        """Test double that records report method invocation order."""

        def __init__(self, sqlite_path):
            del sqlite_path

        def _df(self, report_name):
            call_order.append(report_name)
            return pd.DataFrame({"value": [1]})

        def report_projects_without_releases(self):
            return self._df("projects_without_releases")

        def report_zero_or_negative_lead_times(self):
            return self._df("zero_or_negative_lead_times")

        def report_releases_with_open_pull_requests(self):
            return self._df("releases_with_open_pull_requests")

        def report_releases_with_open_stories(self):
            return self._df("releases_with_open_stories")

        def report_pull_requests_with_old_commits(self):
            return self._df("pull_requests_with_old_commits")

        def report_stories_in_multiple_releases(self):
            return self._df("stories_in_multiple_releases")

        def report_pull_requests_in_multiple_stories(self):
            return self._df("pull_requests_in_multiple_stories")

        def report_stories_without_pull_requests(self):
            return self._df("stories_without_pull_requests")

        def report_counts_of_stories_without_pull_requests(self):
            return self._df("counts_of_stories_without_pull_requests")

    monkeypatch.setattr(main, "OutlierReports", FakeOutlierReports)
    monkeypatch.setattr(main, "datetime", _FakeDateTime)
    monkeypatch.chdir(tmp_path)

    config = main.LeadTimeConfiguration(
        sqlite_path="unused.db",
        build_database=False,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        github_org_tokens_map={},
    )

    reports_dir = main.save_outlier_reports(config)

    expected_order = [
        "projects_without_releases",
        "zero_or_negative_lead_times",
        "releases_with_open_pull_requests",
        "releases_with_open_stories",
        "pull_requests_with_old_commits",
        "stories_in_multiple_releases",
        "pull_requests_in_multiple_stories",
        "stories_without_pull_requests",
        "counts_of_stories_without_pull_requests",
    ]

    assert call_order == expected_order

    for report_name in expected_order:
        report_path = reports_dir / f"{report_name}.csv"
        assert report_path.exists()
