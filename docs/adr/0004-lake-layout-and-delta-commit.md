# ADR-0004: Lake layout by `ingest_date` and staged publishing

- Status: Proposed (Delta strategy pending Phase 2 spike)
- Date: 2026-10-21

## Context

v1 writes Parquet and Delta to ADLS Gen2. Snapshot history must be kept per ingest day, and re-running the same day must not create duplicates. Readers must never see partial output from a failed or running job.

## Decision

**Layout.** Every table is partitioned by `ingest_date` and carries the audit columns `_ingest_run_id` and `_ingested_at`:

```
raw/parquet/<system>/<schema>/<table>/ingest_date=YYYY-MM-DD/
raw/delta/<system>/<schema>/<table>/   (Delta table, partition column ingest_date)
```

**Writes always go to a run-scoped location first; publishing is a separate control-plane step after verification.**

- **Parquet:** the runner writes to `raw/_staging/<run_id>/`. The publisher replaces `ingest_date=<date>/` by renaming the staged directory (atomic on ADLS Gen2 with hierarchical namespace), then writes `_SUCCESS` and `_manifest.json`.
- **Delta (preferred, to be confirmed):** the runner writes Parquet files under the Delta table root in a run-specific directory. Files not referenced by the Delta log are invisible to readers. The publisher creates **one Delta commit** that adds the new files and removes the existing files of that `ingest_date` partition, using delta-rs (`create_write_transaction` or equivalent).
- **Delta fallback:** use the `delta-flink` sink (append) and let the publisher delete the previous rows of that `ingest_date` with delta-rs afterwards. This takes two commits, so readers may briefly see both versions.

## Consequences

- Readers either see the previous complete partition or the new complete partition.
- The runner is independent of the Delta library version; Delta concerns live in the publisher.
- Requires hierarchical namespace on the storage account.
- The Parquet replace is "delete old directory, rename new directory": a reader listing between the two operations can see an empty partition. Readers that need strict atomicity should use Delta.
- The Phase 2 spikes must confirm: Parquet written by Flink (timestamp encoding, schema) is accepted in a Delta commit and readable by Spark and pandas; the delta-rs API commits externally written files with partition values on ADLS Gen2.

## Alternatives considered

- **Full overwrite of the table per run**: loses history, rejected.
- **Append only, never replace**: re-runs create duplicates, rejected.
- **`delta-flink` sink only**: couples the runner to a connector with uncertain Flink 1.20 support and append-only semantics; kept as fallback.
