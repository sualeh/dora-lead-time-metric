-- Lookback window: 60 days — a two-month rolling window captures recently
-- closed releases and their associated stories and pull requests.
WITH recent_pull_request_ids AS (
  SELECT DISTINCT
    pull_requests.id AS pr_id
  FROM
    pull_requests
    JOIN stories_pull_requests
      ON pull_requests.id = stories_pull_requests.pr_id
    JOIN stories
      ON stories_pull_requests.story_id = stories.id
    JOIN releases_stories
      ON releases_stories.story_id = stories.id
    JOIN releases
      ON releases_stories.release_id = releases.id
  WHERE
    julianday('now') - julianday(releases.release_date) <= 60
)
SELECT
  pull_requests.pr_owner,
  pull_requests.pr_repository,
  pull_requests.pr_number,
  pull_requests.pr_title,
  pull_requests.pr_open,
  pull_requests.pr_url,
  pull_requests.commit_count,
  pull_requests.changed_files_count,
  CAST(ROUND(
    (SQRT(pull_requests.commit_count) * 3.0) +
    (SQRT(pull_requests.changed_files_count) * 5.0))
    AS INTEGER)
    AS complexity_score
FROM
  pull_requests
  JOIN recent_pull_request_ids
    ON pull_requests.id = recent_pull_request_ids.pr_id
WHERE
  complexity_score  > 29
ORDER BY
  complexity_score DESC
