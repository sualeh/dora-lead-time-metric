FROM python:3.13-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy poetry config files
COPY pyproject.toml poetry.lock* ./

# Configure poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Copy the application
COPY dora_lead_time/ ./dora_lead_time/

# Install dependencies
RUN poetry install --no-dev

# Set the entrypoint
ENTRYPOINT ["python", "-m", "dora_lead_time.main"]
