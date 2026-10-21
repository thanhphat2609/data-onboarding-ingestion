# ADR-0006: On-demand runs first, Airflow for scheduling

- Status: Proposed
- Date: 2026-10-21

## Context

Most ingestion jobs eventually need to run on a schedule, often as one step in a larger pipeline (ingest, then transform, then publish). The first phases focus on making a single run correct.

## Decision

- **Phases 1–4:** runs are triggered on demand with `ingestctl run <job>` or `POST /jobs/{name}/runs`. Both accept `ingest_date`, which also supports backfills.
- **Interim option:** if scheduling is needed before Phase 5, use a Kubernetes `CronJob` that calls `ingestctl run <job> --wait`.
- **Phase 5:** integrate with **Apache Airflow** instead of building a scheduler:
  - `IngestionRunOperator` triggers a run through the API and waits for a terminal state as a deferrable task.
  - `ingest_date` is taken from the DAG run's logical date, so Airflow backfills map to `ingest_date` partitions.
  - DAGs are generated from the optional `schedule` field on `IngestionJob`, or written by hand when ingestion is part of a larger DAG.
- The **control plane remains the source of truth** for run state, concurrency limits and idempotency. Airflow only triggers and observes.
- The `schedule` field is part of the spec from the start so that jobs do not need to change when Phase 5 lands.

## Consequences

- No scheduler code to build, operate or make highly available.
- Ingestion runs can be chained with downstream tasks using standard Airflow dependencies.
- Requires an Airflow deployment (open question 3 in the roadmap). Without one, the `CronJob` interim option can stay longer.

## Alternatives considered

- **Built-in scheduler in the control plane** (for example APScheduler): needs leader election, missed-run handling and backfill semantics, all of which Airflow already provides.
- **Kubernetes CronJob only**: fine for independent jobs, but no dependency management or backfill UI.
