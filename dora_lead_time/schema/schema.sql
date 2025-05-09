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
	release_date VARCHAR(1024), -- DATE
	project_id INTEGER,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	UNIQUE(release_internal_id, project_id),
	FOREIGN KEY (project_id) REFERENCES projects (id)
);

CREATE TABLE IF NOT EXISTS stories (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	story_key VARCHAR(1024),
	story_title VARCHAR(1024),
	story_type VARCHAR(1024),
	story_created VARCHAR(1024), -- DATE
	story_resolved VARCHAR(1024), -- DATE
	release_id VARCHAR(1024),
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	UNIQUE(story_key, release_id),
	FOREIGN KEY (release_id) REFERENCES releases (id)
);

CREATE TABLE IF NOT EXISTS pull_requests (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	pr_title VARCHAR(1024),
	pr_owner VARCHAR(1024),
	pr_repository VARCHAR(1024),
	pr_number VARCHAR(1024),
	pr_open VARCHAR(1024), -- DATE
	pr_close VARCHAR(1024), -- DATE
	commit_count INTEGER,
	earliest_commit_date VARCHAR(1024), -- DATE
	latest_commit_date VARCHAR(1024), -- DATE
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
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	story_key VARCHAR(1024),
	pr_count INTEGER,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
	UNIQUE(story_key),
	FOREIGN KEY (story_key) REFERENCES stories (story_key)
);

DROP VIEW IF EXISTS lead_times;

CREATE VIEW lead_times AS
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
	  julianday(pull_requests.earliest_commit_date) + 1
	  AS lead_time
FROM
	releases
	JOIN projects
	  ON releases.project_id = projects.id
	JOIN stories
	  ON stories.release_id = releases.id
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
  MIN(strftime('%Y-%m-%d', created_at)) AS earliest_date,
  MAX(strftime('%Y-%m-%d', created_at)) AS latest_date
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
