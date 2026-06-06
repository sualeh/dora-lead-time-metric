-- database: ../../releases.2024-07.2025-03.db
-- Lookback window: 60 days — a two-month rolling window captures recently
-- closed releases and their associated stories and pull requests.
SELECT
  stories.story_key,
  stories.story_title,
  releases.release_title,
  CAST(julianday(date(julianday(stories.story_resolved))) - julianday(releases.release_date) + 1
  -- +1 makes the count inclusive: if story resolves on the release day itself, days_open = 1.
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
  -- +3: 3-day grace period — stories may legitimately resolve shortly
  -- after a release during a stabilization window.
  julianday(date(julianday(stories.story_resolved))) > julianday(releases.release_date) + 3
  AND julianday('now') - julianday(releases.release_date) <= 60
ORDER BY
  releases.release_date,
  stories.story_key
