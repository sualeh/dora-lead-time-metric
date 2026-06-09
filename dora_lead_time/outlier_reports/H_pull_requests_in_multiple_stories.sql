-- Lookback window: 60 days — a two-month rolling window captures recently
-- closed releases and their associated stories and pull requests.
SELECT
  pull_requests.pr_owner,
  pull_requests.pr_repository,
  pull_requests.pr_number,
  pull_requests.pr_title,
  pull_requests.pr_url,
  COUNT(DISTINCT stories.story_key) AS story_count
FROM
  pull_requests
  JOIN stories_pull_requests
    ON pull_requests.id = stories_pull_requests.pr_id
  JOIN stories
    ON stories_pull_requests.story_id = stories.id
  JOIN releases_stories
    ON releases_stories.story_id = stories.id
  JOIN releases
    ON releases_stories.release_id = releases.id
WHERE
  julianday('now') - julianday(releases.release_date) <= 60
GROUP BY
  pull_requests.pr_owner,
  pull_requests.pr_repository,
  pull_requests.pr_number,
  pull_requests.pr_title,
  pull_requests.pr_url
HAVING
  COUNT(DISTINCT stories.story_key) >= 2
ORDER BY
  story_count DESC,
  pull_requests.pr_owner,
  pull_requests.pr_repository,
  pull_requests.pr_number
