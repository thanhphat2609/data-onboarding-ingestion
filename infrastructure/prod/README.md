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

Secrets and variables are per repository: set them here **and** in data-onboarding-agent. Both repositories can use the same SSH key and deploy user.

### Secrets (Settings → Secrets and variables → Actions → New repository secret)

| Name | Example | What it is |
|---|---|---|
| `PROD_SSH_PRIVATE_KEY` | `-----BEGIN OPENSSH PRIVATE KEY-----`<br>`b3BlbnNzaC1rZXktdjEAAAAA...`<br>`-----END OPENSSH PRIVATE KEY-----` | Whole content of the private key file, including the BEGIN/END lines. Made once for CI only: `ssh-keygen -t ed25519 -C github-deploy -f deploy_key -N ""`; `deploy_key.pub` goes into `/home/deploy/.ssh/authorized_keys` on both VMs |
| `PROD_SSH_KNOWN_HOSTS` | `20.198.10.15 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK...`<br>`20.198.10.16 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM...` | Output of `ssh-keyscan -t ed25519 20.198.10.15 20.198.10.16` (one line per VM); compare the fingerprints with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on each VM |
| `PROD_SSH_USER` | `deploy` | Linux user on the VMs, member of the `docker` group |
| `PROD_VM1_HOST` | `20.198.10.15` or `vm1.dataplatform.example.com` | Address of VM 1 that GitHub's runners can reach |
| `PROD_VM2_HOST` | `20.198.10.16` or `vm2.dataplatform.example.com` | Address of VM 2 that GitHub's runners can reach |

### Variables (same page → Variables tab → New repository variable)

| Name | Example | What it is |
|---|---|---|
| `PROD_DEPLOY_ENABLED` | `true` | Anything else (or unset) turns the Deploy workflow off. Leave unset until the VMs are ready |
| `PROD_REPO_DIR` | `/opt/data-onboarding-ingestion` | Where the repository is cloned on both VMs (this is also the default) |
| `PROD_SSH_PORT` | `22` | SSH port of the VMs (default `22`) |

Variables are not secret: they show in the logs. Anything secret goes in Secrets.

### Environments (Settings → Environments → New environment)

An environment is a named deployment target with its own protection rules. A job that says `environment: production` stops and waits until one of the required reviewers clicks **Review deployments → Approve** on the workflow run. That is the approval of stage 2.

| Name | Settings to tick |
|---|---|
| `production` | **Required reviewers**: the people who may approve deploys (one approval is enough). **Prevent self-review** if the person who pushes should not approve their own change. **Deployment branches and tags**: *Selected branches* → `main` |
| `production-pipelines` | No reviewers (job and connection files sync on their own). **Deployment branches and tags**: *Selected branches* → `main` |

### Branch protection (Settings → Rules → Rulesets, or Branches)

For `main`: require a pull request before merging, and require the status checks `Python (lint, types, YAML files)`, `Web UI (types, lint, build)` and `Compose files and image builds`.

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
