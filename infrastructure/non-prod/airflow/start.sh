#!/usr/bin/env bash
# Non-prod Airflow: migrate the database, create pools from connection files, run all components.
set -euo pipefail

airflow db migrate
python /opt/airflow/scripts/sync_pools.py > /tmp/ingestion-pools.json
airflow pools import /tmp/ingestion-pools.json
exec airflow standalone
