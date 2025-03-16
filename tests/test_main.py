from datetime import datetime, timedelta
import pytest
from dora_lead_time.main import LeadTimeCalculator


def test_calculate_lead_time():
    """Test lead time calculation between commit and deployment."""
    commit_time = datetime(2023, 1, 1, 10, 0)
    deployment_time = datetime(2023, 1, 1, 14, 0)

    lead_time = LeadTimeCalculator.calculate_lead_time(commit_time, deployment_time)

    assert lead_time == timedelta(hours=4)


def test_average_lead_time():
    """Test average lead time calculation."""
    lead_times = [
        timedelta(hours=4),
        timedelta(hours=2),
        timedelta(hours=6)
    ]

    avg_lead_time = LeadTimeCalculator.average_lead_time(lead_times)

    assert avg_lead_time == timedelta(hours=4)


def test_average_lead_time_empty_list():
    """Test average lead time calculation with empty list."""
    avg_lead_time = LeadTimeCalculator.average_lead_time([])

    assert avg_lead_time is None


def test_process_deployments():
    """Test processing deployment data."""
    deployments = [
        {
            "commit_time": datetime(2023, 1, 1, 10, 0),
            "deployment_time": datetime(2023, 1, 1, 14, 0),
            "commit_id": "abc123",
        },
        {
            "commit_time": datetime(2023, 1, 2, 9, 0),
            "deployment_time": datetime(2023, 1, 2, 11, 0),
            "commit_id": "def456",
        }
    ]

    results = LeadTimeCalculator.process_deployments(deployments)

    assert results["average_lead_time"] == timedelta(hours=3)
    assert results["min_lead_time"] == timedelta(hours=2)
    assert results["max_lead_time"] == timedelta(hours=4)
    assert results["total_deployments"] == 2


def test_process_deployments_empty_list():
    """Test processing empty deployment data."""
    results = LeadTimeCalculator.process_deployments([])

    assert results["average_lead_time"] is None
    assert results["min_lead_time"] is None
    assert results["max_lead_time"] is None
    assert results["total_deployments"] == 0


def test_process_deployments_missing_data():
    """Test processing deployment data with missing timestamps."""
    deployments = [
        {
            "commit_id": "abc123",
        },
        {
            "commit_time": datetime(2023, 1, 2, 9, 0),
            "commit_id": "def456",
        }
    ]

    results = LeadTimeCalculator.process_deployments(deployments)

    assert results["average_lead_time"] is None
    assert results["min_lead_time"] is None
    assert results["max_lead_time"] is None
    assert results["total_deployments"] == 2
