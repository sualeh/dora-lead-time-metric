FROM python:3.10-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry==1.5.1

# Copy poetry config files
COPY pyproject.toml poetry.lock* ./

# Configure poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-dev

# Copy the application
COPY dora_lead_time/ ./dora_lead_time/

# Set the entrypoint
ENTRYPOINT ["python", "-m", "dora_lead_time.main"]
