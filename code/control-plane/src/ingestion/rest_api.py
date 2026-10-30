"""API sources (ADR-0015): the Airflow task ``fetch`` pages through a REST API and lands every record on Redpanda.

Flink never calls the API. ``fetch`` writes one message per record (the record's JSON) to the job's single-partition
topic and returns the run's offsets; the runner then reads exactly that range as the bounded table ``landing``
(``landing.table`` in ``code/templates/sources/rest_api.yaml``). So everything that differs between APIs (auth,
pagination, rate limits, retries) lives here, and the Flink side is the same for every API.

The Kafka client is imported lazily, so the API and the tests don't need it; the Airflow image installs it.
"""

from __future__ import annotations

import importlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Protocol
from urllib.parse import parse_qsl

import httpx

from ingestion import secrets
from ingestion.templates import Template, render, with_defaults

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
MAX_RETRY_WAIT_S = 60.0
SEND_BATCH = 500  # records per acknowledged write; a page is split into batches of this size


class FetchError(Exception):
    """The run can't land the API's data; the message is shown in the Airflow task log."""


class Landing(Protocol):
    def prepare(self, topic: str) -> int:
        """Creates the topic if needed and returns its next offset (where this run's first record will land)."""
        ...

    def send(self, topic: str, values: list[bytes]) -> list[int]:
        """Writes the values in order and returns their offsets once every one is acknowledged."""
        ...


@dataclass(frozen=True)
class FetchResult:
    topic: str
    start_offset: int  # inclusive
    end_offset: int  # exclusive; equals start_offset when the API returned no records
    records: int
    pages: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def landing_topic(template: Template, job_name: str) -> str:
    return render(str(template.body["landing"]["topic"]), {"job": job_name})


def landing_table_sql(template: Template, result: FetchResult, bootstrap_servers: str) -> str:
    """The Flink SQL ``CREATE TABLE landing`` for one run, for the runner (Phase 4)."""
    values = {**result.as_dict(), "bootstrap_servers": bootstrap_servers}
    return render(str(template.body["landing"]["table"]), values).strip()


def dig(document: Any, path: str | None) -> Any:
    """Value at a dot path (``data.items``); the document itself for an empty path, None when a key is missing."""
    value = document
    for key in (path or "").split("."):
        if not key:
            continue
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _seconds(duration: str) -> float:
    return float(int(duration[:-1]) * {"s": 1, "m": 60, "h": 3600}[duration[-1]])


class _Api:
    """GET with auth, a request rate limit and retries on 429/5xx (honouring a numeric Retry-After)."""

    def __init__(self, params: dict[str, Any], client: httpx.Client, sleep: Callable[[float], None]) -> None:
        self.base_url = str(params["base_url"]).rstrip("/")
        self.client = client
        self.sleep = sleep
        self.interval = 1.0 / int(params["max_requests_per_second"])
        self.timeout = _seconds(str(params["timeout"]))
        self.headers: dict[str, str] = {"Accept": "application/json"}
        self.auth_query: dict[str, str] = {}
        auth = params["auth"]
        if auth != "none":
            if not params.get("token"):
                raise FetchError(f"connection param token is required with auth: {auth}")
            token = secrets.resolve(str(params["token"]))
            if auth == "bearer":
                self.headers["Authorization"] = f"Bearer {token}"
            elif not params.get("auth_name"):
                raise FetchError(f"connection param auth_name is required with auth: {auth}")
            elif auth == "header":
                self.headers[str(params["auth_name"])] = token
            else:
                self.auth_query[str(params["auth_name"])] = token
        self._last_request = float("-inf")

    def get(self, path: str, query: dict[str, str]) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            wait = self._last_request + self.interval - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            self._last_request = time.monotonic()
            try:
                response = self.client.get(
                    url, params={**query, **self.auth_query}, headers=self.headers, timeout=self.timeout
                )
            except httpx.TransportError as error:
                problem, retry_after = f"{type(error).__name__}: {error}", None
            else:
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError:
                        raise FetchError(f"GET {path}: the response is not JSON") from None
                if response.status_code not in RETRY_STATUSES:
                    # Never the URL: with auth: query it holds the token.
                    raise FetchError(f"GET {path} returned HTTP {response.status_code}: {response.text[:300]}")
                problem, retry_after = f"HTTP {response.status_code}", response.headers.get("Retry-After")
            if attempt == MAX_ATTEMPTS:
                raise FetchError(f"GET {path} failed {MAX_ATTEMPTS} times, last: {problem}")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2.0**attempt
            log.warning("GET %s: %s; retry %d/%d in %.0fs", path, problem, attempt, MAX_ATTEMPTS - 1, delay)
            self.sleep(min(delay, MAX_RETRY_WAIT_S))
        raise AssertionError("unreachable")


