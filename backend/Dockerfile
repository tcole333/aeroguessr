# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies if needed (e.g., for specific libraries)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

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

# Copy the rest of the application code into the container
COPY . .

# --- Port Exposure ---

# Expose the port the app runs on
EXPOSE 8000

# --- Run Command ---

# Define the command to run the application (adjust `backend.app:app` as needed)
# The command assumes the main FastAPI app instance is named `app` in `backend/app.py`
# Using --reload is typically for development, remove it for production images.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
