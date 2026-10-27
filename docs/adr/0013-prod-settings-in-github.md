# ADR-0013: Every prod setting in GitHub secrets and variables; the Deploy workflow writes the files on the VMs

- Status: Proposed
- Date: 2026-10-27
- Amends: [ADR-0012](0012-cicd-ssh-deploy.md) ("application secrets stay in files on the VMs")

## Context

ADR-0012 kept GitHub to SSH access only: `.env` on each VM and `sources.env` on VM 1 were written by hand. Every setting then lives in two places (a password manager and the VMs), a rebuilt VM needs every file typed again, and nothing checks a file before a deploy. The team wants one place for prod configuration. The data-onboarding-agent stack on VM 1 makes the same change, and its `POSTGRES_AIRFLOW_PASSWORD` must equal this repository's `AIRFLOW_DB_PASSWORD`.

## Decision

- **Every prod setting is a repository secret or variable of this repository**, named exactly like its key in `infrastructure/prod/vm1/.env.example`, `vm1/sources.env.example` or `vm2/.env.example`. Passwords, keys and tokens are secrets; addresses, ports and sizes are variables. The example files are the list of settings.
- **A full Deploy run writes the files** before `deploy.sh`: `infrastructure/prod/render_env.py` takes the keys of the target commit's example files and the values from the secret, else the variable, else empty (the Compose default). `docker compose config` checks the result on the runner. The files go to the VMs over the existing SSH connection, mode `600`, replacing what was there.
- **It stops before touching a VM** when a secret or variable is still the placeholder `TODO`, when a required secret is missing (`__GENERATE__` in an example, every key of `sources.env`), when a password-like key is a variable, when a value can't be written to the file (a single quote or a line break), or when Compose rejects the result. Values are never printed.
- The `pipelines/`-only sync doesn't rewrite the files; a changed setting needs a manual Deploy run.
- Still no GitHub environments (ADR-0012): repository secrets work on the current plan.

## Consequences

- One place to set and change prod configuration; a new or rebuilt VM needs only Docker, the `deploy` user and the clone.
- Anyone with write access to the repository can run a workflow that reads the secrets. Acceptable while the team is small; branch protection and Key Vault (Phase 6) narrow it later.
- A new `env://` reference needs a line in `vm1/sources.env.example` and a secret of the same name, or the deploy stops.
- `AIRFLOW_DB_PASSWORD` is only read by PostgreSQL on its first start (agent stack). Changing it later needs `ALTER ROLE airflow PASSWORD …` on the server first, then both repositories' secrets.
- Secret values can't be read back from GitHub; keep them in a password manager as well.
- Key Vault (`kv://`) still replaces the source passwords in Phase 6; the Airflow keys may stay GitHub secrets.

## Alternatives considered

- **Files typed on the VMs (ADR-0012 as written).** No secrets in GitHub, but two places, no checks, manual work on every rebuilt VM.
- **One secret holding the whole file.** Fewer secrets, but changing one value means pasting the whole file again, which can't be read back.
- **GitHub environment secrets.** Scoped to a `production` environment, but environments on a private repository need a paid plan.
- **Key Vault now.** The target for the source passwords, blocked on the Phase 6 decision on where the VMs run.
