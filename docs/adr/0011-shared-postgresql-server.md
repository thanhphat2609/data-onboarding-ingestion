# ADR-0011: One shared PostgreSQL server, hosted by the onboarding agent stack

- Status: Proposed
- Date: 2026-10-24
- Amends: [architecture §3.4](../architecture.md#34-metadata-db), [ADR-0009](0009-environments.md) (PostgreSQL in the non-prod Compose project)

## Context

Architecture §3.4 puts Airflow's metadata database and the platform database on one PostgreSQL 16 instance, run by this repository's Compose project. The [data-onboarding-agent](https://github.com/thanhphat2609/data-onboarding-agent) now needs PostgreSQL too, for its chat sessions. For the real demo the platform has two VMs: VM 1 runs the agent, Airflow and the Flink JobManager, and VM 2 runs the Flink TaskManagers. Two PostgreSQL servers on VM 1 would mean two sets of backups, upgrades and memory for the same job.

This repository is still in Phase 1, so its own stack can't be the one to test PostgreSQL with yet. The agent's stack can be started today.

## Decision

**One PostgreSQL 16 server for the platform, defined in the data-onboarding-agent Compose project.** It holds one database per owner, and no database is shared between owners:

| Database | Owner role | Used by | Tables created by |
|---|---|---|---|
| `airflow` | `airflow` | Airflow metadata | `airflow db migrate` |
| `platform` | `platform` | Run records (§3.4: `runs`, `run_events`, Phase 5) | This repository |
| `onboarding_agent` | `agent` | Agent sessions | The agent |

- The agent stack's init script creates all three databases and roles on the first start of an empty volume.
- The agent stack creates the Docker network `data-platform` and attaches the server to it. This repository's Airflow joins that network as an external network and connects to `postgres:5432` (`METADATA_DB_HOST` overrides the host).
- The two `.env` files must agree: `AIRFLOW_DB_PASSWORD` / `PLATFORM_DB_PASSWORD` here = `POSTGRES_AIRFLOW_PASSWORD` / `POSTGRES_PLATFORM_PASSWORD` there.
- Compose can't wait for a service of another project, so `start.sh` waits for the database (`airflow db check`, up to 5 minutes) before `airflow db migrate`.
- **Standalone fallback:** a Codespace of this repository alone has no agent stack. The `local-db` Compose profile starts the existing local PostgreSQL container with the same databases. `bootstrap.sh` sets `COMPOSE_PROFILES=local-db` by default and creates the `data-platform` network if it is missing.
- The agent never reads the `airflow` or `platform` databases. If it needs run status, it calls the Airflow REST API.

## Consequences

- VM 1 runs one PostgreSQL server; backups and upgrades cover every database at once (Phase 6).
- On a shared host, Airflow depends on the agent stack being up: start the agent stack first. `down -v` on the agent stack deletes Airflow's metadata as well.
- Sharing needs both stacks on one Docker host. Two separate Codespaces can't share the server; each ingestion Codespace keeps using `local-db`.
- The PostgreSQL version is pinned in two places (here for `local-db`, in the agent repository for the shared server) and must be changed together.
- If the agent moves off VM 1 later, the server should move to its own Compose project (or a managed PostgreSQL) instead of following the agent.

## Plan

| Step | Where | Status |
|---|---|---|
| 1. Shared server with `airflow`, `platform`, `onboarding_agent`; network `data-platform` | data-onboarding-agent `infrastructure/` | Done, to test in a Codespace |
| 2. Non-prod Compose: Airflow on `data-platform`, `local-db` profile, `start.sh` waits for the DB, `bootstrap.sh` network + profile | this repository `infrastructure/non-prod/` | Done, not yet verified |
| 3. Verify standalone (`local-db`) in a Codespace of this repository: Airflow healthy, sample DAG runs | Codespace | Open |
| 4. Verify shared mode on one host: agent stack first, then this stack with `COMPOSE_PROFILES=` empty; Airflow tables appear in the shared `airflow` database | One Codespace or VM with both repositories | Open |
| 5. Phase 5: `runs` / `run_events` in the `platform` database, migrations owned by this repository | `code/control-plane/` | Not started |
| 6. Phase 6: `infrastructure/prod/vm1/` joins the agent stack's server; backups of the `pgdata` volume (`pg_dump` per database) | prod VM 1 | Not started |

## Alternatives considered

- **Server in this repository's Compose project, the agent connects to it**: Airflow would not depend on the agent stack. Rejected for now because this stack is still in Phase 1 and can't host the server for testing yet. This is the preferred direction if the agent stops running on VM 1.
- **A separate Compose project only for PostgreSQL**: the cleanest ownership, but a third project to start for the demo. Revisit for prod.
- **Two servers (one per stack)**: no coupling, but two servers to back up and upgrade on the same VM.
- **One database, a schema per owner**: Airflow's migrations expect to own their database, and per-database roles give cleaner isolation and per-database backups.
