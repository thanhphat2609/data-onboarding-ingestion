# Contributing

## Language

All repository content is written in **English**: code, comments, docs, YAML, commit messages, pull request titles and descriptions.

## Workflow

- `main` is protected. Work on a branch named `<type>/<short-description>`, for example `feat/sqlserver-template` or `docs/adr-0007`.
- Open a pull request; at least one review is required.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `build:`, `ci:`.

## Versioning and releases

The repository has one version for all components, following [Semantic Versioning](https://semver.org/). It is marked with annotated Git tags on `main` only.

| Tag | When |
|---|---|
| `v0.<phase>.0-rc.<n>` | A phase is ready for testing; increase `n` after each round of fixes |
| `v0.<phase>.0` | Every exit criterion of that phase in the [roadmap](docs/roadmap.md) is met |
| `v1.0.0` | First production release (Phase 6) |
| `vX.Y.Z` after 1.0 | `Z` for fixes, `Y` for backward-compatible features, `X` for breaking changes |

```bash
git tag -a v0.1.0-rc.1 -m "Phase 1: ready for testing in Codespaces"
git push origin v0.1.0-rc.1
```

- Tags are never moved or reused. A fix gets a new tag.
- From Phase 6, each tag builds images with the same version (`ingestion-ui:1.0.0`) and creates a GitHub Release; prod deploys a tag, and a rollback deploys the previous one.
- Template versions (`sqlserver@1`) are separate: they change only when a template breaks existing connections or jobs.

## Design changes

- Any change to a decision recorded in [docs/adr](docs/adr/README.md) needs a new ADR that supersedes the old one.
- Keep [docs/architecture.md](docs/architecture.md) and [docs/configuration-spec.md](docs/configuration-spec.md) in sync with the code in the same pull request.
- When a roadmap item is done, tick it in [docs/roadmap.md](docs/roadmap.md) in the same pull request.

## Configuration files

- Never commit secret values. Connections reference secrets as `env://<VAR>` (non-prod) or `kv://<vault>/<secret>` (prod).
- Template changes that break existing connections or jobs require a new template `version`.
- YAML: 2-space indentation, lowercase kebab-case names.

## Code style (from Phase 1)

| Area | Tooling |
|---|---|
| Python (control plane, Airflow) | Python 3.12, `ruff` (lint + format), `mypy`, `pytest` |
| Python (runner) | Python 3.11 (PyFlink 1.20 limit), same tooling; Table API and SQL only, no Python UDFs |
| TypeScript (UI) | `tsc` (strict), `oxlint` |
