"""Config store: ``pipelines/connections/<name>.yaml`` and ``pipelines/jobs/<name>.yaml`` are the only storage.

Here ``pipelines/`` is the Web UI's working copy; the files Airflow runs live in data-onboarding-orchestration and
reach it by pull request (ADR-0017). The file name equals ``name``, names never change, and every write is
validated first and replaces the file atomically.

In ``pull_request`` mode the pull request is the record: once it is open the local file is deleted, so orchestration
is the only place a connection or job is stored. What is already merged is read from ``reference_pipelines_dir``
(a read-only checkout of the orchestration repository); a local file, if any, wins over it.
"""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ingestion.settings import Settings
from ingestion.specs import InvalidSpec, validate_connection, validate_job
from ingestion.templates import TemplateRegistry

# Called with a file's path relative to pipelines/ and its text, after validation and the local write; it may raise,
# and the local write is then undone.
Publish = Callable[[str, str], None]

# Key order in written files, matching docs/configuration-spec.md.
_CONNECTION_KEYS = ["kind", "name", "template", "owner", "params", "limits", "access"]
_JOB_KEYS = ["kind", "name", "owner", "connection", "source", "sink", "verify", "runtime", "schedule", "tags"]


class NotFound(LookupError):
    pass


class Conflict(Exception):
    pass


class StorageError(Exception):
    """The working copy can't be written; the message says what to check."""


@dataclass(frozen=True)
class InvalidFile:
    path: str  # relative to the repository, for example pipelines/jobs/x.yaml
    error: str


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        # Indent list items under their key (`tags:\n  - crm`), per .editorconfig and the examples.
        """Indents list items under their key."""
        super().increase_indent(flow, False)


def _represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    # SQL and other multi-line text as literal blocks (`query: |`), like the hand-written examples.
    """Writes multi-line text, such as SQL, as a literal block."""
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _represent_str)


def _clean(value: Any) -> Any:
    """Drops empty values, so written files only hold what the user set."""
    if isinstance(value, dict):
        cleaned = {k: _clean(v) for k, v in value.items()}
        return {k: v for k, v in cleaned.items() if v not in (None, "", {}, [])}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, str) and "\n" in value:
        # Literal blocks can't keep trailing spaces on a line.
        return "\n".join(line.rstrip() for line in value.strip("\n").splitlines()) + "\n"
    return value


def to_yaml(document: dict[str, Any], key_order: list[str]) -> str:
    """The document as YAML: empty values dropped, the keys in ``key_order`` first."""
    cleaned = _clean(document)
    ordered = {key: cleaned[key] for key in key_order if key in cleaned}
    ordered.update({k: v for k, v in cleaned.items() if k not in ordered})
    return yaml.dump(ordered, Dumper=_Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False, indent=2)


