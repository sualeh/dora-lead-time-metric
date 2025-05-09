SELECT
  stories.story_key,
  stories.story_title,
  pull_requests.pr_title,
  CAST(julianday(pull_requests.pr_open) - julianday(pull_requests.earliest_commit_date) AS INTEGER) AS days_between,
  pull_requests.earliest_commit_date,
  pull_requests.pr_open AS pr_created_date,
  pull_requests.pr_url
FROM
  pull_requests
  JOIN stories_pull_requests
    ON pull_requests.id = stories_pull_requests.pr_id
  JOIN stories
    ON stories_pull_requests.story_id = stories.id
  JOIN releases
    ON stories.release_id = releases.id
  JOIN projects
    ON releases.project_id = projects.id
WHERE
  pull_requests.earliest_commit_date IS NOT NULL
  AND julianday(pull_requests.pr_open) - julianday(pull_requests.earliest_commit_date) > 5
  AND julianday('now') - julianday(releases.release_date) <= 60
ORDER BY
  days_between DESC,
  projects.project_key,
  stories.story_key
