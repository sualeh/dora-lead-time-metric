# Design Notes

## Idempotent, Incremental, and Resumable Database Builds

### Overview

The database build is designed so that every run is safe to abort and
re-run. The database can be built up incrementally across multiple
partial runs without corrupting data or creating duplicate rows. Each
committed batch of work is immediately durable: a run that is aborted
picks up exactly where it left off on the next invocation.

This property is valuable because the data collection involves many
slow, rate-limited API calls. Progress must not be lost on interruption.

---

### Mechanism 1: `INSERT OR IGNORE` + `UNIQUE` constraints

Every write to a permanent table uses `INSERT OR IGNORE`, backed by a
`UNIQUE` constraint on the record's natural key:

| Table | Natural unique key |
|---|---|
| `projects` | `project_internal_id` |
| `releases` | `release_internal_id` |
| `stories` | `(story_key, release_internal_id)` |
| `pull_requests` | `(pr_owner, pr_repository, pr_number)` |
| `stories_pull_requests` | `(story_id, pr_id)` |

`INSERT OR IGNORE` silently skips any row whose natural key already
exists. Re-running any `save_*` method with the same API data is always
safe — rows are written at most once.

---

### Mechanism 2: "Not-yet-done" sentinel queries

Each step in `main.py` queries the database for *only the work that
has not yet been completed*. This is what makes the build incremental
and resumable.

**`retrieve_releases_without_stories()`**
Uses a `LEFT JOIN` on the `stories` table. A release is returned only
if it has no story row yet.

**`retrieve_stories_without_pull_requests()`**
Uses a `LEFT OUTER JOIN` against the `stories_pull_request_counts`
table. A story is included in results only if it has no row in that
table — meaning its PR lookup has never been attempted. Crucially, when
`save_story_pull_requests()` runs it writes a row for every story,
including ones where `pr_count = 0` (the story has no linked PRs).
This correctly records "we looked and found nothing", so the API is
never called again for that story on a subsequent run.

**`retrieve_pull_requests_without_details()`**
Uses `pr_title IS NULL` as the sentinel. A pull request is inserted
into the `pull_requests` table when its identifier is first seen
(owner, repository, number). Its detail columns (`pr_title`, dates,
commit counts) are all `NULL` at that point. After
`save_pull_request_details()` runs, `pr_title` is populated and the
row is excluded from future queries.

---

### Mechanism 3: Staged two-phase writes

`save_releases`, `save_stories`, and `save_story_pull_requests` use a
temporary staging table to keep each write operation atomic:

```
1. CREATE TABLE IF NOT EXISTS stage_*  (temp table)
2. INSERT  raw API data → stage_*
3. INSERT OR IGNORE  permanent table ← SELECT … FROM stage_*
                                       (resolves foreign-key IDs)
4. DROP TABLE IF EXISTS stage_*
5. conn.commit()
```

The staging table decouples the API data shape (which uses natural
string keys such as `project_key` and `release_internal_id`) from the
permanent table shape (which uses integer `id` foreign keys). Step 3
performs the join and key resolution in a single SQL statement. If
anything fails before step 5, the transaction is rolled back and the
permanent table is unchanged.

---

### Mechanism 4: Per-batch commits with limits

Steps 5 and 6 in `main.py` use `while True` loops that retrieve and
process 100 items per iteration, committing after each batch:

```python
while True:
    items = db.retrieve_items_without_details(limit=100)
    if not items:
        break
    details = api_client.get_details(items)
    db.save_details(details)   # commits inside
```

Each committed batch is immediately durable. A crash after any commit
leaves all prior batches intact in the database; the next run resumes
from the first uncommitted item.

---

### API error handling and the build loop

`api_get()` in `api_client.py` applies three error checks after every
HTTP call, in order:

1. `raise_if_auth_error` — raises `AuthError` on 401/403
2. `raise_if_rate_limit_error` — raises `RateLimitError` on 429,
   logging when the rate limit resets
3. `raise_if_api_error` (structural calls only) — raises `ApiError`
   on any other 4xx/5xx

`AuthError`, `RateLimitError`, and `ApiError` are all caught at the top
level in `main.py`, which logs a clear message and exits. Because every
batch has already been committed before the failing API call is made,
no committed data is lost.

Per-item failures (a single PR or Jira story that returns a non-200)
are logged as warnings and skipped; they do not stop the run.

---
