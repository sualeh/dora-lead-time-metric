"""Tests for drop_invalid_story_key_fk migration runner."""

import sqlite3
from dora_lead_time.migrations.drop_invalid_story_key_fk.run_migration import (
    MIGRATION_ID,
    run_migration,
)


def _create_legacy_schema(db_path: str) -> None:
    """Create schema with invalid story_key FK for migration testing.

    Args:
        db_path: SQLite database path.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript(
        """
        PRAGMA foreign_keys = OFF;

        CREATE TABLE stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_key VARCHAR(1024),
            release_id VARCHAR(1024),
            UNIQUE(story_key, release_id)
        );

        CREATE TABLE stories_pull_request_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_key VARCHAR(1024),
            pr_count INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(story_key),
            FOREIGN KEY (story_key) REFERENCES stories (story_key)
        );

        INSERT INTO stories (story_key, release_id)
        VALUES ('ABC-123', 'REL-1');

        INSERT INTO stories_pull_request_counts (story_key, pr_count)
        VALUES ('ABC-123', 2);

        PRAGMA foreign_keys = ON;
        """
    )

    conn.commit()
    conn.close()


def _count_rows(db_path: str, table_name: str) -> int:
    """Count rows in a table.

    Args:
        db_path: SQLite database path.
        table_name: Table name.

    Returns:
        int: Number of rows in the table.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    row_count = cursor.fetchone()[0]
    conn.close()
    return row_count


def test_migration_applies_and_preserves_data(tmp_path):
    """Apply migration once and verify data is preserved."""
    db_path = str(tmp_path / "legacy.db")
    _create_legacy_schema(db_path)

    before_count = _count_rows(db_path, "stories_pull_request_counts")

    applied = run_migration(db_path)

    after_count = _count_rows(db_path, "stories_pull_request_counts")
    assert applied is True
    assert before_count == after_count

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_key_list(stories_pull_request_counts)")
    foreign_keys = cursor.fetchall()
    assert foreign_keys == []

    cursor.execute(
        "SELECT migration_id FROM schema_migrations WHERE migration_id = ?",
        (MIGRATION_ID,),
    )
    recorded = cursor.fetchone()
    conn.close()

    assert recorded is not None


def test_migration_second_run_is_noop(tmp_path):
    """Re-running migration should be a no-op without data loss."""
    db_path = str(tmp_path / "legacy.db")
    _create_legacy_schema(db_path)

    first_applied = run_migration(db_path)
    count_after_first = _count_rows(db_path, "stories_pull_request_counts")

    second_applied = run_migration(db_path)
    count_after_second = _count_rows(db_path, "stories_pull_request_counts")

    assert first_applied is True
    assert second_applied is False
    assert count_after_first == count_after_second
