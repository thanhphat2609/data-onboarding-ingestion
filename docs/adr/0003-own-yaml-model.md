# ADR-0003: Own YAML configuration model instead of Flink CDC pipeline YAML

- Status: Proposed
- Date: 2026-10-21

## Context

The DE team wants to onboard sources and submit jobs as YAML, with one template per source type (SQL Server, PostgreSQL, BigQuery). Flink CDC 3.x provides a YAML pipeline definition (`source`, `sink`, `route`, `transform`).

## Decision

Define a platform-owned YAML model with four kinds (`SourceTemplate`, `SinkTemplate`, `Connection`, `IngestionJob`) described in [configuration-spec.md](../configuration-spec.md). The control plane renders them into a resolved job spec and a `FlinkDeployment` manifest executed by a generic runner.

## Consequences

- Full control over what a template expresses: preflight SQL, type mapping, load limits, verification policy, lake layout.
- Separation of ownership: platform team owns templates, DE team owns connections, users own jobs.
- The platform must maintain its own schemas, renderer and runner.

## Alternatives considered

- **Flink CDC pipeline YAML**: designed for CDC streaming. At the time of writing its pipeline sinks do not include Parquet or Delta on Azure Blob Storage, and SQL Server and BigQuery are not available as pipeline sources. To be revisited for CDC in Phase 7; check the connector list of the latest release before deciding.
- **Raw Flink SQL scripts per job**: flexible, but pushes connector details, secrets handling and layout conventions onto every user.
