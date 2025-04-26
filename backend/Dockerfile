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
# Install poetry
RUN pip install poetry
# Copy only dependency files first for better caching
COPY pyproject.toml poetry.lock* ./
# Install dependencies
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --no-dev
# Use --no-dev if you want to exclude development dependencies in the final image

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
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
