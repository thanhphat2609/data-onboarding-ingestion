# Phase 2 spikes

Throwaway jobs that prove the risky building blocks on Flink 1.20 before the runner is written (roadmap Phase 2). Results go to [docs/spikes/phase-2.md](../../../docs/spikes/phase-2.md); the code here is not reused as is.

Mounted read-only on the JobManager at `/opt/spikes`. Output goes to `infrastructure/non-prod/data/spike-out/` (`/opt/ingestion/spike-out` in the Flink containers).

## Setup (in the Codespace)

```bash
git pull
bash infrastructure/non-prod/bootstrap.sh            # adds the new source passwords to .env
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build
bash infrastructure/non-prod/seed-large.sh           # optional: 10M rows in orders (sqlserver postgres mysql)
alias jm='docker compose -f infrastructure/non-prod/docker-compose.yml exec flink-jobmanager'
```

## Runs

| What | Command |
|---|---|
| Table mode, small table | `jm flink run -py /opt/spikes/phase-2/jdbc_to_parquet.py --source postgres --table customers` |
| Partitioned scan, 10M rows | `jm flink run -py /opt/spikes/phase-2/jdbc_to_parquet.py --source mysql --table orders --partitions 4` |
| Query mode (JOIN + CTE as a derived table) | `jm flink run -py /opt/spikes/phase-2/jdbc_to_parquet.py --source sqlserver --mode query` |
| Submit through REST with PythonDriver | `jm python /opt/spikes/phase-2/submit_rest.py /opt/spikes/phase-2/jdbc_to_parquet.py --source sqlserver` |
| Read the output back | `jm python /opt/spikes/phase-2/check_parquet.py /opt/ingestion/spike-out/postgres/customers` |
| Write to ADLS (needs credentials) | add `--out abfss://<container>@<account>.dfs.core.windows.net/spikes` |

`--source` is `sqlserver`, `postgres` or `mysql`. Each run prints a `SPIKE ... seconds=` line for the throughput table. BigQuery and the Delta commit get their own scripts once the BigQuery project and the ADLS account are available.
