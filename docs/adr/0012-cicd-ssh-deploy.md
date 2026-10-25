# ADR-0012: Two-stage CI/CD: checks on main, approved deploy that builds on the VMs

- Status: Proposed
- Date: 2026-10-26
- Amends: [roadmap Phase 6](../roadmap.md#phase-6-prod-environment-and-cicd) ("build and push images")

## Context

Prod is two VMs running Docker Compose ([ADR-0009](0009-environments.md)). The team wants every merge to `main` checked automatically, but code to reach prod only after a person approves. Job and connection files are different: a merged job file should become a DAG without a manual step (roadmap Phase 6). There is no container registry yet, and the VMs don't exist yet, so the pipeline has to be ready before it can deploy anything.

## Decision

**Stage 1, CI** (`.github/workflows/ci.yml`), on every pull request and push to `main`:

- Python: ruff, mypy, compile check of the Airflow files, and validation of every file in `pipelines/` with the API's own rules (`python -m ingestion.validate`).
- Web UI: typecheck, lint and production build.
- Docker: shell scripts parse, every Compose file passes `docker compose config`, every image builds. Nothing is pushed.

**Stage 2, Deploy** (`.github/workflows/deploy.yml`), after CI succeeds on a push to `main`:

- The workflow compares the target commit with the commit VM 1 runs.
- Code changed: GitHub environment `production` with required reviewers. After one approval, VM 1 and then VM 2 run `infrastructure/prod/deploy.sh` over SSH: `git checkout <sha>`, `docker compose build --pull`, `up -d --wait`, then prune dangling images and build cache older than a week. The script is taken from the target commit (`git show <sha>:...`), not from the old checkout.
- Only `pipelines/` changed: environment `production-pipelines` without reviewers; VM 1 checks out the commit and resyncs the Airflow pools. Airflow parses the new files by itself.
- A manual run deploys any commit and can rebuild without the layer cache.
- The whole workflow is off until the repository variable `PROD_DEPLOY_ENABLED` is `true`.

Images are built **on the VMs** from the checkout; no registry. GitHub holds only SSH access; application secrets stay in files on the VMs (later Key Vault).

## Consequences

- No registry to run or pay for, and the deployed code is exactly a Git commit. Rollback is a manual run with the previous commit.
- Each VM builds its own images, so a deploy takes minutes (PyFlink on the JobManager image) and needs disk for the build cache; the prune step bounds it. VM 2 only builds the TaskManager image.
- Images in prod are not the bytes CI built; CI proves they build, the VM builds them again. Moving to a registry later (build once in CI, `docker compose pull` on the VMs) changes only the build step of `deploy.sh` and CI.
- GitHub-hosted runners need SSH access to the VMs. If that isn't allowed, a self-hosted runner on VM 1 replaces SSH for VM 1 and reaches VM 2 on the private network.
- The Web UI writes job files on VM 1 until open question 7 is decided; `deploy.sh` refuses to check out over uncommitted changes rather than lose them.
- Restarting VM 2 fails running Flink jobs; Airflow retries the runs (Phase 5). Deploys should avoid the main schedule window.

## Alternatives considered

- **Build in CI, push to a registry (GHCR or ACR), pull on the VMs.** Faster deploys and identical images, but needs a registry and credentials on the VMs. Kept as the next step once deploy time matters.
- **Deploy on every merge without approval.** Rejected: the team wants a person to approve code changes to prod.
- **Self-hosted runner on the VMs from the start.** Possible, and the fallback when SSH from GitHub is blocked; SSH keeps the VMs free of a long-running agent.
