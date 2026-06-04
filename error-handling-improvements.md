# Error Handling Improvements

## 1. Handling Expired API Keys (401, 403)
**Current State:**
*   GitHub module ignores bad status codes, logs generic messages, and skips.
*   Atlassian module crashes the program entirely via `raise_for_status()`.
**Recommendation:**
*   Introduce an explicit check for `401 Unauthorized` and `403 Forbidden`. If detected, raise an `AuthError` exception identifying which token failed, then gracefully exit the program instead of proceeding with incomplete data.

## 2. Handling Rate Limit Errors (429)
**Current State:**
*   Requests that return `429 Too Many Requests` are treated as generic errors.
**Recommendation:**
*   Detect `429` status codes specifically.
*   Read `Retry-After` or `x-ratelimit-reset` headers where available (especially for GitHub) and log exactly when the user can re-run the collector. Raise a `RateLimitError` to halt execution.

## 3. Other HTTP Error Codes
**Current State:**
*   Some HTTP issues are skipped with `continue`. Others crash the program.
**Recommendation:**
*   For item-specific failures (e.g. `404 Not Found` when pulling details on a single PR), log the error and **continue** to the next item so a single glitch doesn't kill the entire job.
*   For list-based, structural failures (e.g. `500 Server Error` on the main projects endpoint), raise an unrecoverable `ApiError`.

## 4. Preventing Database Corruption and Partial Updates
**Current State:**
*   Database `commit()` calls happen within every `save_*` method loop (e.g., `save_releases`). If the script crashes midway through pulling releases, half the DB tables are populated, requiring manual cleanup or causing duplicate rows on restart.
**Recommendation:**
*   **Transaction Scoping:** Separate the "fetch" loops from the "save" routines, OR remove the automatic `conn.commit()` lines from individual insert methods in `database_processor.py`.
*   Rely on `main.py` to trigger the `commit()` only once the entire logical step (or overall script) has completed successfully without API errors.
