-- Lookback window: 60 days — a two-month rolling window captures recently
-- closed releases and their associated stories and pull requests.
SELECT
  projects.project_key,
  releases.release_internal_id,
  releases.release_title,
  releases.release_date,
  stories.story_key,
  stories.story_title,
  date(julianday(stories.story_created))
    AS story_created,
  CAST(
    julianday(date(julianday(stories.story_created))) -
    julianday(releases.release_date)
    AS INTEGER
  ) AS days_after_release,
  'Story created after release date'
    AS reason
FROM
  releases
  JOIN projects
    ON releases.project_id = projects.id
  JOIN releases_stories
    ON releases_stories.release_id = releases.id
  JOIN stories
    ON releases_stories.story_id = stories.id
WHERE
  stories.story_created IS NOT NULL
  AND julianday(date(julianday(stories.story_created))) >
    julianday(releases.release_date)
  AND julianday('now') - julianday(releases.release_date) <= 60
ORDER BY
  releases.release_date,
  days_after_release DESC,
  stories.story_key
