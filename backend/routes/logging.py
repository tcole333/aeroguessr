"""Logging route for frontend log collection."""

import logging
import logging.handlers
import os
from typing import Dict

from fastapi import APIRouter, status
from pydantic import BaseModel

# Get logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v0/logs", tags=["logging"])

# Ensure logs directory exists
LOGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs"
)
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

FRONTEND_LOG_PATH = os.path.join(LOGS_DIR, "frontend.log")

# Set up frontend logger with rotation
frontend_logger = logging.getLogger("frontend")
frontend_logger.setLevel(logging.DEBUG)
frontend_logger.propagate = False  # Don't propagate to root logger

# Create rotating file handler for frontend logs
frontend_file_handler = logging.handlers.RotatingFileHandler(
    FRONTEND_LOG_PATH,
    maxBytes=5 * 1024 * 1024,  # 5MB for dev
    backupCount=1,  # Keep only 1 backup for dev
)
frontend_formatter = logging.Formatter("%(asctime)s - frontend - %(levelname)s - %(message)s")
frontend_file_handler.setFormatter(frontend_formatter)
frontend_logger.addHandler(frontend_file_handler)


class LogEntry(BaseModel):
    """Frontend log entry."""

    level: str  # debug, info, warn, error
    message: str
    timestamp: float  # Unix timestamp from frontend
    context: Dict[str, str] = {}  # Optional context like component name, user action, etc.


@router.post("/frontend", status_code=status.HTTP_204_NO_CONTENT)
async def log_frontend_message(entry: LogEntry) -> None:
    """Accept log messages from the frontend and write them to file.

    Args:
        entry: Log entry containing level, message, timestamp, and optional context

    Returns:
        None (204 No Content)
    """
    # Map frontend log levels to Python logging levels
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }

    log_level = level_map.get(entry.level.lower(), logging.INFO)

    # Format the message with context if provided
    message_parts = [entry.message]
    if entry.context:
        context_str = " ".join(f"{k}={v}" for k, v in entry.context.items())
        message_parts.append(f"[{context_str}]")

    full_message = " ".join(message_parts)

    # Log with the appropriate level
    frontend_logger.log(log_level, full_message)

    # Also log to backend logger at debug level for visibility
    logger.debug(f"Frontend log: [{entry.level}] {full_message}")
