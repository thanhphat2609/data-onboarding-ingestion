#!/usr/bin/env bash
# Prepares non-prod: creates .env with random secrets and the shared run directory.
# Safe to run again; existing values are kept.
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  cp .env.example .env
  while grep -qE '^[A-Z0-9_]+=__GENERATE__$' .env; do
    key=$(grep -m1 -E '^[A-Z0-9_]+=__GENERATE__$' .env | cut -d= -f1)
    if [[ "$key" == "AIRFLOW_FERNET_KEY" ]]; then
      # Fernet keys are 32 random bytes, URL-safe base64.
      value=$(openssl rand -base64 32 | tr '+/' '-_')
    else
      # Prefix guarantees SQL Server password complexity.
      value="Aa1-$(openssl rand -hex 16)"
    fi
    sed -i "s|^${key}=__GENERATE__$|${key}=${value}|" .env
  done
  echo "Created infrastructure/non-prod/.env"
else
  echo "Keeping existing infrastructure/non-prod/.env"
fi

# Written by Airflow (uid 50000), read by the Flink JobManager.
mkdir -p data/runs
chmod 777 data/runs
