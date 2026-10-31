"""The only code that talks to FlightAware AeroAPI.

Every request first reserves its worst case (``max_pages`` result sets) with
:class:`AeroApiBudget`; a denied reservation means no request is sent. Errors
are never retried here: the board refresher decides when to try again.
"""

import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

import httpx

from backend.ingest.aeroapi_budget import AeroApiBudget, BudgetDenial, BudgetGrant
from backend.ingest.enrichment_config import COST_PER_RESULT_SET_USD

logger = logging.getLogger(__name__)

AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
RATE_LIMITED_PAUSE_SECONDS = 120
AUTH_FAILURE_PAUSE_SECONDS = 3600


class BoardEndpoint(StrEnum):
    """Airport board endpoints; each response lists rows under its own name."""

    SCHEDULED_ARRIVALS = "scheduled_arrivals"
    SCHEDULED_DEPARTURES = "scheduled_departures"
    DEPARTURES = "departures"


class FetchFailure(StrEnum):
    """Why a board fetch produced no rows (budget denials are reported separately)."""

    PAUSED = "paused"
    HTTP_ERROR = "http_error"
    TRANSPORT_ERROR = "transport_error"
    BAD_RESPONSE = "bad_response"


@dataclass(frozen=True)
class BoardPage:
    """Rows from one board request; ``truncated`` means more pages were available."""

    rows: list[object]
    truncated: bool


def format_aeroapi_time(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


class AeroApiClient:
    """Budgeted access to one airport's AeroAPI boards."""

    def __init__(
        self,
        api_key: str,
        budget: AeroApiBudget,
        airport_icao: str,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._budget = budget
        self._airport_icao = airport_icao
        self._clock = clock
        self._paused_until = 0.0
        self._http = httpx.AsyncClient(
            base_url=AEROAPI_BASE_URL,
            headers={"x-apikey": api_key, "accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            transport=transport,
        )
        self.result_sets_by_endpoint: Counter[str] = Counter()

    async def fetch_board(
        self, endpoint: BoardEndpoint, start: float, end: float, max_pages: int
    ) -> BoardPage | BudgetDenial | FetchFailure:
        """Fetch up to ``max_pages`` of ``endpoint`` for flights between ``start`` and ``end``."""
        if self._clock() < self._paused_until:
            return FetchFailure.PAUSED

        grant = await self._budget.reserve(endpoint.value, max_pages)
        if isinstance(grant, BudgetDenial):
            return grant
        self.result_sets_by_endpoint[endpoint.value] += max_pages

        try:
            response = await self._http.get(
                f"/airports/{self._airport_icao}/flights/{endpoint.value}",
                params={
                    "start": format_aeroapi_time(start),
                    "end": format_aeroapi_time(end),
                    "max_pages": max_pages,
                },
            )
        except httpx.HTTPError as e:
            # The request may still have been billed, so it is logged like any other.
            self._log_usage(endpoint, "-", "-", max_pages, grant)
            logger.warning("AeroAPI %s request failed: %s", endpoint.value, type(e).__name__)
            return FetchFailure.TRANSPORT_ERROR

        body = _json_object(response) if response.status_code == 200 else None
        pages = body.get("num_pages") if body else "-"
        self._log_usage(endpoint, response.status_code, pages, max_pages, grant)

        if response.status_code == 429:
            self._pause(RATE_LIMITED_PAUSE_SECONDS)
            logger.warning("AeroAPI rate limited; pausing %ds", RATE_LIMITED_PAUSE_SECONDS)
            return FetchFailure.HTTP_ERROR
        if response.status_code in (401, 403):
            self._pause(AUTH_FAILURE_PAUSE_SECONDS)
            logger.error(
                "AeroAPI rejected the API key (HTTP %d); pausing %ds. Check FLIGHTAWARE_API_KEY.",
                response.status_code,
                AUTH_FAILURE_PAUSE_SECONDS,
            )
            return FetchFailure.HTTP_ERROR
        if response.status_code != 200:
            return FetchFailure.HTTP_ERROR

        rows = body.get(endpoint.value) if body else None
        if not isinstance(rows, list):
            logger.warning("AeroAPI %s response had no %r list", endpoint.value, endpoint.value)
            return FetchFailure.BAD_RESPONSE
        links = body.get("links")
        truncated = isinstance(links, dict) and bool(links.get("next"))
        return BoardPage(rows=rows, truncated=truncated)

    def _log_usage(
        self,
        endpoint: BoardEndpoint,
        status: object,
        pages: object,
        reserved: int,
        grant: BudgetGrant,
    ) -> None:
        """One INFO line per sent request, to compare with the FlightAware usage page."""
        logger.info(
            "AeroAPI %s status=%s pages=%s reserved=%d | today %d/%d result sets ($%s) | "
            "since start %s",
            endpoint.value,
            status,
            pages,
            reserved,
            grant.day_total,
            grant.daily_cap,
            grant.day_total * COST_PER_RESULT_SET_USD,
            dict(self.result_sets_by_endpoint),
        )

    def _pause(self, seconds: float) -> None:
        self._paused_until = max(self._paused_until, self._clock() + seconds)


def _json_object(response: httpx.Response) -> dict | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None
