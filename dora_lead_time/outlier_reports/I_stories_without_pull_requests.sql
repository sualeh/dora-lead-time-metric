-- database: ../../releases.2024-07.2025-03.db
-- Lookback window: 60 days — a two-month rolling window captures recently
-- closed releases and their associated stories and pull requests.
SELECT DISTINCT
  stories.id AS story_id,
  projects.project_key,
  projects.project_title,
  stories.story_key,
  stories.story_type,
  stories.story_title
FROM
  stories
  JOIN releases_stories
    ON releases_stories.story_id = stories.id
  JOIN releases
    ON releases_stories.release_id = releases.id
  JOIN projects
    ON releases.project_id = projects.id
  LEFT JOIN stories_pull_requests
    ON stories.id = stories_pull_requests.story_id
  LEFT JOIN pull_requests
    ON stories_pull_requests.pr_id = pull_requests.id
WHERE
  pull_requests.id IS NULL
  AND julianday('now') - julianday(releases.release_date) <= 60
ORDER BY
  projects.project_key,
  stories.story_type,
  stories.story_key
