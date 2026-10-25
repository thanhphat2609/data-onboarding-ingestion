#!/usr/bin/env bash
# Deploys one prod VM to a commit (ADR-0012). Run on the VM, from the repository checkout, by the Deploy workflow:
#   git -C <repo> fetch --prune origin && git -C <repo> show <sha>:infrastructure/prod/deploy.sh | bash -s -- ...
# so the script of the target commit runs, not the one currently checked out.
#
# Usage: deploy.sh <vm1|vm2> <sha> [--pipelines-only] [--no-cache]
#   --pipelines-only  only move pipelines/ to <sha> and resync Airflow pools; no rebuild, no restart (VM 1)
#   --no-cache        rebuild every image layer (default: reuse the cache, but always pull newer base images)
set -euo pipefail

vm="${1:?vm1 or vm2}"
sha="${2:?commit sha}"
shift 2
pipelines_only=false
no_cache=()
for arg in "$@"; do
  case "$arg" in
    --pipelines-only) pipelines_only=true ;;
    --no-cache) no_cache=(--no-cache) ;;
    *) echo "Unknown option $arg" >&2; exit 2 ;;
  esac
done

repo="${PROD_REPO_DIR:-$(pwd)}"
cd "$repo"
compose=(docker compose -f "infrastructure/prod/${vm}/docker-compose.yml")

# Until open question 7 is decided, the Web UI writes job files on VM 1 without committing them. A checkout must
# never overwrite them: stop and let a person commit or discard the changes first.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "::error::Uncommitted changes in ${repo} on ${vm}; commit or discard them, then re-run the deploy:" >&2
  git status --short >&2
  exit 1
fi

echo "Deploying ${vm}: $(git rev-parse --short HEAD) -> ${sha:0:7}"
git checkout --quiet --detach "$sha"

if [[ "$pipelines_only" == true ]]; then
  # The DAG processor picks up the files by itself; pools come from the connection files.
  "${compose[@]}" exec -T airflow-scheduler bash -c \
    'python /opt/airflow/scripts/sync_pools.py > /tmp/pools.json && airflow pools import /tmp/pools.json'
  echo "Pipelines at ${sha:0:7}"
  exit 0
fi

"${compose[@]}" build --pull "${no_cache[@]}"
"${compose[@]}" up -d --remove-orphans --wait --wait-timeout 600

# Keep the disk in check: dangling images from earlier builds, and build cache unused for a week.
docker image prune -f
docker builder prune -f --filter until=168h
"${compose[@]}" ps
echo "${vm} at ${sha:0:7}"
