# ADR-0015: REST API sources land on Redpanda first; Flink reads a bounded offset range

- Status: Proposed (checked outside the Codespace with Airflow 3.3.2, Redpanda v25.3.18 and Flink 1.20.3; the Compose stack and the PyFlink spike are pending a Codespace run)
- Date: 2026-10-30

## Context

The roadmap asks for a REST API source after the four database sources (Phase 2). Flink has no generic HTTP source, and every API differs in auth, pagination, rate limits, retries and error handling. If that logic sat inside the Flink job, every new API, and every change an API provider makes, would touch the runner that all jobs share. The runner must stay one generic job: a table in, Parquet or Delta out ([ADR-0010](0010-pyflink-runner.md)). Runs must stay bounded and verifiable ([ADR-0002](0002-bounded-batch-execution.md)).

Options compared:

1. **Fetch inside PyFlink** (a Python function that calls the API before the SQL runs): puts API code back in the runner, and Python on the JobManager would do the network work.
2. **A custom Flink HTTP source** (Java): the most work, and the same coupling.
3. **Airflow fetches, then Flink reads a landing zone.** The landing zone is either files on ADLS or a Kafka topic.

## Decision

Option 3, with **Redpanda** (Kafka API, single binary, no JVM or ZooKeeper) as the landing zone.

- **Template `rest_api@1`** (`code/templates/sources/rest_api.yaml`, `connector: kafka`, `dialect: flink`). The connection holds `base_url`, `auth` (`none`, `bearer`, `header`, `query`), `auth_name`, `token` (a secret reference), `timeout` and `max_requests_per_second`. The job's `source.read` holds `endpoint`, `query_string`, `records_path`, `pagination` (`none`, `page`, `offset`, `cursor`) and its parameters, plus `max_pages`. `{{ ingest_date }}` can be used in `endpoint` and `query_string`.
- **DAG:** the template says `fetch: rest_api`, and that line (not `connector: kafka`, which a topic filled by another system would also have) makes the DAG factory add a `fetch` task: `validate → fetch → submit → wait`. `fetch` (`ingestion.rest_api.fetch_to_landing`) pages through the API, writes **one message per record** (the record's JSON, unchanged) to the job's topic `ingest.<job>`, and returns `{topic, start_offset, end_offset, records, pages}` to `submit`.
  - One single-partition topic per job. `max_active_runs=1` gives one writer per topic, and `fetch` fails if the offsets it gets back don't follow on from the start offset (another writer).
  - The producer is idempotent with `acks=all`. Offsets come from the delivery reports, so `[start_offset, end_offset)` is exactly this run's records. Records that a failed run already wrote fall outside the next run's range.
  - Retries (429 and 5xx, honouring a numeric `Retry-After`) and the request rate limit live in `fetch`. The run fails on other 4xx, on a `records_path` that isn't a list, and beyond `max_pages`. The token is never logged; with `auth: query` it is in the URL, so request URLs are not logged at all.
  - Topics are created by `fetch` through the Kafka admin API. Redpanda's HTTP proxy is not enough: it does not create topics, and it answers HTTP 200 with a per-record error code for a missing one (checked on v25.3.18).
- **Flink:** the job's query is **Flink SQL over one table, `landing`** (`payload STRING` holds the record's JSON, plus `_offset` and `_fetched_at`). The runner creates `landing` from `landing.table` in the template with the run's offsets: `scan.startup.mode` and `scan.bounded.mode` are both `specific-offsets`. The job reaches `FINISHED` by itself like the JDBC jobs, and the expected row count is `fetch`'s `records`. The SQL check accepts only `landing` (and CTEs over it) for this dialect.
- **Raw JSON is kept.** Queries can pick fields with `JSON_VALUE`, but keeping `payload` means a new or renamed field in the API never fails the Flink job. Parsing can then happen in dbt.
- **Images:** Airflow is `apache/airflow` plus `confluent-kafka` (`infrastructure/docker/airflow/Dockerfile`), with the control plane mounted on `PYTHONPATH`. Flink gets `flink-sql-connector-kafka` 3.3.0-1.20. Redpanda runs in non-prod and on VM 1 (Kafka API `redpanda:9092`; VM 2's TaskManagers use `FLINK_JOBMANAGER_ADDRESS:19092`). Retention is Redpanda's default of 7 days, so a run can be read again without calling the API.
- **Secrets** of API connections are needed by Airflow, which calls the API, not by Flink.

## Consequences

- A new API is a connection plus a job, with no code, as long as the auth and pagination styles above cover it. An API that needs something else (OAuth refresh, POST bodies, `Link` headers) is a change to `ingestion.rest_api` only; the Flink side doesn't change.
- When an API breaks, the `fetch` task fails with the API's message, and Flink is never started.
- Redpanda is one more service to run and size (roadmap question 8). Later, a streaming or webhook source can use the same topics.
- Flink reads partition 0 only. A topic with more partitions would need per-partition offsets in the template.
- `fetch` holds a whole page in memory, and a message is limited to Redpanda's 1 MB default. A record larger than that fails the run.
- An empty response gives `start_offset == end_offset`. The runner must then write an empty partition (Phase 4).

## Alternatives considered

- **Files on ADLS as the landing zone:** no new service, but no replay without the API, and no path to streaming sources. Still a fallback if Redpanda proves too costly to run.
- **Kafka Connect HTTP source:** a commercial (Confluent) or community connector. It is made for continuous polling, not "fetch this `ingest_date` once" from Airflow, and needs a Connect cluster.
- **Redpanda Connect (Benthos) `http_client` input:** configuration instead of code, but a second tool for pagination and auth rules that Python already covers and the tests check offline.
- **Apache Kafka:** the same model, but heavier to run on two VMs.
