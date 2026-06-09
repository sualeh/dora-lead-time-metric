"""Unit tests for the DatabaseProcessor class."""

import os
import pytest
import sqlite3
from datetime import date, datetime
from dora_lead_time.database_processor import (
    DatabaseOperationError,
    DatabaseProcessor,
    PULL_REQUEST_BATCH_SIZE,
    make_sqlite_connection,
)
from dora_lead_time.models import (
    Project,
    PullRequestIdentifier,
    PullRequest,
    Story,
    StoryInRelease,
)


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database path for testing."""
    db_file = tmp_path / "test.db"
    return str(db_file)


@pytest.fixture
def db_processor(temp_db_path, monkeypatch):
    """Create a DatabaseProcessor instance with a temp database."""
    monkeypatch.setenv("SQLITE_PATH", temp_db_path)
    processor = DatabaseProcessor(sqlite_path=temp_db_path)
    return processor


def test_create_schema(db_processor):
    """Test schema creation."""
    db_processor.create_schema()

    # Verify tables were created
    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()

    # Check if tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    assert "projects" in tables
    assert "releases" in tables
    assert "stories" in tables
    assert "releases_stories" in tables
    assert "pull_requests" in tables
    assert "stories_pull_requests" in tables
    assert "stories_pull_request_counts" in tables

    # Check if view exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='view';")
    views = [row[0] for row in cursor.fetchall()]

    assert "lead_times" in views

    # New database files should use typed date declarations.
    cursor.execute("PRAGMA table_info(releases);")
    release_columns = {row[1]: row[2].upper() for row in cursor.fetchall()}
    assert release_columns["release_date"] == "DATE"

    cursor.execute("PRAGMA table_info(stories);")
    story_columns = {row[1]: row[2].upper() for row in cursor.fetchall()}
    assert story_columns["story_internal_id"] == "VARCHAR(1024)"
    assert story_columns["story_created"] == "DATETIME"
    assert story_columns["story_resolved"] == "DATETIME"
    assert "release_id" not in story_columns

    cursor.execute("PRAGMA table_info(stories_pull_request_counts);")
    spr_rows = cursor.fetchall()
    spr_columns = {row[1]: row[2].upper() for row in spr_rows}
    spr_pk_columns = {row[1] for row in spr_rows if row[5] == 1}
    assert "story_id" in spr_columns
    assert "story_key" not in spr_columns
    assert "id" not in spr_columns
    assert spr_pk_columns == {"story_id"}

    cursor.execute("PRAGMA table_info(pull_requests);")
    pr_columns = {row[1]: row[2].upper() for row in cursor.fetchall()}
    assert pr_columns["pr_open"] == "DATE"
    assert pr_columns["pr_close"] == "DATE"
    assert pr_columns["earliest_commit_date"] == "DATE"
    assert pr_columns["latest_commit_date"] == "DATE"

    conn.close()


def test_save_projects(db_processor):
    """Test saving projects to database."""
    db_processor.create_schema()

    # Create test projects
    projects = [
        Project(None, "P1", "PROJ1", "Project 1", "painter"),
        Project(None, "P2", "PROJ2", "Project 2", "millworks"),
    ]

    # Save projects
    db_processor.save_projects(projects)

    # Verify projects were saved
    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            project_key,
            project_title,
            project_type
        FROM
            projects
        """)
    saved_projects = cursor.fetchall()
    conn.close()

    assert len(saved_projects) == 2
    assert ("PROJ1", "Project 1", "painter") in saved_projects
    assert ("PROJ2", "Project 2", "millworks") in saved_projects


