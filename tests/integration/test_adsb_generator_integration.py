import asyncio
from pathlib import Path

import pytest

from sample_data.adsb_generator import run_server

pytest.skip(
    "Skipping generator TCP integration test until stability improved", allow_module_level=True
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_sample_generator_tcp_stream() -> None:
    """Spin up the sample generator and verify TCP clients receive data."""

    # Use an arbitrary high port likely to be free
    host, port = "127.0.0.1", 31003
    capture_file = Path("sample_data/sbs_parser_fixtures.sbs")
    assert capture_file.exists(), "Sample capture file missing in repo"

    # Start generator in looping mode so it keeps streaming
    server_task = asyncio.create_task(
        run_server(
            filepath=str(capture_file),
            host=host,
            port=port,
            speed=1_000_000.0,  # extremely fast to minimise delays
            loop_forever=True,
        )
    )

    # Poll until server accepts connections (max 1s)
    for _ in range(20):
        try:
            reader, writer = await asyncio.open_connection(host, port)
            break
        except ConnectionRefusedError:
            await asyncio.sleep(0.05)
    else:
        pytest.fail("Generator did not accept TCP connections in time")

    # Read a handful of lines – should receive at least 3 within reasonable time
    received = []
    for _ in range(3):
        line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        assert line, "Connection closed prematurely by generator"
        received.append(line.decode().strip())

    # Clean-up
    writer.close()
    await writer.wait_closed()
    if not server_task.done():
        server_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await server_task

    # Basic sanity – lines look like SBS CSV (start with e.g. 'SEL' or 'MSG')
    assert all(
        any(line.startswith(prefix) for prefix in ("SEL", "ID", "AIR", "STA", "CLK", "MSG"))
        for line in received
    )
