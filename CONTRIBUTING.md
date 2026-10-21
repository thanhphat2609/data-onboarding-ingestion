# Contributing

## Language

All repository content is written in **English**: code, comments, docs, YAML, commit messages, pull request titles and descriptions.

## Workflow

- `main` is protected. Work on a branch named `<type>/<short-description>`, for example `feat/sqlserver-template` or `docs/adr-0007`.
- Open a pull request; at least one review is required.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `build:`, `ci:`.

## Design changes

- Any change to a decision recorded in [docs/adr](docs/adr/README.md) needs a new ADR that supersedes the old one.
- Keep [docs/architecture.md](docs/architecture.md) and [docs/configuration-spec.md](docs/configuration-spec.md) in sync with the code in the same pull request.
- When a roadmap item is done, tick it in [docs/roadmap.md](docs/roadmap.md) in the same pull request.

## Configuration files

- Never commit secret values. Connections reference secrets as `kv://<vault>/<secret>`.
- Template changes that break existing connections or jobs require a new template `version`.
- YAML: 2-space indentation, lowercase kebab-case names.

## Code style (from Phase 2)

| Area | Tooling |
|---|---|
| Python (control plane) | Python 3.12, `ruff` (lint + format), `mypy`, `pytest` |
| Java (runner) | Java 17, Maven, Spotless (google-java-format), JUnit 5 |
| TypeScript (UI) | ESLint, Prettier |
