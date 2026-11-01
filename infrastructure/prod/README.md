# Prod

Two VMs ([ADR-0009](../../docs/adr/0009-environments.md)), deployed by GitHub Actions ([ADR-0012](../../docs/adr/0012-cicd-ssh-deploy.md)). Airflow runs on VM 1 too, deployed by [data-onboarding-orchestration](https://github.com/thanhphat2609/data-onboarding-orchestration) ([ADR-0016](../../docs/adr/0016-airflow-moves-to-orchestration.md)). **Draft until the VMs exist** (roadmap Phase 6): the Compose files follow the ADRs but have not run yet.

```
vm1/docker-compose.yml   Web UI, Ingestion API, Flink JobManager, Redpanda
vm2/docker-compose.yml   Flink TaskManager (host network)
deploy.sh                Run on a VM by the Deploy workflow: checkout <sha>, build, up, prune
render_env.py            Used by the Deploy workflow: keys of the *.env.example files + GitHub secrets/variables -> .env, sources.env
vm1/.env.example, vm1/sources.env.example, vm2/.env.example   every prod setting, by name (ADR-0013)
```

## How a change reaches prod

| Stage | Trigger | What runs |
|---|---|---|
| 1. CI | Pull request or push to `main` | Ruff, mypy, YAML file validation, UI typecheck/lint/build, Compose files, every image built (not pushed) |
| 2a. Deploy (approval) | Someone runs **Actions → Deploy → Run workflow** on `main` | Checks the commit is on `main` with a green CI run; writes VM 1's `.env` and `sources.env` and VM 2's `.env` from the secrets and variables and checks them with `docker compose config`; then VM 1 and VM 2: the files replaced, `git checkout <sha>`, `docker compose build --pull`, `up -d --wait`, prune images and week-old build cache |
| 2b. Pipelines sync | CI green on a push to `main` that changed only `pipelines/` | VM 1: `git checkout <sha>`, no rebuild; Airflow mounts the checkout and picks up the files and pools by itself |

Separate from the stages: `.github/workflows/delete-merged-branch.yml` deletes a pull request's branch once it is merged. Run it by hand once (Actions → Delete merged branches → Run workflow) for branches merged before it existed.

**Approving a deploy** = running the workflow: Actions → Deploy → Run workflow → branch `main` → optionally a commit (`sha`, default the latest `main`) and `no_cache` → Run. A commit without a green CI run is refused. Anyone with write access to the repository can run it. When code changed, the push itself deploys nothing; the CI-triggered Deploy run only notes that a manual run is needed.

The build reuses the Docker layer cache (rebuilding PyFlink every time takes minutes) but always pulls newer base images; old images and build cache are pruned after each deploy. Use `no_cache` when a build looks stale.

## GitHub setup (Settings of this repository)

**Every prod setting lives here** ([ADR-0013](../../docs/adr/0013-prod-settings-in-github.md)); nothing is edited on the VMs. Each full deploy writes `vm1/.env`, `vm1/sources.env` and `vm2/.env` on the VMs, one line per key of the matching `*.env.example`, from the secret or variable of the **same name** ([render_env.py](render_env.py)). It stops before touching a VM when a required secret is missing, when a password-like setting was saved as a variable, or when `docker compose config` rejects the result. To change a setting: edit it here, then run **Actions → Deploy** (a `pipelines/`-only sync doesn't rewrite the files).

A setting you can't fill in yet (e.g. the Flink addresses before the VMs exist): set it to **`TODO`**. The deploy stops while any secret or variable of this repository is still `TODO`, naming each one, so a placeholder never reaches a VM. Don't use another placeholder such as `1`: it would be deployed as a real value.

Secrets and variables are per repository: set them here, in data-onboarding-agent **and** in data-onboarding-orchestration. All three can use the same SSH key and deploy user. One value is shared: this repository's `AIRFLOW_ADMIN_PASSWORD` secret = the orchestration repository's `AIRFLOW_ADMIN_PASSWORD` secret.

### Secrets (Settings → Secrets and variables → Actions → New repository secret)

| Name | Example | What it is |
|---|---|---|
| `PROD_SSH_PRIVATE_KEY` | `-----BEGIN OPENSSH PRIVATE KEY-----`<br>`b3BlbnNzaC1rZXktdjEAAAAA...`<br>`-----END OPENSSH PRIVATE KEY-----` | Whole content of the private key file, including the BEGIN/END lines. Made once for CI only: `ssh-keygen -t ed25519 -C github-deploy -f deploy_key -N ""`; `deploy_key.pub` goes into `/home/deploy/.ssh/authorized_keys` on both VMs |
| `PROD_SSH_KNOWN_HOSTS` | `20.198.10.15 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK...`<br>`20.198.10.16 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM...` | Output of `ssh-keyscan -t ed25519 20.198.10.15 20.198.10.16` (one line per VM); compare the fingerprints with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on each VM |
| `PROD_SSH_USER` | `deploy` | Linux user on the VMs, member of the `docker` group |
| `PROD_VM1_HOST` | `20.198.10.15` or `vm1.dataplatform.example.com` | Address of VM 1 that GitHub's runners can reach |
| `PROD_VM2_HOST` | `20.198.10.16` or `vm2.dataplatform.example.com` | Address of VM 2 that GitHub's runners can reach |

App settings (written into the files on the VMs):

| Name | Required | What it is |
|---|---|---|
| `AIRFLOW_ADMIN_PASSWORD` | yes | Airflow login `admin`, which the Ingestion API uses; same value as in data-onboarding-orchestration |
| `CRM_SQLSERVER_RO_PASSWORD`, `SALES_POSTGRES_RO_PASSWORD`, `SHOP_MYSQL_RO_PASSWORD` | yes | Source passwords for `env://` references (`vm1/sources.env`). Every key of [vm1/sources.env.example](vm1/sources.env.example) is required: a new connection with a new `env://` reference adds a line there and a secret here |

### Variables (same page → Variables tab → New repository variable)

| Name | Example | What it is |
|---|---|---|
| `PROD_DEPLOY_ENABLED` | `true` | Anything else (or unset) turns the Deploy workflow off. Leave unset until the VMs are ready |
| `PROD_REPO_DIR` | `/opt/data-onboarding-ingestion` | Where the repository is cloned on both VMs (this is also the default) |
| `PROD_SSH_PORT` | `22` | SSH port of the VMs (default `22`) |
| `FLINK_JOBMANAGER_ADDRESS` | `10.0.0.4` | **Required.** Private address of VM 1 as seen from VM 2 (used on both VMs) |
| `FLINK_TASKMANAGER_ADDRESS` | `10.0.0.5` | **Required.** Private address of VM 2 as seen from VM 1 |
| `UI_PORT`, `AIRFLOW_PUBLIC_URL`, `FLINK_PUBLIC_URL`, `JOBMANAGER_MEMORY`, `TASKMANAGER_SLOTS`, `TASKMANAGER_MEMORY` | | Optional; empty = the default in the Compose files |

Variables are not secret: they show in the logs. Anything secret goes in Secrets.

### Branch protection (Settings → Rules → Rulesets, or Branches)

For `main`: require a pull request before merging, and require the status checks `Python (lint, types, YAML files)`, `Web UI (types, lint, build)` and `Compose files and image builds`.

Application secrets (source passwords, the Airflow login) are GitHub secrets until Key Vault (`kv://`, Phase 6) replaces the source passwords. Don't edit `.env` or `sources.env` on a VM: the next deploy replaces them (mode `600`, ignored by Git).

## VM setup (once per VM)

1. Docker Engine with the Compose plugin; a `deploy` user in the `docker` group with the CI public key.
2. Clone the repository to `PROD_REPO_DIR` as `deploy`. For a private repository, add a read-only **deploy key** (repository Settings → Deploy keys) on each VM.
3. No `.env` to write by hand: set the secrets and variables above; the first deploy writes `vm1/.env`, `vm1/sources.env` and `vm2/.env`.
4. VM 1: deploy the data-onboarding-agent stack first (agent app, shared PostgreSQL, SearXNG; its own `infrastructure/prod/README.md`); it creates the `data-platform` network and the PostgreSQL server (ADR-0011). Then this repository, then data-onboarding-orchestration, whose Airflow needs this stack's volumes and a checkout next to this one. The agent's ports are localhost-only (7860, 5432), so they don't clash with this stack's 80, 8081, 6123 and 6124 or Airflow's 8080.
5. Firewall: VM 2 → VM 1 on 6123-6124; VM 1 → VM 2 on 6121-6122; users → VM 1 on the UI port (Airflow 8080 and Flink 8081 only from admin networks); GitHub runners → both VMs on SSH.

If the VMs can't accept SSH from the internet, run a self-hosted GitHub runner on VM 1 instead and point the jobs at it (`runs-on: [self-hosted, prod]`).

## Open points (Phase 6)

- The Web UI writes job files on VM 1 without a commit until [ADR-0014](../../docs/adr/0014-prod-save-flow.md) (proposed: a pull request per save) is built. `deploy.sh` stops when the checkout has uncommitted changes, so nothing is overwritten.
- **New connection with a new password** (ADR-0014): its pull request adds `NAME=` to `vm1/sources.env.example`; add the secret `NAME` here, merge, then run **Actions → Deploy** once. Until Key Vault (`kv://`) replaces this step.
- TLS and Entra ID SSO in front of the UI; Airflow keeps one admin user until then.
- ADLS identity for the TaskManagers and `kv://` secrets.
