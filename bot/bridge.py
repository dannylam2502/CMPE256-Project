from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional, Set

import websockets

log = logging.getLogger(__name__)


class UIBridge:
    """Cross-loop-safe bridge between the bot and the Svelte UI.

    poke-env's PSClient may process incoming battle messages on a different
    asyncio loop than the one where the WebSocket server runs. This bridge
    carefully creates futures on the caller's loop and routes outbound sends
    through the server's loop.
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self._clients: Set[Any] = set()
        self._server: Any = None
        # The loop the WS server (and per-client send machinery) lives on.
        self._handler_loop: Optional[asyncio.AbstractEventLoop] = None

        self._pending_decision: Optional[asyncio.Future] = None
        self._pending_decision_loop: Optional[asyncio.AbstractEventLoop] = None
        self._client_wait_future: Optional[asyncio.Future] = None
        self._client_wait_loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self) -> None:
        self._handler_loop = asyncio.get_running_loop()
        self._server = await websockets.serve(self._handle, self.host, self.port)
        log.info("UI bridge listening on ws://%s:%d", self.host, self.port)

    async def wait_for_client(self) -> None:
        if self._clients:
            return
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._client_wait_future = future
        self._client_wait_loop = loop
        await future

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def broadcast(self, payload: dict) -> None:
        """Send a snapshot to every UI client. Safe to call from any loop."""
        if not self._clients:
            return
        message = json.dumps({"type": "update", "payload": payload}, default=str)

        caller_loop = asyncio.get_running_loop()
        if caller_loop is self._handler_loop:
            # Same loop — send directly.
            await self._do_broadcast(message)
        else:
            # Different loop — schedule on the handler loop and await the result
            # via a wrapped future on the caller's loop.
            assert self._handler_loop is not None
            cf = asyncio.run_coroutine_threadsafe(
                self._do_broadcast(message), self._handler_loop
            )
            await asyncio.wrap_future(cf)

    async def _do_broadcast(self, message: str) -> None:
        sent = 0
        for c in list(self._clients):
            try:
                await c.send(message)
                sent += 1
            except websockets.ConnectionClosed:
                self._clients.discard(c)
            except Exception:
                log.exception("send failed; dropping client")
                self._clients.discard(c)
        log.debug("broadcast sent to %d/%d clients", sent, len(self._clients))

    def has_clients(self) -> bool:
        return len(self._clients) > 0

    def await_user_decision(self) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        if self._pending_decision and not self._pending_decision.done():
            old = self._pending_decision
            old_loop = self._pending_decision_loop
            if old_loop is not None and old_loop is not loop:
                old_loop.call_soon_threadsafe(old.cancel)
            else:
                old.cancel()
        future = loop.create_future()
        self._pending_decision = future
        self._pending_decision_loop = loop
        return future

    async def _handle(self, client: Any) -> None:
        self._clients.add(client)
        log.info("UI client connected (%d total)", len(self._clients))

        if self._client_wait_future and not self._client_wait_future.done():
            cwl = self._client_wait_loop
            if cwl is not None:
                cwl.call_soon_threadsafe(self._client_wait_future.set_result, None)

        try:
            async for raw in client:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "action":
                    payload = msg.get("payload")
                    if (
                        payload
                        and self._pending_decision is not None
                        and not self._pending_decision.done()
                    ):
                        pd = self._pending_decision
                        pdl = self._pending_decision_loop
                        if pdl is not None:
                            pdl.call_soon_threadsafe(pd.set_result, payload)
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(client)
            log.info("UI client disconnected (%d remaining)", len(self._clients))
