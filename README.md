# DORA Lead Time Metric

A Python tool to calculate DORA (DevOps Research and Assessment) lead time metrics.

## Installation

### Using Poetry
```bash
poetry install
```

### Using pip
```bash
pip install dora-lead-time-metric
```

## Usage

```python
from datetime import datetime
from dora_lead_time.main import LeadTimeCalculator

# Sample deployment data
deployments = [
    {
        "commit_time": datetime(2023, 1, 1, 10, 0),
        "deployment_time": datetime(2023, 1, 1, 14, 0),
        "commit_id": "abc123",
        "environment": "production"
    }
]

calculator = LeadTimeCalculator()
results = calculator.process_deployments(deployments)

print(f"Average Lead Time: {results['average_lead_time']}")
```

## Development

### Setup
```bash
poetry install
```

### Running Tests
```bash
poetry run pytest
```

### Running with Coverage
```bash
poetry run pytest --cov=dora_lead_time tests/
```

## Docker

Build the Docker image:
```bash
docker build -t dora-lead-time-metric .
```

Run the container:
```bash
docker run dora-lead-time-metric
```
