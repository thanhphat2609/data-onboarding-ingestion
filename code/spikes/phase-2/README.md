# Phase 2 spikes

Throwaway jobs that prove the risky building blocks on Flink 1.20 before the runner is built on them (roadmap Phase 2; the first cut of the runner is in [code/runner/](../../runner/README.md) and is what these spikes confirm). Results go to [docs/spikes/phase-2.md](../../../docs/spikes/phase-2.md); the code here is not reused as is.

Mounted read-only on the JobManager at `/opt/spikes`. Output goes to `infrastructure/non-prod/data/spike-out/` (`/opt/ingestion/spike-out` in the Flink containers).

## Setup (in the Codespace)

```bash
git pull
bash infrastructure/non-prod/bootstrap.sh            # .env files, sources.env, the ingestion-sources network
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build
docker compose -f infrastructure/non-prod/example-sources/docker-compose.yml up -d   # the test sources
bash infrastructure/non-prod/example-sources/seed-large.sh   # optional: 10M rows in orders (sqlserver postgres mysql)
alias jm='docker compose -f infrastructure/non-prod/docker-compose.yml exec flink-jobmanager'
```

## Runs

| What | Command |
|---|---|
| Table mode, small table | `jm flink run -py /opt/spikes/phase-2/jdbc_to_parquet.py --source postgres --table customers` |
| Partitioned scan, 10M rows | `jm flink run -py /opt/spikes/phase-2/jdbc_to_parquet.py --source mysql --table orders --partitions 4` |
| Query mode (JOIN + CTE as a derived table) | `jm flink run -py /opt/spikes/phase-2/jdbc_to_parquet.py --source sqlserver --mode query` |
| Submit through REST with PythonDriver | `jm python /opt/spikes/phase-2/submit_rest.py /opt/spikes/phase-2/jdbc_to_parquet.py --source sqlserver` |
| API landing topic → Parquet, bounded by offsets (ADR-0015) | `jm flink run -py /opt/spikes/phase-2/kafka_to_parquet.py --topic ingest.shop-api-orders-daily --start <start> --end <end>` (offsets from the `fetch` log of `ingest__shop-api-orders-daily`, created as in [example-sources/README.md](../../../infrastructure/non-prod/example-sources/README.md)) |
| Read the output back | `jm python /opt/spikes/phase-2/check_parquet.py /opt/ingestion/spike-out/postgres/customers` |
| Write to ADLS (needs credentials) | add `--out abfss://data-onboarding-ingestion@<account>.dfs.core.windows.net/spikes` |

**ADLS Gen2 for the spikes:** a storage account with **hierarchical namespace enabled** (it can't be turned on later without a migration), and a container named `data-onboarding-ingestion`. The account name itself allows only 3-24 lowercase letters and digits, no hyphens (for example `stdataonboardingdev`); the hyphenated name fits the container. Jobs then set `container: data-onboarding-ingestion` in the `adls_parquet` sink (its default is `raw`).

`--source` is `sqlserver`, `postgres` or `mysql`. Each run prints a `SPIKE ... seconds=` line for the throughput table. BigQuery and the Delta commit get their own scripts once the BigQuery project and the ADLS account are available.
