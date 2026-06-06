-- database: ../../releases.2024-07.2025-03.db
-- Lookback window: 60 days — a two-month rolling window captures recently
-- closed releases and their associated stories and pull requests.
SELECT DISTINCT
  stories.story_key,
  stories.story_title,
  pull_requests.pr_title,
  releases.release_title,
  CAST(julianday(pull_requests.pr_close) - julianday(releases.release_date)
  -- days_open uses an exclusive convention: 0 means the PR closed on the
  -- release day itself; NULL means the PR is still open (no close date).
  AS INTEGER)
    AS days_open,
  releases.release_date,
  date(julianday(pull_requests.pr_close))
    AS pr_close
FROM
  stories
  JOIN releases
    ON stories.release_id = releases.id
  JOIN stories_pull_requests
    ON stories_pull_requests.story_id = stories.id
  JOIN pull_requests
    ON stories_pull_requests.pr_id = pull_requests.id
WHERE
  -- Flag PRs that closed on the release day, after it, or were never closed.
  -- A PR must close at least 1 day before the release to be considered clean.
  (
    julianday(pull_requests.pr_close) >= julianday(releases.release_date)
    OR pull_requests.pr_close IS NULL
  )
  AND julianday('now') - julianday(releases.release_date) <= 60
ORDER BY
  releases.release_date,
  pull_requests.pr_owner,
  pull_requests.pr_repository,
  pull_requests.pr_number
