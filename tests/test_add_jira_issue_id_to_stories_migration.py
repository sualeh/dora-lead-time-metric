"""Tests for add_jira_issue_id_to_stories migration runner."""

import sqlite3
from dora_lead_time.migrations.add_jira_issue_id_to_stories.run_migration import (
    MIGRATION_ID,
    run_migration,
)


def _create_legacy_schema(db_path: str) -> None:
    """Create schema without jira_issue_id for migration testing.

    Args:
        db_path: SQLite database path.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript(
        """
        CREATE TABLE stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_key VARCHAR(1024),
            story_title VARCHAR(1024),
            story_type VARCHAR(1024),
            story_created DATETIME,
            story_resolved DATETIME,
            release_id VARCHAR(1024),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(story_key, release_id)
        );

        INSERT INTO stories (
            story_key,
            story_title,
            story_type,
            story_created,
            story_resolved,
            release_id
        )
        VALUES (
            'ABC-123',
            'First Story',
            'Story',
            '2024-01-01T10:00:00',
            '2024-01-02T10:00:00',
            '10000'
        );
        """
    )

    conn.commit()
    conn.close()


def _column_names(db_path: str, table_name: str) -> list[str]:
    """Return table column names.

    Args:
        db_path: SQLite database path.
        table_name: Table name.

    Returns:
        list[str]: Table column names.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    return columns


def test_migration_adds_column_and_preserves_data(tmp_path):
    """Apply migration and verify jira_issue_id column + data retention."""
    db_path = str(tmp_path / "legacy.db")
    _create_legacy_schema(db_path)

    applied = run_migration(db_path)

    assert applied is True
    assert "jira_issue_id" in _column_names(db_path, "stories")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT story_key, story_title FROM stories")
    rows = cursor.fetchall()
    cursor.execute(
        "SELECT migration_id FROM schema_migrations WHERE migration_id = ?",
        (MIGRATION_ID,),
    )
    recorded = cursor.fetchone()
    conn.close()

    assert rows == [("ABC-123", "First Story")]
    assert recorded is not None


def test_migration_second_run_is_noop(tmp_path):
    """Re-running migration should be a no-op."""
    db_path = str(tmp_path / "legacy.db")
    _create_legacy_schema(db_path)

    first_applied = run_migration(db_path)
    second_applied = run_migration(db_path)

    assert first_applied is True
    assert second_applied is False
