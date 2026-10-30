#!/usr/bin/env bash
# Prepares non-prod: .env files with random secrets (the platform's, and each example source's), sources.env (the
# source secrets the platform reads, like prod's GitHub secrets), the shared run directory and the Docker networks.
# Safe to run again; existing values are kept.
set -euo pipefail

cd "$(dirname "$0")"

# Creates <file> from <file>.example, or appends the keys added to the example since; then fills __GENERATE__.
prepare_env() {
  local file=$1 example=$1.example
  if [[ ! -f "$file" ]]; then
    cp "$example" "$file"
    echo "Created infrastructure/non-prod/${file}"
  else
    echo "Keeping existing infrastructure/non-prod/${file}"
    while IFS= read -r line; do
      key=${line%%=*}
      if ! grep -qE "^${key}=" "$file"; then
        printf '%s\n' "$line" >> "$file"
        echo "Added ${key} to ${file}"
      fi
    done < <(grep -E '^[A-Z0-9_]+=' "$example")
  fi

  while grep -qE '^[A-Z0-9_]+=__GENERATE__$' "$file"; do
    key=$(grep -m1 -E '^[A-Z0-9_]+=__GENERATE__$' "$file" | cut -d= -f1)
    if [[ "$key" == "AIRFLOW_FERNET_KEY" ]]; then
      # Fernet keys are 32 random bytes, URL-safe base64.
      value=$(openssl rand -base64 32 | tr '+/' '-_')
    else
      # Prefix guarantees SQL Server password complexity.
      value="Aa1-$(openssl rand -hex 16)"
    fi
    sed -i "s|^${key}=__GENERATE__$|${key}=${value}|" "$file"
  done
}

prepare_env .env
for example in example-sources/*/.env.example; do
  prepare_env "${example%.example}"
done

# sources.env: every key of sources.env.example that is still empty gets its value from the example sources' .env
# files (in prod: a GitHub secret per key, written by the Deploy workflow). Values you set yourself are kept.
touch sources.env
chmod 600 sources.env
while IFS= read -r key; do
  if ! grep -qE "^${key}=.+" sources.env; then
    value=$(cat example-sources/*/.env | grep -m1 -E "^${key}=" | cut -d= -f2- || true)
    sed -i "/^${key}=/d" sources.env
    printf '%s=%s\n' "$key" "$value" >> sources.env
    if [[ -n "$value" ]]; then echo "Set ${key} in sources.env"; fi
  fi
done < <(grep -oE '^[A-Z0-9_]+' sources.env.example)

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
# The platform and the example sources (example-sources/) meet on this network.
if ! docker network inspect ingestion-sources >/dev/null 2>&1; then
  docker network create ingestion-sources >/dev/null
  echo "Created Docker network ingestion-sources"
fi