def test_update_project_types(db_processor):
    """Test updating project types."""
    db_processor.create_schema()

    # Create test projects
    projects = [
        Project(None, "P1", "PROJ1", "Project 1", "software"),
        Project(None, "P2", "PROJ2", "Project 2", "software"),
        Project(None, "P3", "PROJ3", "Project 3", "software"),
    ]

    # Save projects
    db_processor.save_projects(projects)

    # Update project types
    db_processor.update_project_types(["PROJ1", "PROJ2"], "painter")

    # Verify updates
    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute("SELECT project_key, project_type FROM projects;")
    saved_projects = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()

    assert saved_projects["PROJ1"] == "painter"
    assert saved_projects["PROJ2"] == "painter"
    assert saved_projects["PROJ3"] == "software"


def test_retrieve_all_projects(db_processor):
    """Test retrieving all projects."""
    db_processor.create_schema()

    # Create test projects
    projects = [
        Project(None, "P1", "PROJ1", "Project 1", "painter"),
        Project(None, "P2", "PROJ2", "Project 2", "millworks"),
    ]

    # Save projects
    db_processor.save_projects(projects)

    # Retrieve projects
    retrieved_projects = db_processor.retrieve_all_projects()

    # Verify retrieved projects
    assert len(retrieved_projects) == 2

    project_keys = [p.project_key for p in retrieved_projects]
    assert "PROJ1" in project_keys
    assert "PROJ2" in project_keys

    project_types = {p.project_key: p.project_type for p in retrieved_projects}
    assert project_types["PROJ1"] == "painter"
    assert project_types["PROJ2"] == "millworks"


def test_save_and_retrieve_pull_request_details(db_processor):
    """Test saving and retrieving pull request details."""
    db_processor.create_schema()

    # Create test PR details
    pr = PullRequest(
        id=1,
        pr_title="Test PR",
        open_date=date(2023, 1, 1),
        close_date=date(2023, 1, 2),
        commit_count=3,
        earliest_commit_date=date(2022, 12, 30),
        latest_commit_date=date(2023, 1, 1),
        owner="testorg",
        repo="testrepo",
        pr_number="123",
    )

    # Create the PR record first
    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO pull_requests
        (id, pr_owner, pr_repository, pr_number)
        VALUES (?, ?, ?, ?)
        """,
        (1, "testorg", "testrepo", "123"),
    )
    conn.commit()
    conn.close()

    # Save PR details
    db_processor.save_pull_request_details([pr])

    # Retrieve and verify
    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            pr_title,
            commit_count
        FROM
            pull_requests
        WHERE
            id=1
        """)
    result = cursor.fetchone()
    conn.close()

    assert result[0] == "Test PR"
    assert result[1] == 3


def test_save_projects_raises_on_missing_schema(db_processor):
    """Test that save_projects raises DatabaseOperationError without schema."""
    conn = sqlite3.connect(db_processor.sqlite_path)
    conn.close()

    projects = [Project(None, "P1", "PROJ1", "Project 1", "software")]
    with pytest.raises(DatabaseOperationError):
        db_processor.save_projects(projects)


def test_retrieve_all_projects_raises_on_missing_table(db_processor):
    """Test that retrieve_all_projects raises DatabaseOperationError without schema."""
    conn = sqlite3.connect(db_processor.sqlite_path)
    conn.close()

    with pytest.raises(DatabaseOperationError):
        db_processor.retrieve_all_projects()


def test_save_releases_raises_on_missing_schema(db_processor):
    """Test that save_releases raises DatabaseOperationError without schema."""
    conn = sqlite3.connect(db_processor.sqlite_path)
    conn.close()

    releases = [(None, "REL-1", "Release 1", "desc", "2024-01-01", "PROJ1")]
    with pytest.raises(DatabaseOperationError):
        db_processor.save_releases(releases)


def test_retrieve_stories_without_pull_requests_uses_default_limit(
    db_processor,
):
    """Test default limit for story keys without pull requests."""
    db_processor.create_schema()

    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    stories = [
        (f"STORY-{idx}", f"Title {idx}")
        for idx in range(PULL_REQUEST_BATCH_SIZE + 10)
    ]
    cursor.executemany(
        """
        INSERT INTO stories (story_key, story_title)
        VALUES (?, ?)
        """,
        stories,
    )
    conn.commit()
    conn.close()

    story_rows = db_processor.retrieve_stories_without_pull_requests()

    assert len(story_rows) == PULL_REQUEST_BATCH_SIZE
    assert all(len(row) == 2 for row in story_rows)


