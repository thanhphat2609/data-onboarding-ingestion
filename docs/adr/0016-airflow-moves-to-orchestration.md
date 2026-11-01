# ADR-0016: Airflow moves to data-onboarding-orchestration

- Status: Accepted
- Date: 2026-11-01
- Amends: [ADR-0008](0008-airflow-dag-per-job.md) (where Airflow and the factory live), [ADR-0011](0011-shared-postgresql-server.md) (`local-db`)

## Context

ADR-0008 kept Airflow's image and Compose files here "until a second repository needs them; then they move to a shared platform repository". dbt in data-onboarding-transformation is that second repository: its DAGs have to run after ingestion publishes a table.

## Decision

- `code/airflow/`, `infrastructure/docker/airflow/`, the Airflow services and the `local-db` PostgreSQL move to [data-onboarding-orchestration](https://github.com/thanhphat2609/data-onboarding-orchestration). Its [ADR-0001](https://github.com/thanhphat2609/data-onboarding-orchestration/blob/main/docs/adr/0001-orchestration-repo.md) and [ADR-0002](https://github.com/thanhphat2609/data-onboarding-orchestration/blob/main/docs/adr/0002-repo-contracts.md) hold the details.
- This repository keeps what Flink and the Web UI need: `pipelines/`, `code/templates/`, the control plane, the UI, Flink, Redpanda. `pipelines/` stays here because the API writes it and data-onboarding-agent reads it here.
- `code/control-plane/src/ingestion/airflow.py` stays: it is the REST client for "Run now", run status and pools.
- Airflow reads this repository from a read-only checkout next to its own. The schemas in `code/templates/schemas/` are a contract with its DAG factory.
- This stack gives its shared resources fixed names, `ingestion-flink-examples` and `ingestion-runs`, and puts Flink, Redpanda and the API on `data-platform`.
- A `pipelines/`-only deploy no longer touches Airflow: pools follow the connection files on their own.

## Consequences

- Start order: data-onboarding-agent (when used), this repository, data-onboarding-orchestration.
- This stack alone has no Airflow: jobs don't become DAGs and "Run now" fails. Use a Codespace of data-onboarding-orchestration for the whole platform.
- Airflow's secrets move to that repository. `AIRFLOW_ADMIN_PASSWORD` stays here too, because the API logs in with it.
- A breaking change to the job or connection schema needs a matching change in that repository.

## Alternatives considered

- **Keep Airflow here.** dbt DAGs would then depend on this repository's releases.
