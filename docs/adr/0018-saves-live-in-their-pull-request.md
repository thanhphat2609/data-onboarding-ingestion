# ADR-0018: A save lives only in its pull request; the lists show it as pending

- Status: Accepted
- Date: 2026-11-06
- Amends: [ADR-0017](0017-ui-opens-pull-requests-on-orchestration.md) (what the API keeps in `pipelines/` after a save)

## Context

ADR-0017 had the API write the saved file to its working copy `pipelines/` and then open the pull request. In prod that copy sits in the volume `api-pipelines` and nothing ever removed it:

- A pull request that was **closed without merging** left a connection in the UI that Airflow never had.
- Two places held the same file (the volume and the orchestration repository), so what the UI listed and what Airflow ran could differ.
- A save could answer **500 while its pull request was already open**: an error after the pull request exists (for example reading the file back) turned into an error response, and the pull request can't be taken back. The user saw a failure and a pull request.

The opposite problem: once the local copy is gone, a connection that is waiting for its merge disappears from the UI, so it gets saved twice.

## Decision

**The pull request is the only record of a save.**

1. In `SAVE_MODE=pull_request` the API still writes the file locally first (to fail early on permissions, before any pull request exists), opens the pull request, and then **deletes the local file**. If the pull request can't be opened, the write is undone and nothing is saved, as before.
2. **What is merged is read from the orchestration repository.** The prod API container mounts the checkout's `pipelines/` read-only at `/workspace/orchestration-pipelines` (`INGESTION_REFERENCE_PIPELINES_DIR`); lists, reads and the existence checks for create and update look in the working copy first, then there.
3. **Saves waiting for their merge are listed as `pending`.** `GET /api/connections` and `GET /api/jobs` add the files of open pull requests whose branch starts with `ui/connection-` or `ui/job-` (read through the GitHub API, cached for 15 seconds, cleared by every save), each with `pending: {number, url, branch}`. A name that is already merged is not listed twice. If GitHub can't be asked, the lists show the merged files only and the error is logged.
4. **The Web UI shows a pending row blurred, with a blue "Pending merge" badge, and nothing in it is a link or a button.** Hovering it says which pull request it waits for. The job wizard offers only merged connections: the API can test and preview only a connection that exists as a merged file, so a job on a pending connection waits for its merge.
5. **An error after the pull request is open never reaches the user as an error.** The API logs it and answers with the saved document and `pullRequest`.

## Consequences

- Orchestration is the single store of connections and jobs. Nothing in this repository's volume survives a save.
- Listing needs the GitHub token (already configured for saving); without GitHub the UI shows merged files only.
- After a merge there is a delay of up to the orchestration sync (about a minute) before the file is merged *and* visible on VM 1; during it the pull request is closed but the item is not listed yet. The delay is the same as for Airflow seeing the DAG.
- Create a connection, merge it, then create the job. A job pull request can't be opened for a connection that isn't merged.

## Alternatives considered

- **Keep the local copy until the merge is detected.** Needs a sweeper that matches files to pull requests and handles closed ones; it keeps two stores.
- **Hide pending items.** Simple, but the user can't see that the save worked, and saves the same connection again: a second pull request for the same file.
