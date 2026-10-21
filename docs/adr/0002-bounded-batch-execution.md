# ADR-0002: Bounded batch execution and completion detection

- Status: Proposed
- Date: 2026-10-21

## Context

A run must stop by itself once it has read everything the user's query returns, and the platform must only report success when the output is complete. Sources may receive writes while a run is in progress.

## Decision

1. **Bounded by design.** Jobs run with `execution.runtime-mode: BATCH` and use only bounded sources (JDBC scan or `JdbcSource`, BigQuery Storage Read on a table or materialized query). The job reaches `FINISHED` when all splits are read. No component polls the source for remaining data.
2. **Fixed cut-off at preflight.** The control plane captures `run_ts`, partition bounds (`MIN/MAX`) and the expected row count before submission and passes them as constants. An optional `snapshot_column` adds `<= run_ts` to the query. SQL Server reads use `applicationIntent=ReadOnly`; BigQuery queries are materialized into a temporary table.
3. **Detection by the control plane.** A Kubernetes informer watches `FlinkDeployment.status.jobStatus.state`; the Flink REST API is a fallback. Each run has a hard timeout (default `2h`).
4. **Verification before publishing.** Written rows (runner manifest, cross-checked with Parquet footers) are compared with the expected count using the job's policy (`exact`, `tolerance`, `skip`). Output stays in staging until verification passes.

## Consequences

- Completion is a property of the job, not of an external monitor, which removes a whole class of "stuck job" bugs.
- Parallel partitioned reads are separate queries and therefore not a single database snapshot. Jobs on actively written tables should use `snapshot_column`, a replica, or a `tolerance` policy.
- Preflight runs the query (or a count over it) at least once more; costly queries can opt out with `verify.row_count: skip`.
- Retries always restart the whole run, which is simple because nothing outside staging is touched before publishing.

## Alternatives considered

- **Streaming job with an idle-timeout watchdog** that cancels the job when no records arrive: fragile (slow sources look idle), and output commit semantics are tied to checkpoints.
- **Polling the source** to compare progress with a count: adds load and still cannot prove completeness.
