# ADR-0001: Apache Flink 1.20 on the Flink Kubernetes Operator, one cluster per run

- Status: Proposed
- Date: 2026-10-21

## Context

The platform needs a distributed engine that reads from JDBC databases and BigQuery in parallel, writes Parquet to ADLS Gen2, and can be driven by generated configuration. Jobs are bounded batch snapshots with very different sizes, submitted ad hoc by many users.

## Decision

- Use **Apache Flink 1.20**, the last 1.x release line, because the connectors this platform depends on (`flink-connector-jdbc`, the BigQuery connector, filesystem/Parquet) target the 1.x API. Moving to Flink 2.x is re-evaluated when those connectors support it.
- Deploy with the **Flink Kubernetes Operator** on AKS.
- Run **one `FlinkDeployment` in application mode per run**, with `upgradeMode: stateless`, deleted after the run is published.
- Use a local **session cluster** (docker-compose) only for development and spikes.

## Consequences

- Each run gets its own resources and failure domain; one heavy job cannot starve others.
- The run definition is itself a Kubernetes YAML manifest, which fits the template-driven design.
- Every run pays cluster start-up time (tens of seconds). Acceptable for batch.
- The control plane must clean up finished deployments and preserve job history through the Flink History Server.

## Alternatives considered

- **Long-running session cluster on AKS**: faster start, but shared resources, noisy neighbours, and one cluster failure affects all runs.
- **Spark**: equally capable for batch, but the goal includes a later path to CDC/streaming with the same engine and the reference design (Grab) is Flink-based.
- **Flink 2.x**: rejected for v1 because of connector availability.
