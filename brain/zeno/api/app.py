"""The brain's FastAPI app: status, the chat socket and the device socket."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket

from zeno.api.auth import token_matches
from zeno.api.chat import ChatSession
from zeno.senses.auth import parse_bearer
from zeno.senses.protocol import CloseCode
from zeno.senses.server import device_router

if TYPE_CHECKING:
    from zeno.daemon import ZenoDaemon

TRY_AGAIN_LATER = 1013

MESSAGES = {
    "starting": "Zeno is starting.",
    "ready": "Zeno is ready.",
    "stopping": "Zeno is shutting down.",
    "stopped": "Zeno is not running.",
}


def create_api(daemon: "ZenoDaemon") -> FastAPI:
    """The app's lifespan boots and stops the daemon, so a server never accepts a
    connection before every pillar is up."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await daemon.start()
        try:
            yield
        finally:
            await daemon.stop()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    settings = daemon.settings
    app.include_router(
        device_router(settings, auth=daemon.auth, manager=daemon.devices, bus=daemon.bus)
    )

    @app.get("/v1/status")
    async def status() -> dict[str, Any]:
        ready = daemon.state == "ready"
        return {
            "state": daemon.state,
            "message": daemon.error if daemon.state == "failed" else MESSAGES[daemon.state],
            "model": settings.model_path.name if settings.model_path else None,
            "tools": daemon.services.orchestrator.tool_names() if ready else [],
            "devices": daemon.devices.devices(),
        }

    @app.websocket("/v1/chat/ws")
    async def chat(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        # Browsers always send Origin and WebSockets ignore CORS, so without this
        # any web page open on this PC could talk to (and approve for) the agent.
        if origin is not None and origin not in settings.api_allowed_origins:
            await websocket.close(code=CloseCode.POLICY)
            return
        token = parse_bearer(websocket.headers.get("authorization"))
        if not token_matches(token, daemon.api_token):
            await websocket.close(code=CloseCode.POLICY)
            return
        if daemon.state != "ready":
            await websocket.close(code=TRY_AGAIN_LATER)
            return
        await ChatSession(websocket, daemon.services.orchestrator, settings).run()

    return app
