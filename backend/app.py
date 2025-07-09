"""Main FastAPI application for the Plane Guessing Game backend."""

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

from backend.routes import logging as logging_routes  # Import the logging router
from backend.routes import rooms  # Import the rooms router
from backend.routes.rooms import manager as connection_manager

# Explicitly import endpoint for add_api_websocket_route if needed,
# but router usually handles this.
# from backend.routes.rooms import websocket_endpoint
from backend.services.broadcast import broadcast_plane_updates
from backend.utils.redis_async import RedisClient

# --- Remove Basic Logging Configuration ---
# logging.basicConfig(level=logging.INFO, stream=sys.stderr,
# format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# --- End Basic Logging Configuration Removal ---


# --- Custom Log Filter ---
class DeltaFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if '\\"type\\":\\"delta\\"' in msg:  # Check for '{"type":"delta"}'
            return False
        if record.name == "backend.services.broadcast" and "Delta broadcasted" in msg:
            return False
        # The following will filter out the noisy DEBUG messages from websockets library if needed
        # if record.name == 'websockets.server' and record.levelno ==
        # logging.DEBUG and ('> TEXT' in msg or '< TEXT' in msg or '> CLOSE'
        # in msg or '< CLOSE' in msg):
        #     return False
        return True


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

# Add the custom filter to the file handler
delta_filter = DeltaFilter()
file_handler.addFilter(delta_filter)
root_logger.addHandler(file_handler)

# Configure uvicorn access logger to use our handlers too, if desired
# uvicorn_access_logger = logging.getLogger("uvicorn.access")
# uvicorn_access_logger.handlers = root_logger.handlers
# uvicorn_access_logger.setLevel(logging.INFO) # Or whatever level you prefer
# uvicorn_access_logger.propagate = False

# uvicorn_error_logger = logging.getLogger("uvicorn.error")
# uvicorn_error_logger.handlers = root_logger.handlers
# # Send uvicorn errors to our file log as well
# uvicorn_error_logger.propagate = False


logger = logging.getLogger(__name__)  # For specific use in this file, will inherit root config

# --- End Centralized Logger Configuration ---


# --- Custom Exception Handler for Validation Errors --- #
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Log the detailed validation errors
    error_details = (
        f"Validation error for request {request.method} {request.url.path}: {exc.errors()}"
    )
    logger.error(error_details)  # Re-enable logger call
    # print(f"STDERR_DEBUG: {error_details}", file=sys.stderr) # Remove direct print
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

    # Connect Redis client (if it needs explicit connection)
    # await redis_client.connect() # Example if needed

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

    # Disconnect Redis client (if it needs explicit disconnection)
    # await redis_client.disconnect() # Example if needed
    logger.info("Application shutdown complete.")


logging.getLogger("uvicorn.error").setLevel(logging.DEBUG)
# --- FastAPI App Initialization --- #
app = FastAPI(
    title="Plane Guessing Game API",
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
    return {"message": "Welcome to the Plane Guessing Game API!"}


@app.get("/healthz", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, str]:
    """Health check endpoint to verify service status."""
    # TODO: Add checks for Redis connection?
    return {"status": "ok"}


# --- Routers & WebSocket --- #
app.include_router(rooms.router)
app.include_router(logging_routes.router)

# Note: rooms.router already defines the WebSocket endpoint.
# Explicitly adding it again with add_api_websocket_route might cause issues
# unless the router's definition is removed or handled carefully.
# Let's rely on the router inclusion for now.
# app.add_api_websocket_route(
#     path="/ws/{room_code}/{nickname}",
#     endpoint=websocket_endpoint, # Make sure this is correctly imported/defined
#     name="websocket_endpoint_root",
# )


# --- Optional Direct Execution --- #
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)
