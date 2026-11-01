# ADR-0014: In prod, the UI saves through a pull request; source passwords are set by hand until Key Vault

- Status: Proposed
- Date: 2026-10-27
- Amended by: [ADR-0017](0017-ui-opens-pull-requests-on-orchestration.md) (the pull request targets the orchestration repository; non-prod does it too)
- Answers: open question 7 ([roadmap](../roadmap.md#open-questions))
- Builds on: [ADR-0012](0012-cicd-ssh-deploy.md) (the `pipelines/`-only sync), [ADR-0013](0013-prod-settings-in-github.md) (prod settings in GitHub)

## Context

In non-prod the Web UI writes connection and job YAML files straight into the checkout (`store.py`). In prod that would mean:
- files nobody reviewed, outside Git, lost when VM 1 is rebuilt;
- a blocked Deploy: `deploy.sh` refuses to check out over uncommitted changes;
- a new connection whose `env://` reference has no value: since ADR-0013, `sources.env` on VM 1 is written from GitHub secrets on each Deploy, and the UI can't create one.

Connections already store only a reference (`env://NAME`, later `kv://…`), never a password, and the Deploy workflow already syncs a `pipelines/`-only change to VM 1 without a click or a rebuild.

## Decision

**1. In prod, saving in the UI opens a pull request instead of writing to disk.**
- The form is unchanged; the API still renders and validates the YAML (`store.py`). Nobody writes YAML by hand.
- The API writes the file to a new branch and opens a pull request against `main` that changes only `pipelines/` (GitHub REST API). The UI shows "waiting for review" with the link.
- CI validates the files (`python -m ingestion.validate`); the Data Team reviews and merges.
- On merge, the existing `pipelines/`-only sync puts the files on VM 1 and Airflow picks them up (ADR-0012).
- Non-prod keeps writing to disk. A setting selects the mode (e.g. `SAVE_MODE=disk|pull_request`).
- The API's GitHub token can only create branches and pull requests on this repository (fine-grained: Contents and Pull requests, read and write). It is a prod secret like the others (ADR-0013).

**2. A new source password is set by hand, once, until Key Vault.**
- A connection with a new `env://NAME` reference: its pull request also adds `NAME=` to `infrastructure/prod/vm1/sources.env.example`.
- The Data Team adds the repository secret `NAME` with the value in GitHub, merges, then runs **Actions → Deploy** once. Until the secret exists the Deploy stops with "NAME is missing", so it can't be forgotten silently.
- The UI says so after saving: which secret to add, then run Deploy.
- New jobs, and connections that reuse an existing reference, need nothing by hand.
- In Phase 6, Key Vault (`kv://`, open question 3) replaces this step: the form writes the password to Key Vault, the VMs read it with their managed identity, no secret in GitHub and no redeploy.

## Consequences

- Git stays the only source of truth for `pipelines/` and for prod settings; a rebuilt VM gets everything back from `main`.
- Every connection and job is reviewed before it runs in prod; a change takes effect after the merge, not on save.
- One manual step per new source system (rare); none per job.
- The API gets a GitHub token (branches and pull requests only). The UI never handles passwords; they go from the Data Team to GitHub secrets (later Key Vault).
- Editing an existing file in prod is also a pull request; two open pull requests on the same file are resolved in GitHub like any conflict.

## Alternatives considered

- **Write on VM 1, then commit and push from the VM.** Changes apply at once, but nothing is reviewed, VM 1 needs push rights to `main` (branch protection forbids it), and a failed push leaves the checkout dirty, blocking Deploy.
- **The UI saves the password as a GitHub secret** (encrypted with the repository's public key) and starts Deploy. No manual step, but the API on VM 1 would hold a token that can rewrite every secret and run workflows; too much power for one saved click.
- **Key Vault now.** The target, but blocked on where the VMs run (open questions 2 and 3).
