#!/usr/bin/env bash
# Deploys one prod VM to a commit (ADR-0012). Run on the VM, from the repository checkout, by the Deploy workflow:
#   git -C <repo> fetch --prune origin && git -C <repo> show <sha>:infrastructure/prod/deploy.sh | bash -s -- ...
# so the script of the target commit runs, not the one currently checked out.
#
# Usage: deploy.sh <vm1|vm2> <sha> [--no-cache]
#   --no-cache        rebuild every image layer (default: reuse the cache, but always pull newer base images)
set -euo pipefail

vm="${1:?vm1 or vm2}"
sha="${2:?commit sha}"
shift 2
no_cache=()
for arg in "$@"; do
  case "$arg" in
    --no-cache) no_cache=(--no-cache) ;;
    *) echo "Unknown option $arg" >&2; exit 2 ;;
  esac
done

repo="${PROD_REPO_DIR:-$(pwd)}"
cd "$repo"
compose=(docker compose -f "infrastructure/prod/${vm}/docker-compose.yml")

# A checkout must never overwrite local changes: stop and let a person commit or discard them first.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "::error::Uncommitted changes in ${repo} on ${vm}; commit or discard them, then re-run the deploy:" >&2
  git status --short >&2
  exit 1
fi

echo "Deploying ${vm}: $(git rev-parse --short HEAD) -> ${sha:0:7}"
git checkout --quiet --detach "$sha"

"${compose[@]}" build --pull "${no_cache[@]}"
"${compose[@]}" up -d --remove-orphans --wait --wait-timeout 600

# Keep the disk in check: dangling images from earlier builds, and build cache unused for a week.
docker image prune -f
docker builder prune -f --filter until=168h
"${compose[@]}" ps
echo "${vm} at ${sha:0:7}"
