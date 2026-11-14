# data-onboarding-ingestion

Self-service ingestion platform built on Apache Flink. The DE team onboards a source once from a YAML template (SQL Server, PostgreSQL, MySQL, BigQuery, REST APIs). Users then define a job in the Web UI (or as YAML) with a free-form read-only `SELECT`; each job becomes its own Airflow DAG, and every run is compiled into a bounded Flink batch job. The job lands Parquet or Delta on ADLS Gen2, partitioned by `ingest_date`, and every run is verified by row-count reconciliation before it is published.

![Architecture](docs/assets/architecture.svg)

## Demo Video

[![Orchestration + Ingestion + Transformation demo](https://img.youtube.com/vi/mqt1bk2nVeQ/0.jpg)](https://youtu.be/mqt1bk2nVeQ)

End-to-end demo across the three repos: [data-onboarding-orchestration](https://github.com/thanhphat2609/data-onboarding-orchestration) (Airflow), [data-onboarding-ingestion](https://github.com/thanhphat2609/data-onboarding-ingestion) (Flink), and [data-onboarding-transformation](https://github.com/thanhphat2609/data-onboarding-transformation) (dbt).

## Status

**Phase 1 is closed; the Phase 2 and 4 pieces ran together on a prototype.** In prod, on two Azure VMs (stopped between sessions), a job created in the Web UI became an Airflow DAG whose run copied a MySQL table to Parquet on ADLS Gen2 ([ADR-0019](docs/adr/0019-runner-on-the-prototype-cluster.md)). Saves live in their pull request until merged ([ADR-0018](docs/adr/0018-saves-live-in-their-pull-request.md)). See the [roadmap](docs/roadmap.md) for what is still open (publisher, verify, query mode).

## Repository layout

```
.devcontainer/            GitHub Codespaces definition (starts non-prod)
.github/                  CI workflows (Phase 3)
code/                     everything the platform team writes and deploys
  ui/                     Web UI (React)
  control-plane/          shared library, Ingestion API (FastAPI), ingestctl CLI
  runner/                 generic Flink job (PyFlink)
  templates/              versioned source and sink templates, JSON Schemas
    sources/  sinks/  runtime/  schemas/
pipelines/                git-ignored working copy of what the Web UI saved; the real files are in data-onboarding-orchestration (ADR-0017)
  connections/            onboarded sources (connections/<name>.yaml)
  jobs/                   ingestion jobs; jobs/<name>.yaml becomes DAG ingest__<name>
infrastructure/           Dockerfiles and Docker Compose per environment
  docker/  non-prod/  prod/
  non-prod/example-sources/  test sources for demos (SQL Server, PostgreSQL, MySQL, REST API); non-prod only
docs/                     architecture, roadmap, configuration spec, ADRs
```

Details and reasons: [architecture §12](docs/architecture.md#12-repository-layout).

## Getting started

Open the repository in GitHub Codespaces (4-core / 16 GB machine). The non-prod stack starts by itself: Web UI on port 3000, Flink on 8081. Airflow is in [data-onboarding-orchestration](https://github.com/thanhphat2609/data-onboarding-orchestration): a Codespace of that repository starts both stacks, with Airflow on 8080. See [infrastructure/README.md](infrastructure/README.md) to run it elsewhere.

The repository has no example connections or jobs. To demo the platform, start the example sources and create a connection and a job by hand in the Web UI; each save opens a pull request on data-onboarding-orchestration, and after the merge the job becomes a DAG there: [infrastructure/non-prod/example-sources/README.md](infrastructure/non-prod/example-sources/README.md).

## Documentation

| Document | Content |
|---|---|
| [Architecture](docs/architecture.md) | Components, run lifecycle, completion detection, lake layout |
| [Roadmap](docs/roadmap.md) | Phases, checklists, exit criteria, open questions |
| [Configuration spec](docs/configuration-spec.md) | `SourceTemplate`, `SinkTemplate`, `Connection`, `IngestionJob` |
| [ADRs](docs/adr/README.md) | Architecture decisions and their trade-offs |
| [PostgreSQL](https://github.com/thanhphat2609/data-onboarding-orchestration/blob/main/docs/postgresql.md) | The `airflow` and `platform` databases: how to connect and check every table |
| [Contributing](CONTRIBUTING.md) | Conventions for this repository |

## Scope (v1)

- Sources: SQL Server, PostgreSQL, MySQL, BigQuery; REST APIs through a Redpanda landing topic ([ADR-0015](docs/adr/0015-rest-api-source-via-redpanda.md))
- Destination: Azure Data Lake Storage Gen2
- Formats: Parquet, Delta Lake
- Execution: Apache Flink 1.20 in batch mode on a standalone session cluster (JobManager on VM 1, TaskManagers on VM 2)
- Orchestration: Apache Airflow in [data-onboarding-orchestration](https://github.com/thanhphat2609/data-onboarding-orchestration), one DAG `ingest__<name>` per job file; on-demand runs from the UI or CLI
- Environments: non-prod on GitHub Codespaces (one Docker Compose project), prod on two VMs; container definitions in `infrastructure/`