def fetch_to_landing(
    template: Template,
    connection: dict[str, Any],
    job: dict[str, Any],
    ingest_date: str,
    landing: Landing,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Pages through the job's endpoint and lands every record; one call per Airflow run."""
    conn = with_defaults(template.params("connection_params"), connection["params"])
    read = with_defaults(template.params("read_params"), job["source"].get("read"))
    values = {"ingest_date": ingest_date}
    path = render(str(read["endpoint"]), values)
    base_query = dict(parse_qsl(render(str(read.get("query_string") or ""), values), keep_blank_values=True))
    pagination, page_size, max_pages = read["pagination"], int(read["page_size"]), int(read["max_pages"])
    topic = landing_topic(template, job["name"])

    # httpx logs every request URL at INFO, and with auth: query the URL holds the token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    own_client = client is None
    api = _Api(conn, client or httpx.Client(follow_redirects=True), sleep)
    try:
        start = next_offset = landing.prepare(topic)
        records = pages = 0
        cursor: str | None = None
        while True:
            if pages == max_pages:
                raise FetchError(f"more than max_pages={max_pages} pages; raise it or narrow the query")
            query = dict(base_query)
            if pagination in ("page", "offset"):
                position = pages + 1 if pagination == "page" else records
                query |= {str(read["page_param"]): str(position), str(read["page_size_param"]): str(page_size)}
            elif pagination == "cursor" and cursor:
                query[str(read["cursor_param"])] = cursor
            body = api.get(path, query)
            pages += 1

            page = dig(body, read.get("records_path"))
            if not isinstance(page, list):
                keys = ", ".join(map(str, body)) if isinstance(body, dict) else type(body).__name__
                raise FetchError(
                    f"records_path {read.get('records_path') or '(empty)'} is not a list; response: {keys}"
                )
            for i in range(0, len(page), SEND_BATCH):
                batch = [
                    json.dumps(r, ensure_ascii=False, separators=(",", ":")).encode() for r in page[i : i + SEND_BATCH]
                ]
                offsets = landing.send(topic, batch)
                # Offsets must follow on from the last write: anything else means another writer on the topic.
                if offsets != list(range(next_offset, next_offset + len(batch))):
                    raise FetchError(f"topic {topic} has another writer: expected offsets from {next_offset}")
                next_offset += len(batch)
            records += len(page)
            log.info("Page %d: %d record(s), %d so far", pages, len(page), records)

            if pagination == "none":
                break
            if pagination == "cursor":
                cursor = dig(body, read.get("cursor_path"))
                if not cursor or not page:
                    break
                cursor = str(cursor)
            elif len(page) < page_size:
                break
    finally:
        if own_client:
            api.client.close()
    result = FetchResult(topic=topic, start_offset=start, end_offset=next_offset, records=records, pages=pages)
    log.info("Landed %d record(s) from %d page(s) on %s, offsets [%d, %d)", records, pages, topic, start, next_offset)
    return result


class KafkaLanding:
    """Redpanda (or any Kafka) through confluent-kafka: idempotent producer, acks from every replica."""

    def __init__(self, bootstrap_servers: str, timeout_s: float = 60.0) -> None:
        # Untyped on purpose: only the Airflow image has confluent-kafka, the API and CI don't.
        self.kafka: Any = importlib.import_module("confluent_kafka")
        self.kafka_admin: Any = importlib.import_module("confluent_kafka.admin")
        config = {"bootstrap.servers": bootstrap_servers}
        self.admin = self.kafka_admin.AdminClient(config)
        self.producer = self.kafka.Producer({**config, "acks": "all", "enable.idempotence": True, "linger.ms": 20})
        self.timeout_s = timeout_s

    def prepare(self, topic: str) -> int:
        if topic not in self.admin.list_topics(timeout=self.timeout_s).topics:
            future = self.admin.create_topics([self.kafka_admin.NewTopic(topic, num_partitions=1)])[topic]
            try:
                future.result(self.timeout_s)
                log.info("Created topic %s", topic)
            except self.kafka.KafkaException as error:
                if error.args[0].code() != self.kafka.KafkaError.TOPIC_ALREADY_EXISTS:
                    raise
        partition = self.kafka.TopicPartition(topic, 0)
        spec = self.kafka_admin.OffsetSpec.latest()
        latest = self.admin.list_offsets({partition: spec})[partition].result(self.timeout_s)
        return int(latest.offset)

    def send(self, topic: str, values: list[bytes]) -> list[int]:
        offsets: list[int] = []
        errors: list[str] = []

        def delivered(error: Any, message: Any) -> None:
            if error is not None:
                errors.append(str(error))
            else:
                offsets.append(message.offset())

        for value in values:
            self.producer.produce(topic, value=value, partition=0, on_delivery=delivered)
            self.producer.poll(0)
        remaining = int(self.producer.flush(self.timeout_s))
        if errors or remaining:
            raise FetchError(f"writing to {topic} failed: {errors[0] if errors else f'{remaining} not acknowledged'}")
        return offsets
