-- database: ../../releases.2024-07.2025-03.db
SELECT DISTINCT
  stories.story_key,
  stories.story_title,
  pull_requests.pr_title,
  releases.release_title,
  CAST(julianday(pull_requests.pr_close) - julianday(releases.release_date)
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
  julianday(pull_requests.pr_close) > julianday(releases.release_date)
  AND julianday('now') - julianday(releases.release_date) <= 60
ORDER BY
  releases.release_date,
  pull_requests.pr_owner,
  pull_requests.pr_repository,
  pull_requests.pr_number
