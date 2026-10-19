"""FastAPI WebSocket server for edge devices (Raspberry Pi and friends)."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager, suppress
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket

from zeno.config import Settings
from zeno.senses.auth import DeviceAuth, parse_bearer
from zeno.senses.events import DeviceEvent, EventBus, EventKind
from zeno.senses.manager import ConnectionManager, DeviceConnection
from zeno.senses.protocol import (
    CloseCode,
    CommandResult,
    ErrorFrame,
    Hello,
    Ping,
    Pong,
    ProtocolError,
    SensorUpdate,
    Telemetry,
    Welcome,
    parse_inbound,
)

log = logging.getLogger(__name__)


def create_app(
    settings: Settings,
    *,
    auth: DeviceAuth,
    manager: ConnectionManager | None = None,
    bus: EventBus | None = None,
) -> FastAPI:
    manager = manager or ConnectionManager()
    bus = bus or EventBus(settings.event_queue_size)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await bus.start()
        yield
        await manager.close_all()
        await bus.stop()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.manager = manager
    app.state.bus = bus

    @app.websocket("/v1/devices/{device_id}/ws")
    async def device_socket(websocket: WebSocket, device_id: str) -> None:
        await DeviceSession(websocket, device_id, settings, auth, manager, bus).run()

    return app


def server_config(settings: Settings, app: FastAPI) -> uvicorn.Config:
    return uvicorn.Config(
        app,
        host=settings.senses_host,
        port=settings.senses_port,
        # Our own size check answers with an error frame; uvicorn is the hard cap.
        ws_max_size=settings.max_frame_bytes * 2,
        server_header=False,
        proxy_headers=False,
        log_level="info",
    )


class _Disconnected(Exception):
    pass


class DeviceSession:
    def __init__(
        self,
        websocket: WebSocket,
        device: str,
        settings: Settings,
        auth: DeviceAuth,
        manager: ConnectionManager,
        bus: EventBus,
    ) -> None:
        self.ws = websocket
        self.device = device
        self.settings = settings
        self.auth = auth
        self.manager = manager
        self.bus = bus

    async def run(self) -> None:
        if not self._authorised():
            await self.ws.close(code=CloseCode.POLICY)
            return
        await self.ws.accept()
        try:
            hello = await asyncio.wait_for(self._hello(), self.settings.hello_timeout)
        except TimeoutError:
            await self._close(CloseCode.HELLO_TIMEOUT, "No hello received.")
            return
        except (ProtocolError, _Disconnected):
            await self._close(CloseCode.POLICY, "The first frame must be a valid hello.")
            return

        conn = await self.manager.connect(self.device, self.ws, frozenset(hello.capabilities))
        self._publish("connected", {"capabilities": sorted(conn.capabilities)})
        try:
            await self.manager.send(
                conn, Welcome(heartbeat_interval=self.settings.heartbeat_interval)
            )
            await self._serve(conn)
        except Exception:
            log.exception("Device session for %s failed", self.device)
        finally:
            if await self.manager.disconnect(conn):
                self._publish("disconnected", {})

    def _authorised(self) -> bool:
        # Devices never send an Origin header; browsers always do. Refusing it stops
        # a web page open on this PC from talking to the device socket.
        if self.ws.headers.get("origin") is not None:
            return False
        token = parse_bearer(self.ws.headers.get("authorization"))
        return token is not None and self.auth.verify(self.device, token)

    async def _hello(self) -> Hello:
        frame = parse_inbound(await self._receive_text(), max_bytes=self.settings.max_frame_bytes)
        if not isinstance(frame, Hello):
            raise ProtocolError("expected_hello", "The first frame must be hello.")
        return frame

    async def _serve(self, conn: DeviceConnection) -> None:
        tasks = {
            asyncio.create_task(self._listen(conn)),
            asyncio.create_task(self._heartbeat(conn)),
            # Set when the manager drops this connection (e.g. replaced by a
            # reconnect), so a client that never answers the close cannot linger.
            asyncio.create_task(conn.closed.wait()),
        }
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if (error := task.exception()) is not None:
                raise error

    async def _listen(self, conn: DeviceConnection) -> None:
        strikes = 0
        while True:
            try:
                text = await self._receive_text()
            except _Disconnected:
                return
            except ProtocolError as error:
                text, problem = None, error
            self.manager.touch(conn)
            if text is not None:
                try:
                    await self._handle(
                        conn, parse_inbound(text, max_bytes=self.settings.max_frame_bytes)
                    )
                    strikes = 0  # only consecutive bad frames count against a device
                    continue
                except ProtocolError as error:
                    problem = error
            strikes += 1
            await self.manager.send(conn, ErrorFrame(code=problem.code, message=problem.message))
            if strikes >= self.settings.max_invalid_frames:
                await self._close(CloseCode.POLICY, "Too many invalid frames.")
                return

    async def _handle(self, conn: DeviceConnection, frame: Any) -> None:
        if isinstance(frame, Ping):
            await self.manager.send(conn, Pong(id=frame.id))
        elif isinstance(frame, SensorUpdate):
            if frame.sensor not in conn.capabilities:
                raise ProtocolError(
                    "undeclared_capability", f"{frame.sensor} was not declared in hello."
                )
            self._publish(
                "sensor", {"sensor": frame.sensor, "value": frame.value, "unit": frame.unit}
            )
        elif isinstance(frame, Telemetry):
            self._publish("telemetry", {"metrics": dict(frame.metrics)})
        elif isinstance(frame, CommandResult):
            self.manager.resolve(conn, frame)
        elif isinstance(frame, Hello):
            raise ProtocolError("duplicate_hello", "hello is only sent once.")
        # Pong needs nothing beyond the touch() above.

    async def _heartbeat(self, conn: DeviceConnection) -> None:
        while True:
            await asyncio.sleep(self.settings.heartbeat_interval)
            if self.manager.clock() - conn.last_seen > self.settings.heartbeat_timeout:
                await self._close(CloseCode.HEARTBEAT_TIMEOUT, "Heartbeat timed out.")
                return
            await self.manager.send(conn, Ping())

    async def _receive_text(self) -> str:
        message = await self.ws.receive()
        if message["type"] == "websocket.disconnect":
            raise _Disconnected
        text = message.get("text")
        if text is None:
            raise ProtocolError("binary_not_supported", "Send JSON text frames.")
        return str(text)

    async def _close(self, code: CloseCode, reason: str) -> None:
        with suppress(Exception):  # already closed by the other side
            await self.ws.close(code=code, reason=reason)

    def _publish(self, kind: EventKind, data: Mapping[str, Any]) -> None:
        self.bus.publish(DeviceEvent(self.device, kind, data, received_at=time.time()))
