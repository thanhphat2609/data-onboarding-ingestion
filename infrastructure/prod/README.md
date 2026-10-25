# Prod

Two VMs ([ADR-0009](../../docs/adr/0009-environments.md)), deployed by GitHub Actions ([ADR-0012](../../docs/adr/0012-cicd-ssh-deploy.md)). **Draft until the VMs exist** (roadmap Phase 6): the Compose files follow the ADRs but have not run yet.

```
vm1/docker-compose.yml   Web UI, Ingestion API, Airflow (init, api-server, scheduler, dag-processor, triggerer), Flink JobManager
vm2/docker-compose.yml   Flink TaskManager (host network)
deploy.sh                Run on a VM by the Deploy workflow: checkout <sha>, build, up, prune
```

## How a change reaches prod

| Stage | Trigger | What runs | Approval |
|---|---|---|---|
| 1. CI | Pull request or push to `main` | Ruff, mypy, YAML file validation, UI typecheck/lint/build, Compose files, every image built (not pushed) | No |
| 2a. Deploy | CI green on `main`, code changed | VM 1 then VM 2: `git checkout <sha>`, `docker compose build --pull`, `up -d --wait`, prune images and week-old build cache | **Yes**, environment `production` |
| 2b. Pipelines sync | CI green on `main`, only `pipelines/` changed | VM 1: `git checkout <sha>` and pool sync; Airflow picks up the files by itself | No, environment `production-pipelines` |
| Manual | Actions → Deploy → Run workflow | Like 2a for any commit; option `no_cache` rebuilds every layer | Yes |

The build reuses the Docker layer cache (rebuilding PyFlink every time takes minutes) but always pulls newer base images; old images and build cache are pruned after each deploy. Use `no_cache` when a build looks stale.

## GitHub setup (Settings of this repository)

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Name | Value |
|---|---|
| `PROD_SSH_PRIVATE_KEY` | Private key of a key pair made for CI only (`ssh-keygen -t ed25519 -C github-deploy -f deploy_key`); the public key goes into `~/.ssh/authorized_keys` of the deploy user on both VMs |
| `PROD_SSH_KNOWN_HOSTS` | Output of `ssh-keyscan -p <port> <vm1> <vm2>`, checked against the VMs' real host keys |
| `PROD_SSH_USER` | Deploy user on the VMs, for example `deploy` |
| `PROD_VM1_HOST` | Address of VM 1 reachable from GitHub runners |
| `PROD_VM2_HOST` | Address of VM 2 reachable from GitHub runners |

**Variables** (same page → Variables):

| Name | Value |
|---|---|
| `PROD_DEPLOY_ENABLED` | `true` once the VMs are ready; until then the Deploy workflow does nothing |
| `PROD_REPO_DIR` | Checkout path on the VMs (default `/opt/data-onboarding-ingestion`) |
| `PROD_SSH_PORT` | SSH port (default `22`) |

**Environments** (Settings → Environments):

| Name | Settings |
|---|---|
| `production` | Required reviewers: the people who approve deploys; deployment branches: `main` only |
| `production-pipelines` | No reviewers; deployment branches: `main` only |

**Branch protection** for `main` (Settings → Branches or Rulesets): require a pull request and the CI checks `Python (lint, types, YAML files)`, `Web UI (types, lint, build)` and `Compose files and image builds`.

Application secrets (database passwords, source passwords, Airflow keys) are **not** GitHub secrets: they live in `.env` and `sources.env` on the VMs, and later in Key Vault (`kv://`).

## VM setup (once per VM)

1. Docker Engine with the Compose plugin; a `deploy` user in the `docker` group with the CI public key.
2. Clone the repository to `PROD_REPO_DIR` as `deploy`. For a private repository, add a read-only **deploy key** (repository Settings → Deploy keys) on each VM.
3. Copy `infrastructure/prod/<vm>/.env.example` to `.env` (and on VM 1 `sources.env.example` to `sources.env`) and fill in the values.
4. VM 1: start the data-onboarding-agent stack first; it creates the `data-platform` network and the shared PostgreSQL server (ADR-0011).
5. Firewall: VM 2 → VM 1 on 6123-6124; VM 1 → VM 2 on 6121-6122; users → VM 1 on the UI port (Airflow 8080 and Flink 8081 only from admin networks); GitHub runners → both VMs on SSH.

If the VMs can't accept SSH from the internet, run a self-hosted GitHub runner on VM 1 instead and point the jobs at it (`runs-on: [self-hosted, prod]`).

## Open points (Phase 6)

- The Web UI writes job files on VM 1 without a commit (open question 7). `deploy.sh` stops when the checkout has uncommitted changes, so nothing is overwritten; the UI save flow in prod must be decided before go-live.
- TLS and Entra ID SSO in front of the UI; Airflow keeps one admin user until then.
- ADLS identity for the TaskManagers and `kv://` secrets.