def test_save_stories_persists_story_internal_id(db_processor):
    """Stories should persist story_internal_id during save."""
    db_processor.create_schema()

    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO projects (
            project_internal_id,
            project_key,
            project_title,
            project_type
        )
        VALUES (?, ?, ?, ?)
        """,
        ("P1", "TEST", "Test Project", "software"),
    )
    cursor.execute(
        """
        INSERT INTO releases (
            release_internal_id,
            release_title,
            release_description,
            release_date,
            project_id
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        ("10000", "Release 1", "", "2024-01-01", 1),
    )
    conn.commit()
    conn.close()

    stories = [
        StoryInRelease(
            story_internal_id="730307",
            story_key="TEST-1",
            story_title="First Story",
            story_type="Story",
            story_created=datetime(2024, 1, 1, 10, 0, 0),
            story_resolved=datetime(2024, 1, 2, 10, 0, 0),
            release_internal_id="10000",
        )
    ]
    db_processor.save_stories(stories)

    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT story_internal_id, story_key
        FROM stories
        """
    )
    saved_stories = cursor.fetchall()
    conn.close()

    assert saved_stories == [("730307", "TEST-1")]

    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT releases_stories.release_id, stories.story_key
        FROM releases_stories
        JOIN stories ON releases_stories.story_id = stories.id
        """
    )
    links = cursor.fetchall()
    conn.close()

    assert len(links) == 1
    assert links[0][1] == "TEST-1"


