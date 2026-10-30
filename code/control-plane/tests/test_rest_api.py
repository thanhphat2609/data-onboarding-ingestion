"""API sources (ADR-0015): fetch -> landing, with a fake API (httpx.MockTransport) and an in-memory landing."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from ingestion.rest_api import FetchError, FetchResult, dig, fetch_to_landing, landing_table_sql, landing_topic
from ingestion.settings import REPO_ROOT
from ingestion.sql import check_sql
from ingestion.templates import Template, TemplateRegistry

REGISTRY = TemplateRegistry(REPO_ROOT / "code" / "templates")


class MemoryLanding:
    """One topic, one partition, like Redpanda: offsets continue from what is already there."""

    def __init__(self, existing: int = 0) -> None:
        self.messages: list[bytes] = [b"{}"] * existing

    def prepare(self, topic: str) -> int:
        return len(self.messages)

    def send(self, topic: str, values: list[bytes]) -> list[int]:
        start = len(self.messages)
        self.messages += values
        return list(range(start, len(self.messages)))

    def records(self, start: int = 0) -> list[Any]:
        return [json.loads(m) for m in self.messages[start:]]


def template() -> Template:
    return REGISTRY.source("rest_api@1")


def connection(**params: Any) -> dict[str, Any]:
    return {"name": "shop-api", "template": "rest_api@1", "params": {"base_url": "https://api.test/v1", **params}}


def job(**read: Any) -> dict[str, Any]:
    return {"name": "shop-api-orders-daily", "source": {"query": "SELECT payload FROM landing", "read": read}}


def run(
    handler: Any, conn: dict[str, Any], jb: dict[str, Any], landing: MemoryLanding | None = None
) -> tuple[FetchResult, MemoryLanding, list[float]]:
    landing = landing or MemoryLanding()
    sleeps: list[float] = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_to_landing(template(), conn, jb, "2026-10-25", landing, client=client, sleep=sleeps.append)
    return result, landing, sleeps


ORDERS = [{"order_id": i, "status": "paid"} for i in range(1, 251)]


def paged(request: httpx.Request) -> httpx.Response:
    page, size = int(request.url.params["page"]), int(request.url.params["page_size"])
    return httpx.Response(200, json={"data": ORDERS[(page - 1) * size : page * size]})


def test_page_pagination_lands_every_record_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOP_API_TOKEN", "t0ken")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return paged(request)

    result, landing, _ = run(
        handler,
        connection(token="env://SHOP_API_TOKEN"),
        job(
            endpoint="/orders",
            query_string="updated_date={{ ingest_date }}",
            records_path="data",
            pagination="page",
            page_size=100,
        ),
        MemoryLanding(existing=7),
    )
    assert result == FetchResult("ingest.shop-api-orders-daily", start_offset=7, end_offset=257, records=250, pages=3)
    assert [r["order_id"] for r in landing.records(7)] == list(range(1, 251))
    assert seen[0].url.path == "/v1/orders"
    assert seen[0].url.params["updated_date"] == "2026-10-25"
    assert [r.url.params["page"] for r in seen] == ["1", "2", "3"]
    assert seen[0].headers["Authorization"] == "Bearer t0ken"


def test_offset_and_cursor_pagination() -> None:
    def by_offset(request: httpx.Request) -> httpx.Response:
        start, size = int(request.url.params["offset"]), int(request.url.params["limit"])
        return httpx.Response(200, json=ORDERS[start : start + size])

    result, _, _ = run(
        by_offset,
        connection(auth="none"),
        job(endpoint="/orders", pagination="offset", page_param="offset", page_size_param="limit", page_size=100),
    )
    assert (result.records, result.pages) == (250, 3)

    def by_cursor(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("after", 0))
        rows = ORDERS[start : start + 100]
        nxt = str(start + 100) if start + 100 < len(ORDERS) else None
        return httpx.Response(200, json={"items": rows, "meta": {"next": nxt}})

    result, landing, _ = run(
        by_cursor,
        connection(auth="none"),
        job(
            endpoint="/orders", records_path="items", pagination="cursor", cursor_path="meta.next", cursor_param="after"
        ),
    )
    assert (result.records, result.pages) == (250, 3)
    assert landing.records()[-1]["order_id"] == 250


def test_retries_429_with_retry_after_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json=[{"id": 1}])

    result, _, sleeps = run(handler, connection(auth="none"), job(endpoint="/x"))
    assert result.records == 1
    assert 3.0 in sleeps


def test_client_errors_fail_without_retry_and_never_show_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEY", "s3cret")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["api_key"] == "s3cret"
        return httpx.Response(403, text="forbidden")

    with pytest.raises(FetchError) as error:
        run(handler, connection(auth="query", auth_name="api_key", token="env://KEY"), job(endpoint="/x"))
    assert calls == 1
    assert "HTTP 403" in str(error.value)
    assert "s3cret" not in str(error.value)


def test_wrong_records_path_and_page_limit_are_clear_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"id": 1}], "next": "x"})

    with pytest.raises(FetchError, match="records_path data is not a list; response: results, next"):
        run(handler, connection(auth="none"), job(endpoint="/x", records_path="data"))
    with pytest.raises(FetchError, match="max_pages=2"):
        run(
            handler,
            connection(auth="none"),
            job(endpoint="/x", records_path="results", pagination="cursor", cursor_path="next", max_pages=2),
        )


def test_auth_needs_a_token() -> None:
    with pytest.raises(FetchError, match="token is required"):
        run(paged, connection(), job(endpoint="/x"))


def test_another_writer_on_the_topic_fails_the_run() -> None:
    class Interleaved(MemoryLanding):
        def send(self, topic: str, values: list[bytes]) -> list[int]:
            self.messages.append(b"{}")  # someone else wrote first
            return super().send(topic, values)

    with pytest.raises(FetchError, match="another writer"):
        run(lambda r: httpx.Response(200, json=[{"id": 1}]), connection(auth="none"), job(endpoint="/x"), Interleaved())


def test_empty_response_gives_an_empty_range() -> None:
    result, _, _ = run(
        lambda r: httpx.Response(200, json=[]), connection(auth="none"), job(endpoint="/x"), MemoryLanding(existing=5)
    )
    assert (result.start_offset, result.end_offset, result.records) == (5, 5, 0)


def test_landing_table_is_bounded_by_the_run_offsets() -> None:
    result = FetchResult("ingest.j", start_offset=10, end_offset=60, records=50, pages=1)
    ddl = landing_table_sql(template(), result, "redpanda:9092")
    assert ddl.startswith("CREATE TABLE landing")
    assert "'topic' = 'ingest.j'" in ddl
    assert "'scan.startup.specific-offsets' = 'partition:0,offset:10'" in ddl
    assert "'scan.bounded.specific-offsets' = 'partition:0,offset:60'" in ddl
    assert landing_topic(template(), "orders-daily") == "ingest.orders-daily"


def test_dig() -> None:
    assert dig({"a": {"b": [1]}}, "a.b") == [1]
    assert dig([1], "") == [1]
    assert dig({"a": 1}, "a.b") is None


def test_flink_sql_reads_only_the_landing_table() -> None:
    ok = check_sql(
        "WITH o AS (SELECT CAST(JSON_VALUE(payload, '$.id') AS BIGINT) AS id FROM landing) SELECT id FROM o", "flink"
    )
    assert ok.ok, ok.issues
    bad = check_sql("SELECT payload FROM orders", "flink")
    assert [i.message for i in bad.issues] == ["Read only from the table landing, not orders: the API data lands there"]


def test_sample_pipeline_files_are_valid() -> None:
    from ingestion.settings import Settings
    from ingestion.store import ConfigStore

    store = ConfigStore(Settings.from_env(), REGISTRY)
    assert store.invalid_files() == []
    assert "shop-api-orders-daily" in {j["name"] for j in store.list_jobs()}


def test_only_the_api_template_declares_a_fetch_task() -> None:
    # The DAG factory adds `fetch` before `submit` from this field, not from `connector: kafka`.
    assert {t.name: t.body.get("fetch") for t in REGISTRY.sources()} == {
        "mysql": None,
        "postgresql": None,
        "rest_api": "rest_api",
        "sqlserver": None,
    }
