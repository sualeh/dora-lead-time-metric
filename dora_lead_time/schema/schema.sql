CREATE TABLE IF NOT EXISTS projects (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	project_internal_id VARCHAR(1024),
	project_key VARCHAR(1024),
	project_title VARCHAR(1024),
	project_type VARCHAR(1024),
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	UNIQUE(project_internal_id),
	UNIQUE(project_key)
);

CREATE TABLE IF NOT EXISTS releases (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	release_internal_id VARCHAR(1024),
	release_title VARCHAR(1024),
	release_description VARCHAR(2048),
	release_date DATE,
	project_id INTEGER,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	UNIQUE(release_internal_id, project_id),
	FOREIGN KEY (project_id) REFERENCES projects (id)
);

CREATE TABLE IF NOT EXISTS stories (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	story_internal_id VARCHAR(1024),
	story_key VARCHAR(1024),
	story_title VARCHAR(1024),
	story_type VARCHAR(1024),
	story_created DATETIME,
	story_resolved DATETIME,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	UNIQUE(story_internal_id),
	UNIQUE(story_key)
);

CREATE TABLE IF NOT EXISTS releases_stories (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	release_id INTEGER,
	story_id INTEGER,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	UNIQUE(release_id, story_id),
	FOREIGN KEY (release_id) REFERENCES releases (id),
	FOREIGN KEY (story_id) REFERENCES stories (id)
);

CREATE TABLE IF NOT EXISTS pull_requests (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	pr_title VARCHAR(1024),
	pr_owner VARCHAR(1024),
	pr_repository VARCHAR(1024),
	pr_number VARCHAR(1024),
	pr_open DATE,
	pr_close DATE,
	commit_count INTEGER,
	earliest_commit_date DATE,
	latest_commit_date DATE,
	pr_url VARCHAR(1024) GENERATED ALWAYS
	  AS (
		'https://github.com/' || pr_owner || '/' ||
		pr_repository || '/pull/' || pr_number
	  ) VIRTUAL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	UNIQUE(pr_owner, pr_repository, pr_number)
);

CREATE TABLE IF NOT EXISTS stories_pull_requests (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	story_id INTEGER,
	pr_id INTEGER,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	UNIQUE(story_id, pr_id),
	FOREIGN KEY (story_id) REFERENCES stories (id),
	FOREIGN KEY (pr_id) REFERENCES pull_requests (id)
);

CREATE TABLE IF NOT EXISTS stories_pull_request_counts (
	story_id INTEGER PRIMARY KEY,
	pr_count INTEGER,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY (story_id) REFERENCES stories (id)
);

DROP VIEW IF EXISTS lead_times;

CREATE VIEW lead_times AS
-- Stories without any associated pull request are excluded by design:
-- lead time is measured via commits, so only stories linked to at least
-- one PR contribute to the metric.
SELECT
	releases.id
	AS release_id,
	releases.release_date,
	projects.project_key,
	pull_requests.id
	AS pr_id,
	pull_requests.pr_title,
	pull_requests.pr_owner,
	pull_requests.pr_repository,
	pull_requests.pr_number,
	pull_requests.earliest_commit_date,
	julianday(releases.release_date) -
	  julianday(pull_requests.earliest_commit_date)
	  AS lead_time
FROM
	releases
	JOIN projects
	  ON releases.project_id = projects.id
	JOIN releases_stories
	  ON releases_stories.release_id = releases.id
	JOIN stories
	  ON releases_stories.story_id = stories.id
	JOIN stories_pull_requests
	  ON stories_pull_requests.story_id = stories.id
	JOIN pull_requests
	  ON stories_pull_requests.pr_id = pull_requests.id;

DROP VIEW IF EXISTS summary;

CREATE VIEW summary AS
SELECT
  1 as id,
  'releases' AS type,
  COUNT(*) AS count,
  MIN(strftime('%Y-%m-%d', release_date)) AS earliest_date,
  MAX(strftime('%Y-%m-%d', release_date)) AS latest_date
FROM
  releases
UNION
SELECT
  2 as id,
  'stories' AS type,
  COUNT(*) AS count,
  MIN(strftime('%Y-%m-%d', story_created)) AS earliest_date,
  MAX(strftime('%Y-%m-%d', story_resolved)) AS latest_date
FROM
  stories
UNION
SELECT
  3 as id,
  'pull_requests' AS type,
  COUNT(*) AS count,
  MIN(pr_open) AS earliest_date,
  MAX(pr_close) AS latest_date
FROM
  pull_requests
;
