# ADR-0017: The Web UI opens pull requests on the orchestration repository; this repository keeps the runner

- Status: Accepted
- Date: 2026-11-01
- Amends: [ADR-0014](0014-prod-save-flow.md) (the pull request targets another repository), [ADR-0016](0016-airflow-moves-to-orchestration.md) (`pipelines/` and the Airflow client leave)

## Context

After ADR-0016 Airflow lives in data-onboarding-orchestration, but this repository still wrote the job and connection files that Airflow reads, and still called Airflow ("Run now", run history, pools). Two repositories shared one folder and one API, so a change on either side could break the other.

This repository should change rarely: a new source template, a new sink, or a new runner. Everything about *when* and *what* runs belongs where the DAGs are.

## Decision

**This repository = how data is read and written.** Web UI, Ingestion API, `code/templates/` (schemas, source and sink templates), the PyFlink runner (Phase 4), Flink and Redpanda.

**data-onboarding-orchestration = when and what runs.** Airflow, the DAG factory, the YAML files of connections and jobs (`pipelines/connections/`, `pipelines/jobs/` there), pools, and later the dbt step that follows a published table.

**The flow:**

1. In the Web UI the user creates a connection, then a job. The API validates against the schemas and templates here (test connection, SQL check and preview work as before).
2. On **Save**, the API opens a pull request on the orchestration repository through the GitHub REST API: a branch `ui/<kind>-<name>-<timestamp>`, one commit with the file, a pull request against `main`. The UI shows the pull request link.
3. CI there validates the file, the Data Team reviews and merges. Airflow builds the DAG `ingest__<name>` from the merged file.
4. The Web UI only links to Airflow. It has no Airflow client: no "Run now", no run history, no pool calls. Pools follow the connection files in the orchestration repository on their own.

**Settings:** `SAVE_MODE=pull_request` (non-prod default) or `disk`; `GITHUB_TOKEN` (a fine-grained token limited to the orchestration repository, Contents and Pull requests, read and write; in a Codespace the user secret `ORCHESTRATION_GITHUB_TOKEN`); `ORCHESTRATION_REPOSITORY`, `ORCHESTRATION_BASE_BRANCH`. A pull request that can't be opened saves nothing.

**`pipelines/` here is a git-ignored working copy.** The API writes the saved file there so the job wizard can use a connection before its pull request is merged. Pointing `INGESTION_PIPELINES_DIR` at a checkout of the orchestration repository shows what is already merged. The repository has no example connections or jobs: a demo creates them by hand in the Web UI.

**The contract between the repositories** is the schemas in `code/templates/schemas/` (read by the DAG factory) and, from Phase 4, the resolved job spec that Airflow writes and the runner reads with `--spec <path>`. The spec gets a `spec_version` so the runner and the DAG factory can change one after the other.

## Consequences

- This repository no longer needs Airflow's URL or password; `airflow.py`, the `/runs` endpoints and the Airflow columns of the UI are gone.
- Nothing runs from this stack alone, and nothing takes effect on save: a change is live after the merge.
- The API holds a GitHub token. It can only create branches and pull requests on one repository.
- Needed in data-onboarding-orchestration (not done by this change): `pipelines/jobs/` and `pipelines/connections/` in its own tree; its Compose files and DAG factory read them there instead of from the ingestion checkout; a CI check that validates them with the schemas from here; the `fetch` task still imports `ingestion.rest_api` from this checkout until that code moves too.
- Prod: the `pipelines/`-only sync is gone from this repository's Deploy workflow; the orchestration repository syncs its own files. The prod API gets `SAVE_MODE=pull_request` and the secret `ORCHESTRATION_GITHUB_TOKEN`, written like every setting by the Deploy workflow ([ADR-0013](0013-prod-settings-in-github.md)); non-prod takes it from the Codespaces user secret of the same name.
- Branch names carry a timestamp to the second; two saves of the same file in the same second would collide.

## Alternatives considered

- **Keep `pipelines/` here, Airflow reads a checkout** (ADR-0016). Works, but every new job is a commit to the repository that should be stable.
- **Keep a thin Airflow client for "Run now" and status.** Convenient, but it ties the API to Airflow's version and authentication. Airflow's own UI does this better.
- **Push to `main` of the orchestration repository directly.** Faster, but nothing is reviewed.
