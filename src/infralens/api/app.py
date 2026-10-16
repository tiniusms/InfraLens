"""FastAPI application for the read-only InfraLens adapter.

Run from a checkout with the optional api extra installed:

    uvicorn infralens.api.app:app

Set ``INFRALENS_CORS_ORIGINS`` to a comma-separated allowlist. A wildcard
origin is rejected. ``INFRALENS_ROOT`` overrides the repository root.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from infralens.api.errors import register_exception_handlers
from infralens.api.readers import (
    Runtime,
    pjm_catalog,
    pjm_screen,
    price_scenarios,
    read_cases,
    read_evaluation,
    read_history,
    read_holdout,
    status_response,
)
from infralens.api.schemas import (
    ErrorResponse,
    EvaluationSummaryResponse,
    FinanceRequest,
    FinanceResponse,
    HistoryResponse,
    HoldoutCasesResponse,
    HoldoutResponse,
    PjmCatalogResponse,
    PjmScreenResponse,
    StatusResponse,
)
from infralens.data import repository_root
from infralens.demo.eia_views import DEMO_STATES
from infralens.demo.foundation import default_artifact_paths

_STATE_QUERY = "^(" + "|".join(DEMO_STATES) + ")$"

_ERROR_RESPONSES = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}


def create_app(
    *,
    root: Path | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Build an application bound to one repository root and one CORS allowlist."""

    app = FastAPI(
        title="InfraLens API",
        version="v1",
        description=(
            "Read-only adapter over the frozen EIA evaluation, observed price history, "
            "annual energy-cost identity, and PJM zone-year screening. "
            "It does not train or score a model."
        ),
    )
    app.state.runtime = Runtime(root=_resolve_root(root))
    register_exception_handlers(app)
    app.include_router(_router())
    origins = _resolve_cors(cors_origins)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Accept", "Content-Type"],
        )
    return app


def _router():
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/v1")

    @router.get("/status", response_model=StatusResponse)
    def status(request: Request) -> StatusResponse:
        return status_response(request.app.state.runtime)

    @router.get(
        "/evaluation/summary",
        response_model=EvaluationSummaryResponse,
        responses=_ERROR_RESPONSES,
    )
    def evaluation_summary(request: Request) -> EvaluationSummaryResponse:
        path = default_artifact_paths(request.app.state.runtime.root).committed_summary
        return read_evaluation(path)

    @router.get("/eia/history", response_model=HistoryResponse, responses=_ERROR_RESPONSES)
    def eia_history(
        request: Request,
        state_id: Annotated[str | None, Query(pattern=_STATE_QUERY)] = None,
    ) -> HistoryResponse:
        return read_history(request.app.state.runtime, state_id)

    @router.get("/eia/holdout", response_model=HoldoutResponse, responses=_ERROR_RESPONSES)
    def eia_holdout(
        request: Request,
        state_id: Annotated[str | None, Query(pattern=_STATE_QUERY)] = None,
    ) -> HoldoutResponse:
        return read_holdout(request.app.state.runtime, state_id)

    @router.get(
        "/eia/holdout/cases",
        response_model=HoldoutCasesResponse,
        responses=_ERROR_RESPONSES,
    )
    def eia_holdout_cases(request: Request) -> HoldoutCasesResponse:
        return read_cases(request.app.state.runtime)

    @router.post(
        "/finance/scenarios",
        response_model=FinanceResponse,
        responses=_ERROR_RESPONSES,
    )
    def finance_scenarios(body: FinanceRequest, request: Request) -> FinanceResponse:
        return price_scenarios(request.app.state.runtime, body)

    @router.get("/pjm/catalog", response_model=PjmCatalogResponse)
    def catalog() -> PjmCatalogResponse:
        return pjm_catalog()

    @router.get("/pjm/screen", response_model=PjmScreenResponse, responses=_ERROR_RESPONSES)
    def screen(
        request: Request,
        pjm_zone: str,
        forecast_year: int,
        as_of: date,
    ) -> PjmScreenResponse:
        return pjm_screen(request.app.state.runtime, pjm_zone, forecast_year, as_of)

    return router


def _resolve_root(root: Path | None) -> Path:
    if root is not None:
        return Path(root)
    configured = os.environ.get("INFRALENS_ROOT")
    if configured:
        return Path(configured)
    return repository_root()


def _resolve_cors(cors_origins: list[str] | None) -> list[str]:
    if cors_origins is None:
        raw = os.environ.get("INFRALENS_CORS_ORIGINS", "")
        cors_origins = [part.strip() for part in raw.split(",") if part.strip()]
    if any(origin == "*" for origin in cors_origins):
        raise ValueError(
            "CORS origins must be an explicit allowlist. Wildcard origins are not allowed."
        )
    return list(cors_origins)


app = create_app()
