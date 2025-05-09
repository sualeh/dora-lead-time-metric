-- database: ../../releases.2024-07.2025-03.db
WITH project_story_counts AS (
  SELECT
    projects.project_key,
    MIN(COUNT(stories.id), COUNT(CASE WHEN pull_requests.id IS NOT NULL THEN 1 END))
      AS stories_with_prs,
    MIN(COUNT(stories.id), COUNT(CASE WHEN pull_requests.id IS NULL THEN 1 END))
      AS stories_without_prs,
    COUNT(stories.id)
          AS total_stories
  FROM
    projects
    LEFT JOIN releases
      ON projects.id = releases.project_id
    LEFT JOIN stories
      ON releases.id = stories.release_id
    LEFT JOIN stories_pull_requests
      ON stories.id = stories_pull_requests.story_id
    LEFT JOIN pull_requests
      ON stories_pull_requests.pr_id = pull_requests.id
  WHERE
    stories.story_resolved >= date('now', '-60 days')
  GROUP BY
    projects.project_key
  HAVING
    COUNT(stories.id) > 0
)
SELECT
  p.project_key,
  p.project_title,
  COALESCE(s.stories_without_prs, 0)
      AS stories_without_prs,
  COALESCE(s.total_stories, 0)
      AS total_stories,
  CASE
    WHEN COALESCE(s.total_stories, 0) = 0 THEN 0.0
    ELSE CAST(ROUND((COALESCE(s.stories_without_prs, 0) * 100.0 / COALESCE(s.total_stories, 0)), 0) AS INTEGER)
  END
      AS percentage_stories_without_prs
FROM
  projects p
  JOIN project_story_counts s
    ON p.project_key = s.project_key
ORDER BY
  percentage_stories_without_prs DESC