def test_save_stories_links_one_story_to_multiple_releases(db_processor):
    """A story appearing in two releases should produce two releases_stories
    rows but only one stories row."""
    db_processor.create_schema()

    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO projects (project_internal_id, project_key,
                              project_title, project_type)
        VALUES (?, ?, ?, ?)
        """,
        ("P1", "TEST", "Test Project", "software"),
    )
    cursor.executemany(
        """
        INSERT INTO releases (release_internal_id, release_title,
                              release_description, release_date, project_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("20000", "Release A", "", "2024-01-01", 1),
            ("20001", "Release B", "", "2024-02-01", 1),
        ],
    )
    conn.commit()
    conn.close()

    stories = [
        StoryInRelease(
            story_internal_id="999",
            story_key="MULTI-1",
            story_title="Multi-release Story",
            story_type="Story",
            story_created=datetime(2024, 1, 1, 0, 0, 0),
            story_resolved=datetime(2024, 1, 10, 0, 0, 0),
            release_internal_id="20000",
        ),
        StoryInRelease(
            story_internal_id="999",
            story_key="MULTI-1",
            story_title="Multi-release Story",
            story_type="Story",
            story_created=datetime(2024, 1, 1, 0, 0, 0),
            story_resolved=datetime(2024, 1, 10, 0, 0, 0),
            release_internal_id="20001",
        ),
    ]
    db_processor.save_stories(stories)

    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM stories WHERE story_key = 'MULTI-1'")
    story_count = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*) FROM releases_stories
        JOIN stories ON releases_stories.story_id = stories.id
        WHERE stories.story_key = 'MULTI-1'
        """
    )
    link_count = cursor.fetchone()[0]
    conn.close()

    assert story_count == 1, "Only one canonical story row should exist"
    assert link_count == 2, "Story should be linked to both releases"


def test_save_stories_links_by_story_internal_id(db_processor):
    """Story-release linking should use stable story_internal_id."""
    db_processor.create_schema()

    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO projects (project_internal_id, project_key,
                              project_title, project_type)
        VALUES (?, ?, ?, ?)
        """,
        ("P1", "TEST", "Test Project", "software"),
    )
    cursor.executemany(
        """
        INSERT INTO releases (release_internal_id, release_title,
                              release_description, release_date, project_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("30000", "Release A", "", "2024-01-01", 1),
            ("30001", "Release B", "", "2024-02-01", 1),
        ],
    )
    conn.commit()
    conn.close()

    stories = [
        StoryInRelease(
            story_internal_id="1001",
            story_key="RENAMED-OLD",
            story_title="Renamed Story",
            story_type="Story",
            story_created=datetime(2024, 1, 1, 0, 0, 0),
            story_resolved=datetime(2024, 1, 10, 0, 0, 0),
            release_internal_id="30000",
        ),
        StoryInRelease(
            story_internal_id="1001",
            story_key="RENAMED-NEW",
            story_title="Renamed Story",
            story_type="Story",
            story_created=datetime(2024, 1, 1, 0, 0, 0),
            story_resolved=datetime(2024, 1, 10, 0, 0, 0),
            release_internal_id="30001",
        ),
    ]

    db_processor.save_stories(stories)

    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM stories
        WHERE story_internal_id = '1001'
        """
    )
    story_count = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM releases_stories
        JOIN stories ON releases_stories.story_id = stories.id
        WHERE stories.story_internal_id = '1001'
        """
    )
    link_count = cursor.fetchone()[0]
    conn.close()

    assert story_count == 1
    assert link_count == 2


def test_retrieve_pull_requests_without_details_honors_explicit_limit(
    db_processor,
):
    """Test explicit limit for pull requests without details."""
    db_processor.create_schema()

    conn = sqlite3.connect(db_processor.sqlite_path)
    cursor = conn.cursor()
    pull_requests = [
        (f"owner-{idx}", f"repo-{idx}", str(idx))
        for idx in range(5)
    ]
    cursor.executemany(
        """
        INSERT INTO pull_requests (pr_owner, pr_repository, pr_number)
        VALUES (?, ?, ?)
        """,
        pull_requests,
    )
    conn.commit()
    conn.close()

    pending_pull_requests = db_processor.retrieve_pull_requests_without_details(
        limit=2,
    )

    assert len(pending_pull_requests) == 2
    assert all(
        isinstance(pull_request, PullRequestIdentifier)
        for pull_request in pending_pull_requests
    )


def test_connection_converts_typed_date_columns(temp_db_path):
    """Typed DATE and DATETIME declarations should use converters."""
    conn = make_sqlite_connection(temp_db_path, check_exists=False)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE typed_dates (
            release_date DATE,
            story_created DATETIME
        )
        """
    )
    cursor.execute(
        """
        INSERT INTO typed_dates (release_date, story_created)
        VALUES (?, ?)
        """,
        (date(2024, 1, 1), datetime(2024, 1, 1, 12, 30, 45)),
    )
    conn.commit()

    cursor.execute(
        """
        SELECT release_date, story_created
        FROM typed_dates
        """
    )
    release_date, story_created = cursor.fetchone()
    conn.close()

    assert isinstance(release_date, date)
    assert isinstance(story_created, datetime)
    assert release_date == date(2024, 1, 1)
    assert story_created == datetime(2024, 1, 1, 12, 30, 45)


def test_connection_keeps_legacy_text_date_columns_as_strings(temp_db_path):
    """Legacy VARCHAR/TEXT declarations should still read as strings."""
    conn = make_sqlite_connection(temp_db_path, check_exists=False)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE legacy_dates (
            release_date VARCHAR(1024),
            story_created TEXT
        )
        """
    )
    cursor.execute(
        """
        INSERT INTO legacy_dates (release_date, story_created)
        VALUES (?, ?)
        """,
        ("2024-01-01", "2024-01-01T12:30:45"),
    )
    conn.commit()

    cursor.execute(
        """
        SELECT release_date, story_created
        FROM legacy_dates
        """
    )
    release_date, story_created = cursor.fetchone()
    conn.close()

    assert isinstance(release_date, str)
    assert isinstance(story_created, str)
    assert release_date == "2024-01-01"
    assert story_created == "2024-01-01T12:30:45"
