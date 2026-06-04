# Lead Time and Outlier Report Analysis

This document analyzes the calculations in the lead time report and the outlier reports, assessing whether they match their stated intent, and offering suggestions for improvement.

---

## Lead Time Calculation

### How It Works

The core lead time formula is defined in the `lead_times` view (`schema.sql`):

```sql
julianday(releases.release_date) - julianday(pull_requests.earliest_commit_date) + 1
  AS lead_time
```

**Interpretation:** Lead time is measured from the day of the earliest commit in a pull request up to and including the release day. The `+1` makes the range inclusive — commit day counts as day 1.

This aligns with the stated DORA intent: _"from when code is first committed until it is successfully deployed"_.

### `calculate_lead_time` — Filtering and Aggregation

```sql
WHERE lead_times.lead_time > 0
  AND lead_times.release_date BETWEEN ? AND ?
```

- `lead_time > 0` excludes PRs where the earliest commit date is after the release date (data quality issues). Same-day commits yield `lead_time = 1`, which correctly passes this filter.
- The result is an **average over all qualifying PR lead times**, not over releases. A release with many PRs contributes proportionally more to the average than one with few.

### Findings and Suggestions

| # | Finding | Suggestion |
|---|---------|------------|
| 1 | The average is computed over individual PR lead times, not releases. A release with 10 PRs weighs 10× more than a release with 1 PR. | Document this weighting choice explicitly. Consider offering a per-release average (median of per-release lead times) as an alternative metric. |
| 2 | `int(lead_time.average_lead_time)` in `monthly_lead_time_report` truncates rather than rounds. An average of 4.9 days becomes 4. | Use `round()` instead of `int()` for less-biased display values. |
| 3 | The `lead_times` view joins through `stories` and `stories_pull_requests`. A story without any PR is silently excluded from lead time. | This is correct by design, but a comment in the view would help clarify the intent. |

---

## Outlier Report A — Projects Without Releases

**Intent:** Find projects with no releases in the past 60 days.

**SQL logic:** Projects with zero releases in the `releases` table with `release_date >= date('now', '-60 days')`.

**Assessment:** Correct and straightforward.

### Suggestions

| # | Finding | Suggestion |
|---|---------|------------|
| 1 | The 60-day threshold is hard-coded. | Consider making it a parameter for flexibility across different reporting cadences. |

---

## Outlier Report B — Releases With Open Stories

**Intent:** Find releases where a story was resolved more than 3 days after the release date.

**SQL logic:**
```sql
WHERE julianday(date(julianday(stories.story_resolved))) > julianday(releases.release_date) + 3
  AND julianday('now') - julianday(releases.release_date) <= 60
```

**Assessment:** Broadly correct, but has several issues.

### Findings and Suggestions

| # | Finding | Suggestion |
|---|---------|------------|
| 1 | `date(julianday(stories.story_resolved))` is a redundant round-trip through Julian day format. It provides no benefit when `story_resolved` is already a date string. | Replace with `stories.story_resolved` directly. |
| 2 | `days_open` is calculated as `story_resolved - release_date + 1`, adding 1. But the threshold (`> release_date + 3`) means a 4-day-late story shows `days_open = 5`. The `+1` overstates the delay. | Remove the `+1` from `days_open`. Use `story_resolved - release_date` so "4 days late" shows as 4. |
| 3 | The 3-day grace period and the reason for it are undocumented. | Add a SQL comment explaining the 3-day threshold. |

---

## Outlier Report C — Stories in Multiple Releases

**Intent:** Find stories that appear in more than one release (in the past 60 days), indicating potential double-counting of lead time.

**SQL logic (CTE):**
```sql
HAVING COUNT(DISTINCT releases.release_date) > 1
```

**Assessment:** Has a correctness bug.

### Findings and Suggestions

| # | Finding | Suggestion |
|---|---------|------------|
| 1 | **Bug:** Grouping by `release_date` instead of `release_id`. If two distinct releases share the same date, they are treated as one release, missing a genuine duplicate. | Change to `COUNT(DISTINCT releases.id) > 1`. |
| 2 | The outer query shows all releases for duplicate stories, including releases older than 60 days. This may be intentional (full history) but is inconsistent with the CTE's 60-day window. | Add a comment clarifying whether the full history is desired, or apply the 60-day filter consistently to the outer query. |

---

## Outlier Report D — Releases With Open Pull Requests

**Intent:** Find releases where a PR closed after the release date, suggesting code changes were merged post-release.

**SQL logic:**
```sql
WHERE julianday(pull_requests.pr_close) > julianday(releases.release_date)
  AND julianday('now') - julianday(releases.release_date) <= 60
```

**Assessment:** Has a significant gap.

### Findings and Suggestions

| # | Finding | Suggestion |
|---|---------|------------|
| 1 | **Gap:** PRs with a `NULL` `pr_close` date (never closed/merged) are silently excluded. A release with a permanently open PR is not flagged. | Add `OR pull_requests.pr_close IS NULL` to the `WHERE` clause. |
| 2 | `days_open` is calculated as `pr_close - release_date` (no `+1`), while Report B uses `+1` for the equivalent "days late" calculation. | Apply a consistent formula across both reports. Decide on `+1` inclusive or exclusive and document it. |

---

## Outlier Report E — Stories Without Pull Requests

This report has two parts: a count summary (`E_counts`) and a detail list (`E_stories`).

### E_stories — Detail List

**Intent:** List all stories in recent releases that have no associated pull request.

