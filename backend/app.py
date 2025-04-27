"""Main FastAPI application for the Plane Guessing Game backend."""

from typing import Dict

from fastapi import FastAPI, status

from backend.routes import rooms  # Import the rooms router
from backend.routes.rooms import websocket_endpoint  # noqa: E402, after import section

app = FastAPI(
    title="Plane Guessing Game API",
    description="API for managing game rooms, players, and flight data.",
    version="0.1.0",  # Corresponds to pyproject.toml version
)


@app.get("/")
async def read_root() -> Dict[str, str]:
    """Root endpoint providing a basic welcome message."""
    return {"message": "Welcome to the Plane Guessing Game API!"}


@app.get("/healthz", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, str]:
    """Health check endpoint to verify service status."""
    return {"status": "ok"}


# Include routers
app.include_router(rooms.router)


# Register top-level WebSocket route per PRD (alias for rooms.websocket route)
app.add_api_websocket_route(
    path="/ws/{room_code}/{nickname}",
    endpoint=websocket_endpoint,
    name="websocket_endpoint_root",
)


# Further routers and configuration will be added here.


# Optional: Add uvicorn entry point logic if desired for direct execution
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)
