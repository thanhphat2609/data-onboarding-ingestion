#!/usr/bin/env bash
# Prepares non-prod: creates .env with random secrets and the shared run directory.
# Safe to run again; existing values are kept.
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created infrastructure/non-prod/.env"
else
  echo "Keeping existing infrastructure/non-prod/.env"
  # Variables added to .env.example since this .env was created (for example new test sources) are appended.
  while IFS= read -r line; do
    key=${line%%=*}
    if ! grep -qE "^${key}=" .env; then
      printf '%s\n' "$line" >> .env
      echo "Added ${key} to .env"
    fi
  done < <(grep -E '^[A-Z0-9_]+=' .env.example)
fi

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

# Written by Airflow (uid 50000), read by the Flink JobManager.
mkdir -p data/runs
chmod 777 data/runs
# Phase 2 spike output, written by the Flink TaskManager (uid 9999).
mkdir -p data/spike-out
chmod 777 data/spike-out

# Airflow joins the platform network (ADR-0011). The data-onboarding-agent stack creates it when it runs on
# this host; create it here for a standalone non-prod (COMPOSE_PROFILES=local-db).
if ! docker network inspect data-platform >/dev/null 2>&1; then
  docker network create data-platform >/dev/null
  echo "Created Docker network data-platform"
fi
