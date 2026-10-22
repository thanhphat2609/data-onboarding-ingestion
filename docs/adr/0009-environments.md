# ADR-0009: Non-prod on GitHub Codespaces, prod on two VMs

- Status: Proposed
- Date: 2026-10-22

## Context

The platform needs a shared development environment now and a production environment later. Production virtual machines are not available yet. Everything that defines containers and environments should live in one place.

## Decision

**Two environments.**

| Environment | Where | Layout |
|---|---|---|
| **non-prod** | GitHub Codespaces | One Docker Compose project with every service |
| **prod** | Two virtual machines | VM 1: Web UI, Ingestion API, Airflow, Flink JobManager. VM 2: Flink TaskManagers |

**Non-prod** runs from `infrastructure/non-prod/docker-compose.yml`:

- Web UI, Ingestion API
- Airflow (API server, scheduler, DAG processor, triggerer)
- PostgreSQL 16 for the Airflow metadata database and the platform database
- Flink 1.20 JobManager and TaskManager (session cluster, [ADR-0007](0007-flink-standalone-session-cluster.md))
- SQL Server 2022 with a seeded sample database as a test source

The Codespace definition, `.devcontainer/devcontainer.json`, starts the Compose project and forwards the Web UI, Airflow and Flink web UI ports. GitHub only reads it from the repository root, so it is the one container-related file outside `infrastructure/`. Secrets come from Codespaces secrets or a local `.env` file that is never committed. The lake is the dev ADLS Gen2 account.

**Prod** gets one Compose project per VM (`infrastructure/prod/vm1/`, `infrastructure/prod/vm2/`). It is built when the VMs exist. Until then there is no prod CI/CD.

**Everything Docker-related lives in `infrastructure/`.**

```
infrastructure/
  docker/            Dockerfiles: flink, airflow, api, ui
  non-prod/          docker-compose.yml, .env.example
  prod/vm1/          docker-compose.yml (Phase 6)
  prod/vm2/          docker-compose.yml (Phase 6)
```

Both environments use the same images; only Compose files and environment variables differ.

## Consequences

- One command starts the full platform for any contributor, without local installation.
- Codespaces needs a large machine type (at least 4 cores and 16 GB RAM) because SQL Server, Airflow and Flink run side by side.
- A Codespace stops when idle, so non-prod cannot prove long-running behaviour such as a job scheduled daily for a week. Those checks move to prod (Phase 6).
- Each Codespace is private to its user; non-prod data and Airflow history are not shared between developers.
- Behaviour that only exists across two machines (network between VMs, TaskManager loss) is tested in prod or with a two-VM staging setup later.

## Alternatives considered

- **Local Docker Compose on each laptop**: works, but depends on each machine's resources and setup.
- **A shared dev VM**: realistic, but there is no VM available yet, and one shared VM makes parallel work harder.
- **Kubernetes (kind or AKS)**: no longer the target runtime ([ADR-0007](0007-flink-standalone-session-cluster.md)).
