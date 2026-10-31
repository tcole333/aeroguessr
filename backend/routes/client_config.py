"""GET /api/v0/config: where this install is and how to draw its map."""

from fastapi import APIRouter

from backend.schemas.client_config import ClientConfig
from backend.services.client_config import build_client_config
from backend.settings import get_settings

router = APIRouter(prefix="/api/v0", tags=["config"])


@router.get("/config", response_model=ClientConfig)
async def read_client_config() -> ClientConfig:
    """The receiver's location, the monitored airport, the antenna range and the basemap.

    The frontend reads it once at startup, so one frontend build works at any location.
    Static and public: it holds no secrets and names no route's airports.
    """
    return build_client_config(get_settings())
