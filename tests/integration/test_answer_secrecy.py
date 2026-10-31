"""No message before roundResult names a round's answer (#156).

Each test plays over real WebSockets against the live backend and records every
frame a client receives, exactly as sent. Until roundResult, no frame may name
the secret end of any plane's route, in either its ICAO or its IATA form, and
an overflight may name neither end. That holds for clients that reconnect or
join mid-round too. roundResult is the reveal, so a skipped round's answer
never appears at all.

Runs against a live backend and real Redis; see tests/README.md.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Callable, Iterable

import pytest
import redis.asyncio as redis
from fastapi import status
from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession, aconnect_ws

from backend.schemas.core import ScoringMode
from backend.schemas.ws import ErrorCode
from backend.utils.airport_db import resolve_airport

from .planes import seed_plane

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

Frame = dict[str, Any]

DEPARTURE = ("dep156", "KBOS", "KDEN")  # Players guess the destination: KDEN
ARRIVAL = ("arr156", "KMSP", "KBOS")  # Players guess the origin: KMSP
OVERFLIGHT = ("ovr156", "KSEA", "KMIA")  # Not playable; neither end may be shown
SECRET_AIRPORTS = ("KDEN", "KMSP", "KSEA", "KMIA")

DELTA_TIMEOUT_SECONDS = 12.0
REPLY_TIMEOUT_SECONDS = 5.0


class FrameRecorder:
    """Reads a client's frames in arrival order, keeping each one as sent on the wire."""

    def __init__(self, ws: AsyncWebSocketSession) -> None:
        self.ws = ws
        self.frames: list[str] = []

    async def wait_for(
        self, matches: Callable[[Frame], bool], timeout: float = REPLY_TIMEOUT_SECONDS
    ) -> Frame:
        """Record frames until one ``matches``; answer server pings on the way."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise AssertionError(f"Timed out after {timeout}s; last frames: {self.frames[-3:]}")
            text = await self.ws.receive_text(timeout=remaining)
            self.frames.append(text)
            frame = json.loads(text)
            if frame["type"] == "ping":
                await self.ws.send_json({"type": "pong", "payload": frame.get("payload") or {}})
            if matches(frame):
                return frame

    async def wait_for_type(self, *message_types: str) -> Frame:
        return await self.wait_for(lambda frame: frame["type"] in message_types)

    async def wait_for_planes(self, hexes: Iterable[str]) -> dict[str, Frame]:
        """Record deltas until all of ``hexes`` have been sent; return each plane as last sent."""
        wanted = set(hexes)
        seen: dict[str, Frame] = {}

        def collect(frame: Frame) -> bool:
            if frame["type"] == "delta":
                for plane in (frame["payload"].get("planes") or {}).get("updated", []):
                    seen[plane["hex_ident"]] = plane
            return wanted.issubset(seen)

        await self.wait_for(collect, timeout=DELTA_TIMEOUT_SECONDS)
        return seen

    def frames_before(self, message_type: str) -> list[str]:
        for index, text in enumerate(self.frames):
            if json.loads(text)["type"] == message_type:
                return self.frames[:index]
        raise AssertionError(f"No {message_type} frame was recorded")


def _code_forms(icao: str) -> tuple[str, ...]:
    airport = resolve_airport(icao)
    assert airport is not None and airport.iata, f"{icao} must have an IATA code for this test"
    return airport.icao, airport.iata


def _frames_naming(frames: list[str], airports: Iterable[str]) -> list[str]:
    """Frames that name any of ``airports`` by ICAO or IATA code."""
    patterns = [
        re.compile(rf"\b{re.escape(code)}\b", re.IGNORECASE)
        for icao in airports
        for code in _code_forms(icao)
    ]
    return [text for text in frames if any(pattern.search(text) for pattern in patterns)]


def _is_skip_delta(frame: Frame) -> bool:
    round_update = frame["payload"].get("round") if frame["type"] == "delta" else None
    return (round_update or {}).get("state") == "waiting_for_selection"


async def _seed_routes(
    real_redis: redis.Redis, *routes: tuple[str, str | None, str | None]
) -> None:
    for hex_ident, origin, destination in routes:
        await seed_plane(real_redis, hex_ident, origin=origin, destination=destination)


def _hinted_selection(hint: Frame) -> tuple[bool, str | None]:
    """What a route hint promises selectPlane does: accept the plane, and for which end."""
    return hint["eligible"], hint["guess_direction"] if hint["eligible"] else None


def _selection_made(reply: Frame) -> tuple[bool, str | None]:
    """What selectPlane did: accept the plane, and for which end."""
    if reply["type"] == "planeSelectedConfirm":
        return True, reply["payload"]["guess_direction"]
    return False, None


async def _join(client: AsyncClient, room_code: str, nickname: str) -> None:
    joined = await client.post(f"/api/v0/rooms/{room_code}/join", json={"nickname": nickname})
    assert joined.status_code == status.HTTP_200_OK


async def _create_room(client: AsyncClient, host: str, *players: str) -> str:
    created = await client.post(
        "/api/v0/rooms",
        json={"host_nickname": host, "mode": ScoringMode.EXACT.value, "round_timeout_seconds": 30},
    )
    assert created.status_code == status.HTTP_201_CREATED
    room_code = created.json()["room_code"]
    for nickname in players:
        await _join(client, room_code, nickname)
    return room_code


def _ws_path(room_code: str, nickname: str) -> str:
    return f"/api/v0/rooms/ws/{room_code}/{nickname}"


def _is_player_left(nickname: str) -> Callable[[Frame], bool]:
    return lambda frame: frame["type"] == "playerLeft" and frame["payload"]["nickname"] == nickname


async def _send(ws: AsyncWebSocketSession, message_type: str, payload: dict[str, Any]) -> None:
    await ws.send_json({"type": message_type, "payload": payload})


async def test_multiplayer_round_names_the_answer_only_in_round_result(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    hexes = [DEPARTURE[0], ARRIVAL[0], OVERFLIGHT[0]]
    room_code = await _create_room(integration_client, "SecretHost", "SecretGuest")

    async with aconnect_ws(_ws_path(room_code, "SecretHost"), client=integration_client) as host_ws:
        host = FrameRecorder(host_ws)
        await host.wait_for_type("stateSync")

        async with aconnect_ws(
            _ws_path(room_code, "SecretGuest"), client=integration_client
        ) as first_guest_ws:
            first_guest = FrameRecorder(first_guest_ws)
            await first_guest.wait_for_type("stateSync")
            await host.wait_for_type("playerJoined")

            await _seed_routes(real_redis, DEPARTURE, ARRIVAL, OVERFLIGHT)
            await host.wait_for_planes(hexes)
            await first_guest.wait_for_planes(hexes)

            await _send(host_ws, "selectPlane", {"hex": DEPARTURE[0]})
            await host.wait_for_type("planeSelectedConfirm")
            await _send(host_ws, "startRound", {})
            await host.wait_for_type("roundStart")
            await first_guest.wait_for_type("roundStart")

        # Mid-round, the guest reconnects and a third player joins: both get a fresh stateSync.
        await host.wait_for(_is_player_left("SecretGuest"))
        await _join(integration_client, room_code, "LateGuest")
        async with (
            aconnect_ws(_ws_path(room_code, "SecretGuest"), client=integration_client) as guest_ws,
            aconnect_ws(_ws_path(room_code, "LateGuest"), client=integration_client) as late_ws,
        ):
            guest, late = FrameRecorder(guest_ws), FrameRecorder(late_ws)
            await guest.wait_for_type("stateSync")
            await late.wait_for_type("stateSync")

            # The planes move on during the round, so every client gets mid-round deltas too.
            await _seed_routes(real_redis, DEPARTURE, ARRIVAL, OVERFLIGHT)
            for recorder in (host, guest, late):
                await recorder.wait_for_planes(hexes)

            await _send(guest_ws, "guess", {"airport_code": "ORD"})
            await _send(late_ws, "guess", {"airport_code": "SFO"})
            await _send(host_ws, "guess", {"airport_code": "ATL"})
            host_result = await host.wait_for_type("roundResult")
            await guest.wait_for_type("roundResult")
            await late.wait_for_type("roundResult")

    leaked = {
        "host": _frames_naming(host.frames_before("roundResult"), SECRET_AIRPORTS),
        "guest before reconnecting": _frames_naming(first_guest.frames, SECRET_AIRPORTS),
        "guest after reconnecting": _frames_naming(
            guest.frames_before("roundResult"), SECRET_AIRPORTS
        ),
        "late joiner": _frames_naming(late.frames_before("roundResult"), SECRET_AIRPORTS),
    }
    assert leaked == {client: [] for client in leaked}
    # The detector does see the answer once it is revealed.
    assert _frames_naming([json.dumps(host_result)], ["KDEN"]) != []
    assert host_result["payload"]["hex"] == DEPARTURE[0]


async def test_skipped_round_never_names_its_answer(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    room_code = await _create_room(integration_client, "SkipHost", "SkipGuest")

    async with (
        aconnect_ws(_ws_path(room_code, "SkipHost"), client=integration_client) as host_ws,
        aconnect_ws(_ws_path(room_code, "SkipGuest"), client=integration_client) as guest_ws,
    ):
        host, guest = FrameRecorder(host_ws), FrameRecorder(guest_ws)
        await host.wait_for_type("stateSync")
        await guest.wait_for_type("stateSync")
        await host.wait_for_type("playerJoined")

        await _seed_routes(real_redis, DEPARTURE, ARRIVAL)
        await host.wait_for_planes([DEPARTURE[0], ARRIVAL[0]])
        await guest.wait_for_planes([DEPARTURE[0], ARRIVAL[0]])

        # Round 1 on the arrival is skipped, so its answer (KMSP) is never revealed.
        await _send(host_ws, "selectPlane", {"hex": ARRIVAL[0]})
        await host.wait_for_type("planeSelectedConfirm")
        await _send(host_ws, "startRound", {})
        await host.wait_for_type("roundStart")
        await guest.wait_for_type("roundStart")
        await _send(host_ws, "skipRound", {})
        await host.wait_for(_is_skip_delta)
        await guest.wait_for(_is_skip_delta)

        # Round 2 on the departure is played through its reveal.
        await _send(host_ws, "selectPlane", {"hex": DEPARTURE[0]})
        await host.wait_for_type("planeSelectedConfirm")
        await _send(host_ws, "startRound", {})
        await host.wait_for_type("roundStart")
        await guest.wait_for_type("roundStart")
        await _send(guest_ws, "guess", {"airport_code": "ORD"})
        await _send(host_ws, "guess", {"airport_code": "ATL"})
        await host.wait_for_type("roundResult")
        await guest.wait_for_type("roundResult")

    leaked = {
        "host": _frames_naming(host.frames, [ARRIVAL[1]]),
        "guest": _frames_naming(guest.frames, [ARRIVAL[1]]),
    }
    assert leaked == {"host": [], "guest": []}


async def test_solo_round_names_the_answer_only_in_round_result(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    joined = await integration_client.post("/api/v0/rooms/solo/join", json={"nickname": "Solo"})
    assert joined.status_code == status.HTTP_200_OK

    async with aconnect_ws(joined.json()["ws_url"], client=integration_client) as ws:
        solo = FrameRecorder(ws)
        await solo.wait_for_type("stateSync")
        await _seed_routes(real_redis, ARRIVAL, OVERFLIGHT)
        await solo.wait_for_planes([ARRIVAL[0], OVERFLIGHT[0]])

        await _send(ws, "selectPlane", {"hex": ARRIVAL[0]})
        await solo.wait_for_type("planeSelectedConfirm")
        await _send(ws, "startRound", {})
        await solo.wait_for_type("roundStart")
        await _send(ws, "guess", {"airport_code": "ORD"})
        result = await solo.wait_for_type("roundResult")
        await _send(ws, "leave", {})

    assert _frames_naming(solo.frames_before("roundResult"), SECRET_AIRPORTS) == []
    assert (result["payload"]["hex"], result["payload"]["results"][0]["correct_code"]) == (
        ARRIVAL[0],
        "KMSP",
    )


async def test_route_hint_eligibility_matches_what_select_plane_accepts(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    routes = [
        DEPARTURE,
        ARRIVAL,
        OVERFLIGHT,
        ("unk156", "KBOS", "KMVY"),  # Answer airport is not in the dataset
        ("mis156", "KBOS", None),  # Answer end unknown
    ]
    room_code = await _create_room(integration_client, "ParityHost")

    async with aconnect_ws(_ws_path(room_code, "ParityHost"), client=integration_client) as ws:
        host = FrameRecorder(ws)
        await host.wait_for_type("stateSync")
        await _seed_routes(real_redis, *routes)
        planes = await host.wait_for_planes(hex_ident for hex_ident, _, _ in routes)

        replies: dict[str, Frame] = {}
        for hex_ident, _, _ in routes:
            await _send(ws, "selectPlane", {"hex": hex_ident})
            replies[hex_ident] = await host.wait_for_type("planeSelectedConfirm", "error")

    hinted = {
        hex_ident: _hinted_selection(planes[hex_ident]["route_hint"]) for hex_ident in replies
    }
    selected = {hex_ident: _selection_made(reply) for hex_ident, reply in replies.items()}
    rejections = {
        hex_ident: reply["payload"]["code"] if reply["type"] == "error" else None
        for hex_ident, reply in replies.items()
    }
    assert hinted == selected
    # Each rejection is the route's own reason, not an unrelated failure such as PLANE_NOT_FOUND.
    assert rejections == {
        DEPARTURE[0]: None,
        ARRIVAL[0]: None,
        OVERFLIGHT[0]: ErrorCode.INVALID_PLANE_SELECTION.value,
        "unk156": ErrorCode.PLANE_DATA_INCOMPLETE_FOR_GUESS.value,
        "mis156": ErrorCode.INTERNAL_SERVER_ERROR.value,
    }
