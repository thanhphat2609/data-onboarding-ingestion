#!/usr/bin/env bash
# Non-prod Airflow: wait for the metadata DB, migrate it, create pools from connection files, run all components.
set -euo pipefail

# The shared PostgreSQL server belongs to another Compose project, so depends_on can't wait for it (ADR-0011).
for attempt in $(seq 1 60); do
  airflow db check >/dev/null 2>&1 && break
  if [[ "$attempt" == 60 ]]; then
    echo "Metadata DB not reachable after 5 minutes. Start the data-onboarding-agent stack first, or set COMPOSE_PROFILES=local-db in .env." >&2
    exit 1
  fi
  echo "Waiting for the metadata DB (${attempt}/60)..."
  sleep 5
done

airflow db migrate
python /opt/airflow/scripts/sync_pools.py > /tmp/ingestion-pools.json
airflow pools import /tmp/ingestion-pools.json
exec airflow standalone
