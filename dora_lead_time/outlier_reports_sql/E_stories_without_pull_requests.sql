-- database: ../../releases.2024-07.2025-03.db
SELECT DISTINCT
  stories.id AS story_id,
  projects.project_key,
  projects.project_title,
  stories.story_key,
  stories.story_title
FROM
  stories
  JOIN releases
    ON stories.release_id = releases.id
  JOIN projects
    ON releases.project_id = projects.id
  LEFT JOIN stories_pull_requests
    ON stories.id = stories_pull_requests.story_id
  LEFT JOIN pull_requests
    ON stories_pull_requests.pr_id = pull_requests.id
WHERE
  pull_requests.id IS NULL
  AND julianday('now') - julianday(releases.release_date) <= 60
