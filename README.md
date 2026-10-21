# data-onboarding-ingestion

Self-service ingestion platform built on Apache Flink. The DE team onboards a source once from a YAML template (SQL Server, PostgreSQL, BigQuery). Users then submit a free-form read-only `SELECT`, and the platform compiles it into a bounded Flink batch job. The job lands Parquet or Delta on ADLS Gen2, partitioned by `ingest_date`, and every run is verified by row-count reconciliation before it is published.

![Architecture](docs/assets/architecture.svg)

## Status

**Phase 0: Project initialization.** Design documents only; no runnable code yet. See the [roadmap](docs/roadmap.md).

## Documentation

| Document | Content |
|---|---|
| [Architecture](docs/architecture.md) | Components, run lifecycle, completion detection, lake layout |
| [Roadmap](docs/roadmap.md) | Phases, checklists, exit criteria, open questions |
| [Configuration spec](docs/configuration-spec.md) | `SourceTemplate`, `SinkTemplate`, `Connection`, `IngestionJob` |
| [ADRs](docs/adr/README.md) | Architecture decisions and their trade-offs |
| [Contributing](CONTRIBUTING.md) | Conventions for this repository |

## Scope (v1)

- Sources: SQL Server, PostgreSQL, BigQuery
- Destination: Azure Data Lake Storage Gen2
- Formats: Parquet, Delta Lake
- Execution: Apache Flink 1.20 in batch mode on the Flink Kubernetes Operator (AKS)
- Triggering: CLI / API on demand; Airflow scheduling in Phase 5
