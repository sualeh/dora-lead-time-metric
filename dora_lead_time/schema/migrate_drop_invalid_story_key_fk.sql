-- Repair invalid FK on stories_pull_request_counts while preserving data.
--
-- Root cause:
-- stories_pull_request_counts uses UNIQUE(story_key), but stories uses
-- UNIQUE(story_key, release_id). Therefore, a foreign key from
-- stories_pull_request_counts(story_key) to stories(story_key) is invalid
-- in SQLite and can raise "foreign key mismatch".

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

ALTER TABLE stories_pull_request_counts
RENAME TO stories_pull_request_counts_old;

CREATE TABLE stories_pull_request_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_key VARCHAR(1024),
    pr_count INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(story_key)
);

INSERT INTO stories_pull_request_counts (
    id,
    story_key,
    pr_count,
    created_at
)
SELECT
    id,
    story_key,
    pr_count,
    created_at
FROM stories_pull_request_counts_old;

DROP TABLE stories_pull_request_counts_old;

COMMIT;
PRAGMA foreign_keys = ON;

PRAGMA foreign_key_check;