def _load_yaml(path: Path) -> dict[str, Any]:
    """Reads a YAML file that must hold a mapping."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark else ""
        raise InvalidSpec([f"invalid YAML{where}: {getattr(error, 'problem', None) or error}"]) from None
    if not isinstance(data, dict):
        raise InvalidSpec([f"{path.name} is not a YAML mapping"])
    return data


def _write_atomic(path: Path, text: str) -> None:
    # The temporary name doesn't end in .yaml, so the DAG factory ignores it.
    """Writes through a temporary file and a rename, so a reader never sees half a file."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class ConfigStore:
    def __init__(self, settings: Settings, registry: TemplateRegistry) -> None:
        """A store over the connection and job files of ``settings``."""
        self.settings = settings
        self.registry = registry
        self._lock = threading.Lock()

    # --- reading ---------------------------------------------------------------------------------

    def _dirs(self, directory: Path) -> list[Path]:
        """The working copy folder, then the same folder of the orchestration checkout, if one is mounted."""
        reference = self.settings.reference_pipelines_dir
        return [directory] + ([reference / directory.name] if reference else [])

    def _find(self, directory: Path, name: str) -> Path | None:
        """The file of ``name`` in the working copy or the orchestration checkout (the working copy first)."""
        for folder in self._dirs(directory):
            if (folder / f"{name}.yaml").exists():
                return folder / f"{name}.yaml"
        return None

    def _read(self, directory: Path, name: str, kind: str) -> dict[str, Any]:
        """One document by file name; NotFound when the file doesn't exist."""
        path = self._find(directory, name)
        if path is None:
            raise NotFound(f'{kind} "{name}" not found')
        return _load_yaml(path)

    def _scan(self, directory: Path, kind: str) -> tuple[list[dict[str, Any]], list[InvalidFile]]:
        """The valid documents of a folder, and the files that can't be loaded."""
        valid: list[dict[str, Any]] = []
        invalid: list[InvalidFile] = []
        connections = {c["name"]: c for c in self.list_connections()} if kind == "job" else {}
        files: dict[str, Path] = {}
        for folder in reversed(self._dirs(directory)):  # the working copy last, so it wins
            files.update({path.name: path for path in folder.glob("*.yaml")})
        for path in (files[name] for name in sorted(files)):
            relative = f"pipelines/{directory.name}/{path.name}"
            try:
                document = _load_yaml(path)
                if kind == "connection":
                    validate_connection(document, self.registry)
                else:
                    validate_job(document, connections.get(str(document.get("connection"))), self.registry)
                if document["name"] != path.stem:
                    raise InvalidSpec([f'file name does not match name "{document["name"]}"'])
                valid.append(document)
            except (InvalidSpec, OSError) as error:
                invalid.append(InvalidFile(relative, str(error)))
        return valid, invalid

    def list_connections(self) -> list[dict[str, Any]]:
        """All valid connections."""
        return self._scan(self.settings.connections_dir, "connection")[0]

    def list_jobs(self) -> list[dict[str, Any]]:
        """All valid jobs."""
        return self._scan(self.settings.jobs_dir, "job")[0]

    def invalid_files(self) -> list[InvalidFile]:
        """The connection and job files that can't be loaded, with the reason."""
        return self._scan(self.settings.connections_dir, "connection")[1] + self._scan(self.settings.jobs_dir, "job")[1]

    def get_connection(self, name: str) -> dict[str, Any]:
        """One connection by name; NotFound if it doesn't exist."""
        return self._read(self.settings.connections_dir, name, "Connection")

    def get_job(self, name: str) -> dict[str, Any]:
        """One job by name; NotFound if it doesn't exist."""
        return self._read(self.settings.jobs_dir, name, "Job")

    # --- writing ---------------------------------------------------------------------------------

    def _save(
        self,
        directory: Path,
        document: dict[str, Any],
        is_new: bool,
        kind: str,
        keys: list[str],
        publish: Publish | None,
    ) -> dict[str, Any]:
        """Writes one file: new names must not exist, existing ones must; returns the document as stored.

        ``publish`` runs after the write; if it raises, the write is undone. When it succeeds in ``pull_request`` mode
        the local file is deleted: the pull request is the record.
        """
        name = document["name"]
        path = directory / f"{name}.yaml"
        with self._lock:
            existing = self._find(directory, name)
            if is_new and existing:
                raise Conflict(f"pipelines/{directory.name}/{path.name} already exists")
            if not is_new and not existing:
                raise NotFound(f'{kind} "{name}" not found; names can\'t be changed after creation')
            text = to_yaml(document, keys)
            previous = path.read_text(encoding="utf-8") if path.exists() else None
            # The local write goes first: it is the step that can fail for local reasons (permissions of the mounted
            # working copy), and a pull request can't be taken back once it is open.
            try:
                directory.mkdir(parents=True, exist_ok=True)
                _write_atomic(path, text)
            except OSError as error:
                raise StorageError(
                    f"Can't write {path} ({error.strerror or error}); "
                    "nothing was saved and no pull request was opened. "
                    "Check that the API user can write to the pipelines directory."
                ) from None
            if publish:
                try:
                    publish(f"{directory.name}/{path.name}", text)
                except BaseException:
                    # When the pull request can't be opened, nothing is saved.
                    if previous is None:
                        path.unlink(missing_ok=True)
                    else:
                        _write_atomic(path, previous)
                    raise
                if self.settings.save_mode == "pull_request":
                    # The pull request now holds the file; orchestration is the only place it is stored.
                    # The pull request is open: a leftover local file must not turn the save into an error.
                    with contextlib.suppress(OSError):
                        path.unlink(missing_ok=True)
            return yaml.safe_load(text)

    def check_writable(self) -> None:
        """Raises StorageError at startup unless the connections and jobs directories can be written."""
        for directory in (self.settings.connections_dir, self.settings.jobs_dir):
            probe = directory / ".write-check"
            try:
                directory.mkdir(parents=True, exist_ok=True)
                probe.write_text("", encoding="utf-8")
                probe.unlink()
            except OSError as error:
                raise StorageError(
                    f"{directory} isn't writable ({error.strerror or error}). Create pipelines/ on the host before "
                    "starting (infrastructure/non-prod/bootstrap.sh does), or Docker creates it owned by root."
                ) from None

    def save_connection(
        self, connection: dict[str, Any], is_new: bool, publish: Publish | None = None
    ) -> dict[str, Any]:
        """Validates and saves a connection; returns the stored document."""
        validate_connection(connection, self.registry)
        return self._save(self.settings.connections_dir, connection, is_new, "Connection", _CONNECTION_KEYS, publish)

    def save_job(self, job: dict[str, Any], is_new: bool, publish: Publish | None = None) -> dict[str, Any]:
        """Validates and saves a job against its connection; returns the stored document."""
        connection: dict[str, Any] | None = None
        if isinstance(job, dict) and isinstance(job.get("connection"), str):
            try:
                connection = self.get_connection(job["connection"])
                validate_connection(connection, self.registry)
            except NotFound:
                connection = None
            except InvalidSpec as error:
                raise InvalidSpec([f"connection {job['connection']} is invalid: {error}"]) from None
        validate_job(job, connection, self.registry)
        return self._save(self.settings.jobs_dir, job, is_new, "Job", _JOB_KEYS, publish)
