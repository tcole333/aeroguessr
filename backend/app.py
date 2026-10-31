"""Main FastAPI application for the AeroGuessr backend."""

import asyncio
import logging
import logging.handlers  # Added import
import os  # Added import
import sys  # Add sys import
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.routes import client_config, health, rooms
from backend.routes.rooms import manager as connection_manager
from backend.services.broadcast import broadcast_plane_updates
from backend.services.client_config import warn_if_monitored_airport_unknown
from backend.settings import get_settings
from backend.utils import airport_db
from backend.utils.redis_async import RedisClient
from backend.version import app_version

# --- Centralized Logger Configuration ---
# Ensure 'logs' directory exists at the project root
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

LOG_FILE_PATH = os.path.join(LOGS_DIR, "backend.log")

# Get the root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)  # Set root logger level

# Clear existing handlers from the root logger, if any (to avoid duplicates on reload)
if root_logger.hasHandlers():
    root_logger.handlers.clear()

# Create console handler
console_handler = logging.StreamHandler(sys.stderr)
console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)

# Create rotating file handler
file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE_PATH,
    maxBytes=5 * 1024 * 1024,  # 5MB per file for dev
    backupCount=1,  # Keep only 1 backup for dev
)
file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

# --- End Centralized Logger Configuration ---


# --- Custom Exception Handler for Validation Errors --- #
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Log the detailed validation errors
    error_details = (
        f"Validation error for request {request.method} {request.url.path}: {exc.errors()}"
    )
    logger.error(error_details)
    # Return the default 422 response structure that FastAPI uses
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


# --- Global State / Dependencies --- #
# Initialize outside lifespan for potential direct access if needed,
# but manage connections within lifespan.
# TODO: Review if global instances are the best approach vs. dependency injection.
redis_client = RedisClient()  # Assumes RedisClient() handles
# connection setup internally or lazily
# Use the same ConnectionManager instance used by room WebSocket endpoints to
# ensure background broadcast tasks and routes share connection tracking.
# This avoids issues where plane `delta` messages are prepared but not delivered
# because the broadcast task held a separate, empty manager instance.
# Import after rooms to avoid circular import problems.


# --- Application Lifespan Management --- #
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handles application startup and shutdown events."""
    logger.info("Application startup...")

    # Scoring is meaningless without the airport dataset, so refuse to start
    # (FileNotFoundError / ValueError) rather than score every guess as 0.
    airports = airport_db.load_airports()
    logger.info(f"Loaded {len(airports)} airport codes from {airport_db.DATA_PATH}")
    warn_if_monitored_airport_unknown(get_settings())
    # Working the version out here also spares /healthz the file read and the git call
    logger.info(f"AeroGuessr {app_version(get_settings())}")

    # Start background tasks – ensure we don't spawn duplicates if the module is
    # re-imported (e.g. when running with `uvicorn --reload`).
    if not getattr(app.state, "broadcast_started", False):
        broadcast_task = asyncio.create_task(
            broadcast_plane_updates(redis_client, connection_manager)
        )
        app.state.broadcast_started = True
        logger.info("Broadcast task started.")
    else:
        broadcast_task = None  # type: ignore
        logger.debug("Broadcast task already running – skipping second startup.")

    yield  # Application runs here

    # --- Shutdown --- #
    logger.info("Application shutdown...")

    # Cancel background tasks only if we started one
    if broadcast_task is not None:
        logger.info("Attempting to cancel broadcast task...")
        broadcast_task.cancel()
        try:
            await broadcast_task
            logger.info("Broadcast task cancelled successfully.")
        except asyncio.CancelledError:
            logger.info("Broadcast task already cancelled.")
        except Exception as e:
            logger.error(f"Error during broadcast task shutdown: {e}", exc_info=True)

    logger.info("Application shutdown complete.")


# --- FastAPI App Initialization --- #
app = FastAPI(
    title="AeroGuessr API",
    description="API for managing game rooms, players, and flight data.",
    version="0.1.0",
    lifespan=lifespan,  # Register the lifespan context manager
)

# Allow CORS (including WebSocket handshake) from frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins during dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the custom exception handler
app.add_exception_handler(RequestValidationError, validation_exception_handler)


# --- API Endpoints --- #
@app.get("/")
async def read_root() -> Dict[str, str]:
    """Root endpoint providing a basic welcome message."""
    return {"message": "Welcome to the AeroGuessr API!"}


# --- Routers & WebSocket --- #
app.include_router(health.router)
app.include_router(client_config.router)
app.include_router(rooms.router)
