-- Add Jira issue id column to stories table.
--
-- This preserves existing story rows and adds a nullable column used
-- to avoid separate issue-key -> issue-id lookups in PR retrieval.

ALTER TABLE stories
ADD COLUMN jira_issue_id VARCHAR(1024);
