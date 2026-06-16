-- database: ../../releases.2025-26.db
-- Lookback window: 60 days — a two-month rolling window captures recently
-- closed releases and their associated stories and pull requests.
SELECT
  stories.story_key,
  stories.story_title,
  pull_requests.pr_title,
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
  JOIN stories_pull_requests
    ON pull_requests.id = stories_pull_requests.pr_id
  JOIN stories
    ON stories_pull_requests.story_id = stories.id
  JOIN releases_stories
    ON releases_stories.story_id = stories.id
  JOIN releases
    ON releases_stories.release_id = releases.id
  JOIN projects
    ON releases.project_id = projects.id
WHERE
  complexity_score  > 29
  AND julianday('now') - julianday(releases.release_date) <= 60
ORDER BY
  complexity_score DESC
