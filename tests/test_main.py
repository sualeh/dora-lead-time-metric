"""Unit tests for main module report ordering."""

from datetime import date, datetime as real_datetime
from types import SimpleNamespace

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

        def report_releases_modified_after_release_date(self):
            return self._df("releases_modified_after_release_date")

        def report_releases_with_shared_stories(self):
            return self._df("releases_with_shared_stories")

        def report_pull_requests_with_old_commits(self):
            return self._df("pull_requests_with_old_commits")

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
        "releases_modified_after_release_date",
        "releases_with_shared_stories",
        "pull_requests_with_old_commits",
        "pull_requests_in_multiple_stories",
        "stories_without_pull_requests",
        "counts_of_stories_without_pull_requests",
    ]

    assert call_order == expected_order

    for report_name in expected_order:
        report_path = reports_dir / f"{report_name}.csv"
        assert report_path.exists()


def test_create_releases_database_saves_stories_per_release(monkeypatch):
    """Stories should be persisted immediately after each release fetch."""
    save_stories_batch_sizes = []

    class FakeAtlassianRequests:
        """Test double for AtlassianRequests with batched stories."""

        def get_projects(self):
            return []

        def get_releases(self, start_date, end_date, projects):
            del start_date, end_date, projects
            return [
                SimpleNamespace(
                    release_internal_id="R1",
                    release_title="Release One",
                ),
                SimpleNamespace(
                    release_internal_id="R2",
                    release_title="Release Two",
                ),
            ]

        def get_stories(self, releases):
            assert len(releases) == 1
            if releases[0] == "R1":
                return [("story", "rel")] * 100
            return [("story", "rel")] * 10

        def get_story_pull_requests(self, story_records):
            del story_records
            return {}

    class FakeGitHubRequests:
        """Test double for GitHubRequests."""

        def __init__(self, tokens):
            del tokens

        def get_pull_request_details(self, pull_requests):
            del pull_requests
            return []

    class FakeDatabaseProcessor:
        """Test double for DatabaseProcessor."""

        def __init__(self, sqlite_path):
            del sqlite_path

        def create_schema(self):
            return None

        def print_summary(self):
            return None

        def save_projects(self, projects):
            del projects

        def save_releases(self, releases):
            del releases

        def retrieve_releases_without_stories(self):
            return ["R1", "R2"]

        def save_stories(self, stories):
            save_stories_batch_sizes.append(len(stories))

        def retrieve_stories_without_pull_requests(self, limit):
            del limit
            return []

        def save_story_pull_requests(self, stories_pull_requests_map):
            del stories_pull_requests_map

        def retrieve_pull_requests_without_details(self, limit):
            del limit
            return []

        def save_pull_request_details(self, pr_details):
            del pr_details

    monkeypatch.setattr(main, "AtlassianRequests", FakeAtlassianRequests)
    monkeypatch.setattr(main, "GitHubRequests", FakeGitHubRequests)
    monkeypatch.setattr(main, "DatabaseProcessor", FakeDatabaseProcessor)

    config = main.LeadTimeConfiguration(
        sqlite_path="unused.db",
        build_database=True,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        github_org_tokens_map={},
    )

    main.create_releases_database(config)

    assert save_stories_batch_sizes == [100, 10]
