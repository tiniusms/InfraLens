"""Mocked HTTP tests for EIA pagination completeness (no live API)."""

from __future__ import annotations

import httpx
import pytest

from infralens.data.eia_client import EiaApiError, fetch_retail_sales_pages
from infralens.data.eia_normalize import collect_observations

_TEST_KEY = "test-key-not-a-live-credential"


def _row(period: str, state_id: str) -> dict[str, str]:
    return {
        "period": period,
        "stateid": state_id,
        "sectorid": "COM",
        "price": "1.00",
        "sales": "10.0",
        "revenue": "0.10",
    }


def _page(total: int, rows: list[dict[str, str]]) -> dict:
    return {"response": {"total": str(total), "data": rows}}


def _client_for_pages(pages_by_offset: dict[int, dict]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        payload = pages_by_offset.get(offset)
        if payload is None:
            raise AssertionError(f"unexpected offset {offset}")
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_concatenates_multiple_pages() -> None:
    first = [
        _row("2001-01", "VA"),
        _row("2001-01", "PA"),
    ]
    second = [
        _row("2001-02", "VA"),
        _row("2001-02", "PA"),
    ]
    client = _client_for_pages(
        {
            0: _page(4, first),
            2: _page(4, second),
        }
    )
    pages = fetch_retail_sales_pages(
        api_key=_TEST_KEY,
        states=("VA", "PA"),
        client=client,
    )
    rows = collect_observations(pages)
    assert len(pages) == 2
    assert len(rows) == 4
    assert [row["period"] for row in rows] == [
        "2001-01",
        "2001-01",
        "2001-02",
        "2001-02",
    ]


def test_fetch_fails_on_empty_page_before_total() -> None:
    client = _client_for_pages(
        {
            0: _page(5, [_row("2001-01", "VA"), _row("2001-01", "PA")]),
            2: _page(5, []),
        }
    )
    with pytest.raises(EiaApiError, match="empty page"):
        fetch_retail_sales_pages(
            api_key=_TEST_KEY,
            states=("VA", "PA"),
            client=client,
        )


def test_fetch_fails_when_collected_rows_do_not_match_total() -> None:
    client = _client_for_pages(
        {
            0: _page(3, [_row("2001-01", "VA"), _row("2001-01", "PA")]),
            2: _page(3, [_row("2001-02", "VA"), _row("2001-02", "PA")]),
        }
    )
    with pytest.raises(EiaApiError, match="incomplete"):
        fetch_retail_sales_pages(
            api_key=_TEST_KEY,
            states=("VA", "PA"),
            client=client,
        )