**Assessment:** Correct. The `LEFT JOIN ... WHERE pr_id IS NULL` pattern is the appropriate approach. `SELECT DISTINCT` is correct.

### E_counts — Count Summary

**Intent:** Show, per project, how many stories lack pull requests and what percentage that represents.

**Assessment:** Has a correctness bug due to double-counting.

### Findings and Suggestions

| # | Finding | Suggestion |
|---|---------|------------|
| 1 | **Bug:** The `LEFT JOIN pull_requests` multiplies story rows for stories with multiple PRs. `COUNT(stories.id)` over-counts `total_stories`. For a story with 2 PRs, `total_stories` counts it twice. | Replace with `COUNT(DISTINCT stories.id)` for `total_stories`. Count stories with and without PRs using subqueries or conditional distinct counts. |
| 2 | **Bug:** `MIN(COUNT(stories.id), COUNT(...))` is used to cap counts. This does not correctly compensate for the over-counting and produces incorrect values. | Remove the `MIN` wrapper. Fix the root cause by counting distinct stories. |

A corrected version of the CTE:

```sql
WITH project_story_counts AS (
  SELECT
    projects.project_key,
    COUNT(DISTINCT stories.id) AS total_stories,
    COUNT(DISTINCT CASE WHEN pull_requests.id IS NOT NULL THEN stories.id END)
      AS stories_with_prs,
    COUNT(DISTINCT CASE WHEN pull_requests.id IS NULL THEN stories.id END)
      AS stories_without_prs
  FROM projects
    LEFT JOIN releases ON projects.id = releases.project_id
    LEFT JOIN stories ON releases.id = stories.release_id
    LEFT JOIN stories_pull_requests ON stories.id = stories_pull_requests.story_id
    LEFT JOIN pull_requests ON stories_pull_requests.pr_id = pull_requests.id
  WHERE stories.story_resolved >= date('now', '-60 days')
  GROUP BY projects.project_key
  HAVING COUNT(DISTINCT stories.id) > 0
)
```

---

## Outlier Report F — Pull Requests With Old Commits

**Intent:** Find PRs where the earliest commit is more than 5 days older than the PR creation date, suggesting long-lived branches.

**SQL logic:**
```sql
WHERE pull_requests.earliest_commit_date IS NOT NULL
  AND julianday(pull_requests.pr_open) - julianday(pull_requests.earliest_commit_date) > 5
  AND julianday('now') - julianday(releases.release_date) <= 60
```

**Assessment:** Logically sound, but has a presentation issue.

### Findings and Suggestions

| # | Finding | Suggestion |
|---|---------|------------|
| 1 | No `DISTINCT` on the `SELECT`. A PR linked to multiple stories appears once per story, making the same PR appear to be a repeated problem. | Add `SELECT DISTINCT pull_requests.pr_url, pull_requests.pr_title, days_between, ...` or restructure to be PR-centric rather than story-centric. |
| 2 | The 5-day threshold is undocumented. | Add a SQL comment explaining why 5 days is the threshold. |

---

## Outlier Report G — Zero or Negative Lead Times

**Intent:** Find PRs where the lead time is zero or negative (data quality issues).

**SQL logic:**
```sql
WHERE pull_requests.earliest_commit_date IS NOT NULL
  AND julianday(releases.release_date) <= julianday(pull_requests.earliest_commit_date)
  AND julianday('now') - julianday(releases.release_date) <= 60
```

**Assessment:** The condition captures more than the name implies.

### Findings and Suggestions

| # | Finding | Suggestion |
|---|---------|------------|
| 1 | The condition `release_date <= earliest_commit_date` captures **same-day** commits (`release_date = earliest_commit_date`). However, the `lead_times` view formula gives same-day commits a `lead_time = 1`, so they are **not excluded** from the main lead time calculation by the `lead_time > 0` filter. Same-day commits are thus not actually "zero or negative" — they yield a valid lead time of 1 day. | Change the condition to `release_date < earliest_commit_date` for true zero/negative cases. Separate same-day commits into a distinct "Same-day commit" report or note, since they are included in the metric. |
| 2 | The `lead_time` column in Report G's output uses the same formula as the view (`release_date - earliest_commit_date + 1`). For same-day commits this shows `1`, which is inconsistent with the report's purpose of showing zero/negative values. | Consistent with suggestion #1, remove same-day cases from this report. |

---

## Cross-Cutting Issues

| # | Issue | Suggestion |
|---|-------|------------|
| 1 | **Inconsistent lookback windows.** Reports A, B, C, D, E, F, G all use 60 days, but C's outer query shows data outside that window. | Apply the 60-day filter consistently throughout all queries, or parameterize the lookback period. |
| 2 | **Hard-coded thresholds.** The 3-day grace period (B), 5-day old-commit threshold (F), and 60-day lookback (all reports) are magic numbers. | Consider defining these as named constants or SQL parameters with comments explaining their rationale. |
| 3 | **Inconsistent `+1` treatment in "days late" columns.** Report B uses `+1` in `days_open`; Report D does not. | Standardize on one convention and document it. |
| 4 | **`_get_connection` is duplicated** between `LeadTimeReport` and `OutlierReports`. | Extract into a shared utility function or base class. |
| 5 | **Date columns are stored as `VARCHAR`** in the schema (with `-- DATE` comments). SQLite type affinity rules mean arithmetic on these columns works, but explicit `DATE` type or at minimum a schema note would make the intent clearer. | Consider using `DATE` as the column type, or add a schema-level note explaining the VARCHAR choice. |
