-- database: ../../releases.2024-07.2025-03.db
WITH duplicate_stories AS (
  SELECT
    stories.story_key
  FROM
    stories
    JOIN releases
      ON stories.release_id = releases.id
  WHERE
    releases.release_date >= date('now', '-60 days')
  GROUP BY
    stories.story_key
  HAVING
    COUNT(DISTINCT releases.release_date) > 1
)
SELECT
  stories.story_key,
  stories.story_title,
  releases.release_internal_id,
  releases.release_title,
  releases.release_date
FROM
  stories
  JOIN releases
    ON stories.release_id = releases.id
WHERE
  stories.story_key IN (
    SELECT
      duplicate_stories.story_key
    FROM
    duplicate_stories
  )
ORDER BY
  stories.story_key,
  releases.release_date
