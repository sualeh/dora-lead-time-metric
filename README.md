# DORA Lead Time Metric

## DORA Lead Time for Changes

Lead Time for Changes is one of the four key DORA (DevOps Research and Assessment) metrics that measure software delivery performance. It measures the time it takes from when code is committed to when it is successfully running in production. A shorter lead time indicates an organization's ability to respond quickly to customer needs and fix problems rapidly.

This Python package calculates lead time by connecting data from Jira and GitHub. The calculation involves going from Projects → Releases → Stories → Pull Requests → Commits, calculating the lead time for each pull request, and averaging those over a given time period.


## How to Use

See [Calculate the DORA Lead Time Metric in Python](https://dev.to/sualeh/calculate-the-dora-lead-time-metric-in-python-2bhn) for a detailed explanation of how to use this code. The code is at [sualeh/dora-lead-time-metric](https://github.com/sualeh/dora-lead-time-metric).


## Build

Install

- Python 3.13 or higher
- Poetry (Python dependency manager)

Clone the repository:

  ```bash
  git clone https://github.com/sualeh/dora-lead-time-metric.git
  cd dora-lead-time-metric
  ```

Install dependencies using Poetry:

```bash
poetry install
```

Create an `.env` file in the project root based on `.env.example`

Activate the Poetry environment:

```bash
poetry shell
```

Run the main application:

```bash
python -m dora_lead_time.main
```

Generate reports with code similar to the following:

```python
from dora_lead_time.lead_time_report import LeadTimeReport

# Initialize the report generator
report = LeadTimeReport("releases.db")

# Generate a monthly report
monthly_data = report.monthly_lead_time_report(
    ["PROJECT1", "PROJECT2"],
    date(2023, 1, 1),
    date(2023, 12, 31)
)

# Visualize the report
plt = report.show_plot(monthly_data, title="Monthly Lead Time", show_trend=True)
plt.savefig('lead_time_trend.png')
```


## With Docker

Build the Docker image:

```bash
docker build -t dora-lead-time-metric .
```

or download it from Docker Hub:

```bash
docker pull sualeh.fatehi/dora-lead-time-metric
```

Run the container:

```bash
docker run -it --rm \
  --env-file .env \
  -v "$(pwd)/data:/data" \
  dora-lead-time-metric
```
