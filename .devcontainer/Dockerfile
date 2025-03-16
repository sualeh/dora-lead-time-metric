# Use a base image with Python preinstalled
FROM mcr.microsoft.com/vscode/devcontainers/python:dev-3.13

# Set the working directory in the container
WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Jupyter Notebook and Python dependencies
RUN \
  pip install --upgrade pip \
  pip install jupyter python-dotenv requests jupyter numpy pandas matplotlib

# Expose port for Jupyter Notebook
EXPOSE 8888

# Set up JupyterLab to run on container start
CMD ["jupyter-lab", "--ip=0.0.0.0", "--no-browser", "--allow-root"]
