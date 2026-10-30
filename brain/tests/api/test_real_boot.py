"""Integration: the whole brain on real pillars, served by real uvicorn.

The chat model is the tiny random-weight GGUF (also used for embeddings), memory is
a persistent ChromaDB in a temp folder, and clients talk over real sockets.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from websockets.asyncio.client import connect

from tests.api.conftest import brain_settings
from zeno.daemon import ZenoDaemon


async def test_boots_real_pillars_and_answers_over_websockets(
    tiny_gguf: Path, tmp_path: Path
) -> None:
    settings = brain_settings(
        tmp_path,
        model_path=tiny_gguf,
        # The tiny model tokenizes byte by byte, so the tool list needs a big window.
        context_size=16384,
        max_tokens=48,
        agent_max_steps=2,
        senses_port=0,
    )
    daemon = ZenoDaemon(settings)
    serving = asyncio.create_task(daemon.serve())
    try:
        port = await asyncio.wait_for(daemon.wait_until_serving(), timeout=20)
        assert daemon.state == "ready"
        base = f"127.0.0.1:{port}"

        async with httpx.AsyncClient() as http:
            status = (await http.get(f"http://{base}/v1/status")).json()
        assert status["state"] == "ready"
        assert status["model"] == tiny_gguf.name

        headers = {"Authorization": f"Bearer {daemon.api_token}"}
        async with connect(f"ws://{base}/v1/chat/ws", additional_headers=headers) as ws:
            assert json.loads(await ws.recv())["type"] == "ready"
            await ws.send(json.dumps({"type": "chat", "id": "t1", "text": "hello"}))
            frames: list[dict[str, Any]] = []
            while not frames or frames[-1]["type"] != "done":
                frames.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=20)))
        # Random weights rarely finish a step; what matters is a clean end to the turn.
        assert frames[-1]["outcome"] in {"answered", "step_limit", "loop_detected"}

        token = daemon.services.auth.register("pi-real")
        device_headers = {"Authorization": f"Bearer {token}"}
        async with connect(
            f"ws://{base}/v1/devices/pi-real/ws", additional_headers=device_headers
        ) as device:
            await device.send(json.dumps({"v": 1, "id": "h", "type": "hello", "capabilities": []}))
            assert json.loads(await device.recv())["type"] == "welcome"
    finally:
        daemon.shutdown()
        await asyncio.wait_for(serving, timeout=10)
    assert daemon.state == "stopped"
    assert (settings.memory_dir / "chroma.sqlite3").is_file()
