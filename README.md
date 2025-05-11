[![Build and Test](https://github.com/sualeh/dora-lead-time-metric/actions/workflows/build-test.yml/badge.svg)](https://github.com/sualeh/dora-lead-time-metric/actions/workflows/build-test.yml)
[![PyPI Downloads](https://img.shields.io/pypi/dm/dora-lead-time-metric)](https://pypi.org/project/dora-lead-time-metric/)

# DORA Lead Time Metric

A tool to generate lead time charts and outlier reports by connecting data from Jira and GitHub.

## Overview

Lead Time for Changes is one of the four key DORA (DevOps Research and Assessment) metrics that measure software delivery performance. It measures the time it takes from when code is committed to when it is successfully running in production. A shorter lead time indicates an organization's ability to respond quickly to customer needs and fix problems rapidly.

This Python package calculates lead time by connecting data from Jira and GitHub. The calculation involves going from Projects → Releases → Stories → Pull Requests → Commits, calculating the lead time for each pull request, and averaging those over a given time period.


## Requirements

- Python 3.13 or higher
- OpenAI API key and other parameters (set in your .env file)

## Installation

This project uses [Poetry](https://python-poetry.org/) for dependency management.

1. Install Poetry by following the instructions in the [official documentation](https://python-poetry.org/docs/#installation).

    Quick installation methods:

    ```bash
    # For Linux, macOS, Windows (WSL)
    curl -sSL https://install.python-poetry.org | python3 -
    ```

    ```pwsh
    # For Windows PowerShell
    (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
    ```

2. Install Project Dependencies

    ```bash
    # Clone the repository
    git clone https://github.com/sualeh/dora-lead-time-metric.git
    cd dora-lead-time-metric
    ```

3. Install dependencies using Poetry

    ```bash
    poetry install --extras "dev"
    poetry show --tree
    ```


## Configuration


Create an ".env" file in the project root based on ".env.example", and similarly create an ".env.params" file based on ".env.params.example".

## Usage

1. Create releases database

```bash
poetry run python -m dora_lead_time.main --build
```

2. Generate lead time charts

```bash
poetry run python -m dora_lead_time.main --charts
```

3. Generate outlier reports

```bash
poetry run python -m dora_lead_time.main --reports
```


## Development and Testing

1. Install dependencies, as above.

2. Run all tests:

    ```bash
    poetry run pytest
    ```


## Docker Compose Usage

You can also use Docker Compose for easier management of the Local RAG container:

1. Clone the project, as described above.

2. Configure the ".env" and ".env.params" files as described above.

3. Run the application using Docker Compose:

      ```bash
      # To build a releases database
      docker-compose run dora-lead-time --build
      ```

      ```bash
      # To generate lead time charts
      docker-compose run dora-lead-time --charts
      ```

      ```bash
      # To generate outlier reports
      docker-compose run dora-lead-time --reports
      ```

This approach simplifies volume mounting and environment variable management, especially when working with the tool regularly.
