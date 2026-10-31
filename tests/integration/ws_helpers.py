"""Order-tolerant WebSocket waits for integration tests.

The backend interleaves frames a test did not ask for with the replies it is waiting for: a
``delta`` every second once planes exist, ``ping`` heartbeats, and broadcasts caused by other
clients. Reading "the next frame" therefore flakes. These helpers read frames until the expected
ones arrive, answer server pings on the way, and discard everything else.

Because unmatched frames are discarded, messages that the server sends together (for example
``playerLeft`` and ``newHost`` after a host leaves) must be collected in one
``wait_for_messages`` call rather than in two consecutive waits.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from httpx_ws import AsyncWebSocketSession

Frame = dict[str, Any]

DEFAULT_TIMEOUT_SECONDS = 5.0
UNMATCHED_FRAMES_IN_ERROR = 5


@dataclass(frozen=True)
class Expected:
    """A frame of ``message_type`` whose payload contains ``payload`` and satisfies ``where``."""

    message_type: str
    payload: Mapping[str, object] = field(default_factory=dict)
    where: Callable[[Frame], bool] | None = None

    def matches(self, frame: Frame) -> bool:
        if frame.get("type") != self.message_type:
            return False
        frame_payload = frame.get("payload")
        if not isinstance(frame_payload, dict):
            frame_payload = {}
        if any(frame_payload.get(key) != value for key, value in self.payload.items()):
            return False
        return self.where is None or self.where(frame)

    def describe(self) -> str:
        details = ", ".join(f"{key}={value!r}" for key, value in self.payload.items())
        predicate = " + where" if self.where is not None else ""
        return f"{self.message_type}({details}){predicate}"


async def wait_for_messages(
    ws: AsyncWebSocketSession,
    *expected: Expected,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[Frame]:
    """Wait until every ``expected`` frame has arrived, in any order.

    Returns the matching frames in the order of ``expected``. Raises ``AssertionError`` naming
    the missing messages and the last few unmatched frames when ``timeout`` elapses first.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    pending = dict(enumerate(expected))
    matched: dict[int, Frame] = {}
    unmatched: deque[Frame] = deque(maxlen=UNMATCHED_FRAMES_IN_ERROR)

    while pending:
        remaining = deadline - loop.time()
        try:
            if remaining <= 0:
                raise TimeoutError
            frame = await ws.receive_json(timeout=remaining)
        except TimeoutError:
            missing = ", ".join(item.describe() for item in pending.values())
            raise AssertionError(
                f"Timed out after {timeout}s waiting for: {missing}. "
                f"Last unmatched frames: {list(unmatched)}"
            ) from None

        index = next((i for i, item in pending.items() if item.matches(frame)), None)
        if index is not None:
            matched[index] = frame
            del pending[index]
            continue
        if frame.get("type") == "ping":
            await ws.send_json({"type": "pong", "payload": frame.get("payload") or {}})
            continue
        unmatched.append(frame)

    return [matched[i] for i in range(len(expected))]


async def wait_for_message(
    ws: AsyncWebSocketSession,
    message_type: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    where: Callable[[Frame], bool] | None = None,
    **payload: object,
) -> Frame:
    """Wait for one frame of ``message_type`` whose payload contains ``payload``."""
    (frame,) = await wait_for_messages(ws, Expected(message_type, payload, where), timeout=timeout)
    return frame
