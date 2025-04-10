"""Data models for the package."""

from collections import namedtuple

Project = namedtuple(
    'Project',
    [
        'id',
        'project_internal_id',
        'project_key',
        'project_title',
        'project_type'
    ]
)

Release = namedtuple(
    'Release',
    [
        'id',
        'release_internal_id',
        'release_title',
        'release_description',
        'release_date',
        'project_key'
    ]
)

Story = namedtuple(
    'Story',
    [
        'id',
        'story_key',
        'story_title',
        'story_type',
        'story_created',
        'story_resolved',
        'release_id'
    ]
)

PullRequestIdentifier = namedtuple(
    'PullRequestIdentifier',
    [
        'id',
        'pr_owner',
        'pr_repository',
        'pr_number'
    ]
)

PullRequest = namedtuple(
    'PullRequest',
    [
        'id',
        'pr_title',
        'open_date',
        'close_date',
        'commit_count',
        'earliest_commit_date',
        'latest_commit_date',
        'owner',
        'repo',
        'pr_number'
    ]
)
