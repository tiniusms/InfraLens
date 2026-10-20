"""Public API errors. Responses name an artifact role, not a filesystem path."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("infralens.api")

ErrorCode = Literal[
    "artifact_missing",
    "validation_error",
    "malformed_vintage",
    "artifact_invalid",
]

ArtifactId = Literal[
    "committed_summary",
    "price_history",
    "holdout_cases",
    "pjm_2025_tables",
    "pjm_2026_tables",
]


class ApiError(Exception):
    """A request failed in a way the client can handle without a traceback."""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        *,
        artifact_id: ArtifactId | None = None,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.artifact_id = artifact_id
        self.field = field

    def body(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "message": self.message,
            "artifact_id": self.artifact_id,
            "field": self.field,
        }


def safe_detail(exc: BaseException) -> str | None:
    """Return one line of an error when it cannot reveal a path or secret."""

    text = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    lowered = text.lower()
    if not text or len(text) > 300:
        return None
    if any(token in text for token in ("/", "\\", "Traceback")):
        return None
    if "api_key" in lowered or "eia_api" in lowered or ".env" in lowered:
        return None
    return text


def _validation_message(exc: RequestValidationError) -> tuple[str, str | None]:
    errors = exc.errors()
    if not errors:
        return "The request is not valid.", None
    first = errors[0]
    message = safe_detail(Exception(str(first.get("msg", "The request is not valid."))))
    loc = [str(part) for part in first.get("loc", ()) if part not in {"body", "query", "path"}]
    field = ".".join(loc) or None
    return message or "The request is not valid.", field


def register_exception_handlers(app: FastAPI) -> None:
    """Map adapter and request errors onto the four public codes."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.info("API request failed with %s", exc.code)
        return JSONResponse(status_code=exc.status_code, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        message, field = _validation_message(exc)
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": message,
                "artifact_id": None,
                "field": field,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.warning("Unhandled API failure: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "code": "artifact_invalid",
                "message": "The server could not complete this request.",
                "artifact_id": None,
                "field": None,
            },
        )
