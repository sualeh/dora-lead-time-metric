SELECT
  stories.story_key,
  stories.story_title,
  pull_requests.pr_title,
  releases.release_date,
  pull_requests.earliest_commit_date,
  pull_requests.pr_open AS pr_created_date,
  pull_requests.pr_close AS pr_closed_date,
  julianday(releases.release_date) - julianday(pull_requests.earliest_commit_date) + 1
    AS lead_time,
  CASE
    WHEN pull_requests.earliest_commit_date > releases.release_date THEN 'Earliest commit after release'
    WHEN pull_requests.earliest_commit_date = releases.release_date THEN 'Same-day commit and release'
    ELSE 'Other issue'
  END
    AS reason,
  pull_requests.pr_url
FROM
  releases
  JOIN projects
    ON releases.project_id = projects.id
  JOIN stories
    ON stories.release_id = releases.id
  JOIN stories_pull_requests
    ON stories_pull_requests.story_id = stories.id
  JOIN pull_requests
    ON stories_pull_requests.pr_id = pull_requests.id
WHERE
  pull_requests.earliest_commit_date IS NOT NULL
  AND
    julianday(releases.release_date) <= julianday(pull_requests.earliest_commit_date)
  AND julianday('now') - julianday(releases.release_date) <= 60
ORDER BY
  lead_time,
  pull_requests.earliest_commit_date
