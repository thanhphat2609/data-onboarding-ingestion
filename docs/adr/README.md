# Architecture Decision Records

Each ADR records one decision: its context, the decision, its consequences and the alternatives considered. ADRs are immutable once `Accepted`; a changed decision gets a new ADR that supersedes the old one.

Statuses: `Proposed` → `Accepted` | `Rejected`, later optionally `Superseded by ADR-XXXX`.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-flink-on-kubernetes-operator.md) | Apache Flink 1.20 on the Flink Kubernetes Operator, one cluster per run | Superseded by 0007 |
| [0002](0002-bounded-batch-execution.md) | Bounded batch execution and completion detection | Proposed |
| [0003](0003-own-yaml-model.md) | Own YAML configuration model instead of Flink CDC pipeline YAML | Proposed |
| [0004](0004-lake-layout-and-delta-commit.md) | Lake layout by `ingest_date` and staged publishing | Proposed (pending Phase 2 spike) |
| [0005](0005-free-form-sql.md) | Free-form read-only SQL with AST validation and rewriting | Proposed |
| [0006](0006-scheduling.md) | On-demand runs first, Airflow for scheduling | Superseded by 0008 |
| [0007](0007-flink-standalone-session-cluster.md) | Apache Flink 1.20 standalone session cluster on VMs | Proposed |
| [0008](0008-airflow-dag-per-job.md) | Airflow orchestrates runs, one DAG per ingestion job | Proposed |
| [0009](0009-environments.md) | Non-prod on GitHub Codespaces, prod on two VMs | Proposed |
| [0010](0010-pyflink-runner.md) | PyFlink runner, Table API and SQL only | Proposed (pending Phase 2 spikes) |

## Template

```markdown
# ADR-XXXX: Title

- Status: Proposed
- Date: YYYY-MM-DD

## Context
## Decision
## Consequences
## Alternatives considered
```
