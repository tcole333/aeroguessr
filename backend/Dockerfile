# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies including supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# --- Dependency Installation (Choose one method) ---

# Method 1: Using requirements.txt (if not using Poetry)
# COPY requirements.txt .
# RUN pip install --no-cache-dir --upgrade pip
# RUN pip install --no-cache-dir -r requirements.txt

# Method 2: Using Poetry (preferred for this project based on task list)
# Install Poetry and project dependencies
COPY pyproject.toml poetry.lock* ./
RUN pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# --- Application Code ---

# Copy backend code and configs
COPY backend/ ./backend/
COPY backend/supervisord.conf /app/supervisord.conf
COPY backend/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# --- Port Exposure ---

# Expose the port the app runs on
EXPOSE 8000

# --- Run Command ---

# Use the entrypoint script to start both API and ingest services via supervisor
CMD ["/app/entrypoint.sh"]
