"""Unit tests for the DatabaseProcessor class."""

import os
import pytest
import sqlite3
from datetime import date, datetime
from dora_lead_time.database_processor import DatabaseProcessor
from dora_lead_time.models import Project, PullRequestIdentifier, PullRequest


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
    assert "pull_requests" in tables
    assert "stories_pull_requests" in tables

    # Check if view exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='view';")
    views = [row[0] for row in cursor.fetchall()]

    assert "lead_times" in views

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
