#!/bin/sh
# Runs once, on the first start of an empty data volume.
# One instance, two databases: Airflow metadata and the platform database (architecture §3.4).
set -eu

psql -v ON_ERROR_STOP=1 --username postgres <<EOSQL
CREATE ROLE airflow LOGIN PASSWORD '${AIRFLOW_DB_PASSWORD}';
CREATE DATABASE airflow OWNER airflow;
CREATE ROLE platform LOGIN PASSWORD '${PLATFORM_DB_PASSWORD}';
CREATE DATABASE platform OWNER platform;
EOSQL
