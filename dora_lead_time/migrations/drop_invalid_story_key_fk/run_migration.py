"""Execute migration to drop invalid story_key foreign key."""

import argparse
import logging
import os
import pathlib
import sqlite3
from dotenv import load_dotenv
from dora_lead_time.database_processor import (
    DatabaseOperationError,
    make_sqlite_connection,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s `%(funcName)s` %(levelname)s:\n  %(message)s"
)
logger = logging.getLogger(__name__)

MIGRATION_ID = "20260607_drop_invalid_story_key_fk"
MIGRATION_DESCRIPTION = (
    "Drop invalid stories_pull_request_counts.story_key foreign key"
)


def _ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    """Ensure migration bookkeeping table exists.

    Args:
        conn: Active SQLite connection.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id VARCHAR(255) PRIMARY KEY,
            migration_description VARCHAR(1024),
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _is_migration_recorded(conn: sqlite3.Connection) -> bool:
    """Check whether this migration has already been recorded.

    Args:
        conn: Active SQLite connection.

    Returns:
        bool: True if this migration was already applied.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM schema_migrations
        WHERE migration_id = ?
        LIMIT 1
        """,
        (MIGRATION_ID,),
    )
    return cursor.fetchone() is not None


def _has_invalid_story_key_fk(conn: sqlite3.Connection) -> bool:
    """Check whether invalid story_key FK exists on counts table.

    Args:
        conn: Active SQLite connection.

    Returns:
        bool: True if the invalid FK is present and migration is needed.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'stories_pull_request_counts'
        """
    )
    table_exists = cursor.fetchone() is not None
    if not table_exists:
        raise DatabaseOperationError(
            "Table stories_pull_request_counts does not exist"
        )

    cursor.execute("PRAGMA foreign_key_list(stories_pull_request_counts)")
    foreign_keys = cursor.fetchall()

    for foreign_key in foreign_keys:
        # PRAGMA foreign_key_list columns include:
        # (id, seq, table, from, to, on_update, on_delete, match)
        target_table = foreign_key[2]
        source_column = foreign_key[3]
        target_column = foreign_key[4]
        if (
            target_table == "stories"
            and source_column == "story_key"
            and target_column == "story_key"
        ):
            return True

    return False


def _record_migration(conn: sqlite3.Connection) -> None:
    """Record successful migration run.

    Args:
        conn: Active SQLite connection.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (
            migration_id,
            migration_description
        )
        VALUES (?, ?)
        """,
        (MIGRATION_ID, MIGRATION_DESCRIPTION),
    )


def _sql_script_path() -> pathlib.Path:
    """Return migration SQL file path.

    Returns:
        pathlib.Path: SQL script path.
    """
    return pathlib.Path(__file__).with_name(
        "migrate_drop_invalid_story_key_fk.sql"
    )


def run_migration(sqlite_path: str) -> bool:
    """Run migration once, preserving data and skipping repeated runs.

    Args:
        sqlite_path: Path to SQLite database file.

    Returns:
        bool: True if migration SQL was executed; False when skipped.

    Raises:
        DatabaseOperationError: If migration cannot be completed.
    """
    conn = None

    try:
        conn = make_sqlite_connection(sqlite_path)
        _ensure_schema_migrations_table(conn)

        if _is_migration_recorded(conn):
            logger.info("Migration already recorded: %s", MIGRATION_ID)
            return False

        if not _has_invalid_story_key_fk(conn):
            logger.info(
                "Database already in desired state for migration: %s",
                MIGRATION_ID,
            )
            _record_migration(conn)
            conn.commit()
            return False

        script_path = _sql_script_path()
        if not script_path.exists():
            raise FileNotFoundError(f"SQL file not found: {script_path}")

        with open(script_path, "r", encoding="utf-8") as sql_file:
            sql_script = sql_file.read()

        conn.executescript(sql_script)

        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_key_check")
        fk_violations = cursor.fetchall()
        if fk_violations:
            raise DatabaseOperationError(
                "Foreign key violations found after migration"
            )

        _record_migration(conn)
        conn.commit()
        logger.info("Migration applied: %s", MIGRATION_ID)
        return True
    except (
        sqlite3.OperationalError,
        sqlite3.DatabaseError,
        FileNotFoundError,
    ) as exc:
        if conn:
            conn.rollback()
        raise DatabaseOperationError(
            "Could not apply drop-invalid-story-key-fk migration"
        ) from exc
    finally:
        if conn:
            conn.close()


def main() -> None:
    """Parse CLI arguments and execute the migration."""
    load_dotenv(dotenv_path=".env.params")
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Apply migration: drop invalid story_key FK"
    )
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("SQLITE_PATH"),
        help="Path to SQLite database. Defaults to SQLITE_PATH env var.",
    )
    args = parser.parse_args()

    if not args.sqlite_path:
        parser.error("--sqlite-path is required when SQLITE_PATH is not set")

    try:
        applied = run_migration(args.sqlite_path)
        if applied:
            logger.info("Migration completed successfully")
        else:
            logger.info("Migration not needed")
    except DatabaseOperationError as exc:
        logger.error("Migration failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
