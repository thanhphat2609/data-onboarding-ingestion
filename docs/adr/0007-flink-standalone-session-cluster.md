# ADR-0007: Apache Flink 1.20 standalone session cluster on VMs

- Status: Proposed
- Date: 2026-10-22
- Supersedes: [ADR-0001](0001-flink-on-kubernetes-operator.md)

## Context

ADR-0001 assumed an AKS cluster and the Flink Kubernetes Operator, with one Flink cluster per run. Kubernetes is not part of the target environment: production runs on plain virtual machines, and development runs in GitHub Codespaces ([ADR-0009](0009-environments.md)). Jobs are still bounded batch snapshots of very different sizes, submitted by many users.

## Decision

- Keep **Apache Flink 1.20**, for the reason given in ADR-0001: the connectors this platform depends on (`flink-connector-jdbc`, the BigQuery connector, filesystem/Parquet) target the 1.x API.
- Run Flink as a **standalone session cluster** started with Docker Compose:
  - **VM 1** runs the **JobManager**, next to Airflow, the Ingestion API and the Web UI.
  - **VM 2** runs one or more **TaskManagers**. Capacity grows by adding TaskManagers or more VMs, not by changing the jobs.
  - In non-prod every component runs in one Docker Compose project.
- **Submit runs through the Flink REST API.** The runner is a PyFlink script ([ADR-0010](0010-pyflink-runner.md)) started through the `flink-python` JAR shipped with Flink, uploaded once (`POST /jars/upload`). Each run is one Flink job started with `POST /jars/{jar_id}/run`, entry class `PythonDriver` and the arguments `-py <runner>/main.py --job <path> --run-id <run_id> --ingest-date <date>`.
- The runner reads the **job and connection files** (and the templates) as merged, from a read-only mount on the JobManager: the files Airflow runs, on VM 1 (the Web UI's working copy `pipelines/` in non-prod). There is no resolved spec and no run directory to share (updated 2026-11-02, [ADR-0010](0010-pyflink-runner.md)).
- **Secret values never appear in program arguments or in the Flink web UI.** The runner resolves secret references when it builds the job graph ([architecture §3.7](../architecture.md#37-secrets-and-identity)).
- No JobManager high availability in v1. A JobManager restart fails the running jobs, and Airflow retries the affected runs.

## Consequences

- No Kubernetes to provision or operate. Run start-up is fast because the cluster is already running.
- Runs share TaskManager slots, so a heavy run can delay others. Admission control moves to Airflow: pools limit concurrent runs per connection and the total number of slots requested ([ADR-0008](0008-airflow-dag-per-job.md)).
- TaskManager size is fixed per cluster. `runtime.taskmanager` is removed from `IngestionJob`; a job only chooses its parallelism, capped by the available slots.
- A TaskManager crash fails every run that has tasks on it. Retries restart the whole run, which is safe because output stays in staging until it is published ([ADR-0004](0004-lake-layout-and-delta-commit.md)).
- The JobManager keeps finished jobs only for `jobstore.expiration-time` (1 hour by default). Longer job history needs the Flink History Server, and Airflow and the `runs` table keep the run record.
- VM 2 must reach the JobManager RPC and blob server ports on VM 1, and TaskManager ports must be fixed ranges so firewalls can be configured.

## Alternatives considered

- **Flink Kubernetes Operator, one cluster per run** (ADR-0001): best isolation, but requires Kubernetes, which is not available.
- **One application-mode cluster per run on the VMs** (a container started per run): isolation without Kubernetes, but the platform would have to schedule containers across VMs itself.
- **Flink on YARN**: needs a Hadoop cluster that does not exist.
