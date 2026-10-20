"""Bound one HTTP request when the private service asks for it.

``--timeout-keep-alive`` only closes an idle connection. It does not stop a
request that is still running. This middleware is the application limit. It is
off unless ``INFRALENS_REQUEST_TIMEOUT_SECONDS`` is set, so the standalone
portable image keeps its current behavior.
"""

from __future__ import annotations

import json
import math
from collections.abc import MutableMapping

import anyio

_MESSAGE = "The request exceeded the time limit."
_MAX_SECONDS = 120.0


def resolve_request_timeout(raw: str | None) -> float | None:
    """Parse a positive timeout of at most 120 seconds, or None when unset."""

    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise ValueError(
            "INFRALENS_REQUEST_TIMEOUT_SECONDS must be a positive number of at most 120."
        ) from exc
    if not math.isfinite(value) or value <= 0 or value > _MAX_SECONDS:
        raise ValueError(
            "INFRALENS_REQUEST_TIMEOUT_SECONDS must be a positive number of at most 120."
        )
    return value


class RequestTimeout:
    """Stop an HTTP request that outlives ``seconds`` and return 504."""

    def __init__(self, app: object, seconds: float) -> None:
        self.app = app
        self.seconds = seconds

    async def __call__(
        self,
        scope: MutableMapping[str, object],
        receive: object,
        send: object,
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)  # type: ignore[operator]
            return
        started = False

        async def observe(message: MutableMapping[str, object]) -> None:
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)  # type: ignore[operator]

        try:
            with anyio.fail_after(self.seconds):
                await self.app(scope, receive, observe)  # type: ignore[operator]
        except TimeoutError:
            if started:
                return
            body = json.dumps(
                {
                    "code": "request_timeout",
                    "message": _MESSAGE,
                    "artifact_id": None,
                    "field": None,
                }
            ).encode()
            with anyio.CancelScope(shield=True):
                await send(  # type: ignore[operator]
                    {
                        "type": "http.response.start",
                        "status": 504,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})  # type: ignore[operator]
