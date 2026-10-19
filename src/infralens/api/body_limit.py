"""Bound the finance POST before the route parses JSON or runs the cost identity.

Application-level controls are defense in depth. A public reverse proxy or gateway
must still enforce request size, throttling, concurrency, and timeouts. This
process does not install proxy-header middleware and does not trust
``X-Forwarded-*`` headers. A declared ``Content-Length`` that is already too
large is rejected without reading the body. Missing, chunked, or understated
lengths are still capped by counting the bytes the ASGI server actually
delivers. Content-encoding expansion, if a proxy decompresses a body before it
reaches this process, is a gateway concern.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from infralens.api.schemas import FINANCE_MAX_BODY_BYTES

_FINANCE_PATH = "/api/v1/finance/scenarios"
_TOO_LARGE = {
    "code": "request_too_large",
    "message": f"The finance request body exceeds {FINANCE_MAX_BODY_BYTES} bytes.",
    "artifact_id": None,
    "field": None,
}


class FinanceBodyLimit:
    """Reject an oversized finance body with HTTP 413 before the route runs."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        if scope.get("path") != _FINANCE_PATH:
            await self.app(scope, receive, send)
            return
        declared = _declared_length(scope)
        if declared is not None and declared > FINANCE_MAX_BODY_BYTES:
            await _send_too_large(send)
            return
        payload, too_large = await _read_limited(receive)
        if too_large:
            await _send_too_large(send)
            return
        await self.app(scope, _replay(payload), send)


def _declared_length(scope: dict) -> int | None:
    """Return a usable Content-Length, ignoring a malformed or forwarded substitute."""

    lengths: list[int] = []
    for key, value in scope.get("headers", []):
        if key.lower() != b"content-length":
            continue
        try:
            lengths.append(int(value.decode("ascii")))
        except (UnicodeError, ValueError):
            return None
    if not lengths:
        return None
    return max(lengths)


async def _read_limited(receive: Callable) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return b"".join(chunks), False
        if message["type"] != "http.request":
            continue
        piece = message.get("body", b"")
        total += len(piece)
        if total > FINANCE_MAX_BODY_BYTES:
            return b"", True
        chunks.append(piece)
        if not message.get("more_body", False):
            return b"".join(chunks), False


def _replay(payload: bytes) -> Callable:
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": payload, "more_body": False}

    return receive


async def _send_too_large(send: Callable) -> None:
    body = json.dumps(_TOO_LARGE).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})
