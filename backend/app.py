"""Main FastAPI application for the Plane Guessing Game backend."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

from fastapi import FastAPI, status

from backend.routes import rooms  # Import the rooms router
from backend.routes.rooms import manager as connection_manager

# Explicitly import endpoint for add_api_websocket_route if needed, but router usually handles this.
# from backend.routes.rooms import websocket_endpoint
from backend.services.broadcast import broadcast_plane_updates
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

# --- Global State / Dependencies --- #
# Initialize outside lifespan for potential direct access if needed,
# but manage connections within lifespan.
# TODO: Review if global instances are the best approach vs. dependency injection.
redis_client = RedisClient()  # Assumes RedisClient() handles connection setup internally or lazily
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


# --- FastAPI App Initialization --- #
app = FastAPI(
    title="Plane Guessing Game API",
    description="API for managing game rooms, players, and flight data.",
    version="0.1.0",
    lifespan=lifespan,  # Register the lifespan context manager
)


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
