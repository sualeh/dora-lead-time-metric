from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any


class LeadTimeCalculator:
    """Calculator for DORA lead time metrics."""

    @staticmethod
    def calculate_lead_time(commit_time: datetime, deployment_time: datetime) -> timedelta:
        """Calculate lead time between commit and deployment."""
        return deployment_time - commit_time

    @staticmethod
    def average_lead_time(lead_times: List[timedelta]) -> Optional[timedelta]:
        """Calculate average lead time from a list of lead times."""
        if not lead_times:
            return None
        total_seconds = sum(lt.total_seconds() for lt in lead_times)
        return timedelta(seconds=total_seconds / len(lead_times))

    @classmethod
    def process_deployments(cls, deployments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process deployment data to calculate lead time metrics."""
        if not deployments:
            return {
                "average_lead_time": None,
                "min_lead_time": None,
                "max_lead_time": None,
                "total_deployments": 0
            }

        lead_times = []

        for deployment in deployments:
            commit_time = deployment.get("commit_time")
            deployment_time = deployment.get("deployment_time")

            if commit_time and deployment_time:
                lead_time = cls.calculate_lead_time(
                    commit_time, deployment_time
                )
                lead_times.append(lead_time)

        if not lead_times:
            return {
                "average_lead_time": None,
                "min_lead_time": None,
                "max_lead_time": None,
                "total_deployments": len(deployments)
            }

        return {
            "average_lead_time": cls.average_lead_time(lead_times),
            "min_lead_time": min(lead_times),
            "max_lead_time": max(lead_times),
            "total_deployments": len(deployments)
        }


def main():
    """Main entry point of the application."""
    # Example usage
    calculator = LeadTimeCalculator()

    # Sample deployment data
    deployments = [
        {
            "commit_time": datetime(2023, 1, 1, 10, 0),
            "deployment_time": datetime(2023, 1, 1, 14, 0),
            "commit_id": "abc123",
            "environment": "production"
        },
        {
            "commit_time": datetime(2023, 1, 2, 9, 0),
            "deployment_time": datetime(2023, 1, 2, 11, 0),
            "commit_id": "def456",
            "environment": "production"
        }
    ]

    results = calculator.process_deployments(deployments)

    print("DORA Lead Time Metrics:")
    print(f"Average Lead Time: {results['average_lead_time']}")
    print(f"Min Lead Time: {results['min_lead_time']}")
    print(f"Max Lead Time: {results['max_lead_time']}")
    print(f"Total Deployments: {results['total_deployments']}")


if __name__ == "__main__":
    main()
