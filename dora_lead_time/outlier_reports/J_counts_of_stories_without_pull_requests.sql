-- database: ../../releases.2024-07.2025-03.db
-- Lookback window: 60 days — a two-month rolling window captures recently
-- closed releases and their associated stories and pull requests.
WITH project_story_counts AS (
  SELECT
    projects.project_key,
    projects.project_title,
    stories.story_type,
    COUNT(DISTINCT stories.id)
      AS total_stories,
    COUNT(DISTINCT
      CASE WHEN pull_requests.id IS NOT NULL
        THEN stories.id
      END
    )
      AS stories_with_prs,
    COUNT(DISTINCT
      CASE WHEN pull_requests.id IS NULL
        THEN stories.id
      END
    )
      AS stories_without_prs
  FROM
    projects
    LEFT JOIN releases
      ON projects.id = releases.project_id
    LEFT JOIN releases_stories
      ON releases.id = releases_stories.release_id
    LEFT JOIN stories
      ON releases_stories.story_id = stories.id
    LEFT JOIN stories_pull_requests
      ON stories.id = stories_pull_requests.story_id
    LEFT JOIN pull_requests
      ON stories_pull_requests.pr_id = pull_requests.id
  WHERE
    stories.story_resolved >= date('now', '-60 days')
  GROUP BY
    projects.project_key,
    projects.project_title,
    stories.story_type
  HAVING
    COUNT(DISTINCT stories.id) > 0
)
SELECT
  project_story_counts.project_key,
  project_story_counts.project_title,
  project_story_counts.story_type,
  COALESCE(project_story_counts.stories_without_prs, 0)
      AS stories_without_prs,
  COALESCE(project_story_counts.total_stories, 0)
      AS total_stories,
  CASE
    WHEN COALESCE(project_story_counts.total_stories, 0) = 0
      THEN 0.0
      ELSE CAST(
        ROUND(
        (
          COALESCE(project_story_counts.stories_without_prs, 0) * 100.0 /
          COALESCE(project_story_counts.total_stories, 0)
        ), 0)
        AS INTEGER)
  END
      AS percentage_stories_without_prs
FROM
  project_story_counts
ORDER BY
  percentage_stories_without_prs DESC,
  project_story_counts.project_key,
  project_story_counts.story_type
