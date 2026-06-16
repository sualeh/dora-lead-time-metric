-- Lookback window: unbounded for this report to match current
-- retrieve_releases_without_stories behavior.
SELECT
  releases.release_internal_id,
  releases.release_title,
  releases.release_date,
  projects.project_key,
  projects.project_title
FROM
  releases
  LEFT JOIN releases_stories
    ON releases.id = releases_stories.release_id
  LEFT JOIN projects
    ON releases.project_id = projects.id
WHERE
  releases_stories.story_id IS NULL
ORDER BY
  releases.release_date,
  releases.release_internal_id
