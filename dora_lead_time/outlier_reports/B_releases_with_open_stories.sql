-- database: ../../releases.2024-07.2025-03.db
SELECT
  stories.story_key,
  stories.story_title,
  releases.release_title,
  CAST(julianday(date(julianday(stories.story_resolved))) - julianday(releases.release_date) + 1
  AS INTEGER)
    AS days_open,
  releases.release_date,
  date(julianday(stories.story_resolved))
    AS story_resolved
FROM
  stories
  JOIN releases
    ON stories.release_id = releases.id
WHERE
  julianday(date(julianday(stories.story_resolved))) > julianday(releases.release_date) + 3
  AND julianday('now') - julianday(releases.release_date) <= 60
ORDER BY
  releases.release_date,
  stories.story_key
