-- database: ../../releases.2024-07.2025-03.db
WITH release_counts AS (
  SELECT
    releases.project_id,
    COUNT(*)
      AS release_count
  FROM
    releases
  WHERE
    releases.release_date >= date('now', '-60 days')
  GROUP BY
    releases.project_id
)
SELECT
  projects.project_key,
  projects.project_title,
  projects.project_type
FROM
  projects
  LEFT JOIN release_counts
    ON projects.id = release_counts.project_id
WHERE
  COALESCE(release_counts.release_count, 0) = 0
ORDER BY
    projects.project_key
