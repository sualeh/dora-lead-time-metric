"""Test the transaction context manager in database_processor."""

import sqlite3
import pytest
from dora_lead_time.database_processor import (
    DatabaseProcessor,
    DatabaseOperationError,
)


def test_transaction_context_manager_executes_and_commits(tmp_path):
    """Test that _transaction context manager executes SQL and commits."""
    db_path = tmp_path / "test_transaction.db"
    processor = DatabaseProcessor(str(db_path))
    processor.create_schema()

    with processor._transaction("test insert") as cursor:
        cursor.execute(
            """
            INSERT INTO projects (
                project_internal_id, project_key, project_title, project_type
            )
            VALUES (?, ?, ?, ?)
            """,
            ("P-1", "TEST", "Test Project", "software"),
        )

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM projects WHERE project_key = ?", ("TEST",))
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 1


def test_transaction_context_manager_rolls_back_on_error(tmp_path):
    """Test that _transaction context manager rolls back on database error."""
    db_path = tmp_path / "test_rollback.db"
    processor = DatabaseProcessor(str(db_path))
    processor.create_schema()

    with pytest.raises(DatabaseOperationError):
        with processor._transaction("test bad sql") as cursor:
            cursor.execute("INVALID SQL STATEMENT HERE")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM projects")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 0


def test_transaction_context_manager_with_check_exists_false(tmp_path):
    """Test that _transaction respects check_exists=False parameter."""
    db_path = tmp_path / "test_new.db"

    processor = DatabaseProcessor(str(db_path))

    with processor._transaction("create schema", check_exists=False) as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS test_table (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
            """
        )

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'"
    )
    result = cursor.fetchone()
    conn.close()

    assert result is not None
    assert result[0] == "test_table"
