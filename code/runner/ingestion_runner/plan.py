"""Turns a job file into what the Flink job needs: the JDBC source, the Parquet sink and the audit values.

The merged YAML files are the spec: the job, its connection and the two templates are read as they are, and there is
no intermediate document. Only the standard library and PyYAML are used, because this runs on the JobManager next to
PyFlink and nothing else is installed there.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$")


class SpecError(Exception):
    """A file that the runner can't use; the message says which one and what to fix."""


@dataclass(frozen=True)
class Plan:
    job_name: str
    run_id: str
    ingest_date: str
    ingested_at: str  # UTC, "YYYY-MM-DD HH:MM:SS.mmm"
    dialect: str  # postgres, mysql, sqlserver
    driver: str
    jdbc_url: str
    username: str
    password: str = field(repr=False)
    query: str
    fetch_size: int
    partition_column: str | None
    partition_num: int
    parallelism: int | None
    compression: str
    staging_uri: str


def render(text: str, values: dict[str, Any]) -> str:
    """Fills ``{{ name }}`` placeholders; a missing value is an error, booleans become true/false."""

    def fill(match: re.Match[str]) -> str:
        """Replacement for one placeholder."""
        key = match.group(1)
        if key not in values:
            raise SpecError(f"no value for {{{{ {key} }}}}")
        value = values[key]
        return str(value).lower() if isinstance(value, bool) else str(value)

    return PLACEHOLDER.sub(fill, text)


def resolve_secret(ref: str) -> str:
    """Value of an ``env://NAME`` reference from the JobManager's environment (``kv://`` comes in Phase 6)."""
    scheme, _, name = ref.partition("://")
    if scheme == "env":
        value = os.environ.get(name)
        if value is None:
            raise SpecError(f"environment variable {name} is not set on the JobManager")
        return value
    if scheme == "kv":
        raise SpecError("kv:// references are resolved in prod only (Phase 6)")
    raise SpecError(f'"{ref}" is not a secret reference')


def _load(path: Path, kind: str) -> dict[str, Any]:
    """Reads a YAML file and checks its ``kind``."""
    if not path.exists():
        raise SpecError(f"{path} not found")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("kind") != kind:
        raise SpecError(f"{path} is not a {kind} file")
    return document


def _template(templates_dir: Path, folder: str, ref: str) -> dict[str, Any]:
    """Reads ``<name>.yaml`` of a template folder and checks that its version is the one asked for."""
    name, _, version = ref.partition("@")
    path = templates_dir / folder / f"{name}.yaml"
    if not path.exists():
        raise SpecError(f'template "{ref}" not found in {templates_dir / folder}')
    template: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    if str(template.get("version")) != version:
        raise SpecError(f'template "{ref}" not found (current version is {template.get("version")})')
    return template


def _with_defaults(defs: dict[str, Any], values: dict[str, Any] | None) -> dict[str, Any]:
    """The values plus the defaults of the template parameters they leave out."""
    defaults = {key: spec["default"] for key, spec in defs.items() if "default" in spec}
    return {**defaults, **(values or {})}


def build_plan(
    job_path: Path,
    connections_dir: Path,
    templates_dir: Path,
    run_id: str,
    ingest_date: str,
    output_root: str | None = None,
    now: dt.datetime | None = None,
) -> Plan:
    """Reads the job, its connection and the templates; resolves the password from its ``env://`` reference.

    ``output_root`` replaces the sink's storage root (for example ``file:///opt/ingestion/spike-out``), so a run can be
    tried without an ADLS account; the staging layout below it stays the same.
    """
    if not RUN_ID.match(run_id):
        raise SpecError(f'run id "{run_id}" may only use letters, digits and . _ : + -')
    try:
        dt.date.fromisoformat(ingest_date)
    except ValueError:
        raise SpecError(f'ingest date "{ingest_date}" is not YYYY-MM-DD') from None

    job = _load(job_path, "IngestionJob")
    connection = _load(connections_dir / f"{job['connection']}.yaml", "Connection")
    source = _template(templates_dir, "sources", connection["template"])
    sink = _template(templates_dir, "sinks", job["sink"]["template"])
    if source.get("connector") != "jdbc":
        raise SpecError(f'source template {connection["template"]} reads through "{source.get("connector")}", not jdbc')
    if sink.get("format") != "parquet":
        raise SpecError(f'sink template {job["sink"]["template"]} writes "{sink.get("format")}"; only parquet so far')

    connection_params = _with_defaults(source.get("connection_params") or {}, connection.get("params"))
    read = _with_defaults(source.get("read_params") or {}, job["source"].get("read"))
    sink_params = _with_defaults(sink.get("params") or {}, job["sink"].get("params"))
    if read.get("snapshot_column"):
        raise SpecError("source.read.snapshot_column is not supported by the runner yet")

    if output_root:
        staging_uri = f"{output_root.rstrip('/')}/_staging/{run_id}"
    else:
        staging_uri = render(sink["staging_uri"], {**sink_params, "run_id": run_id})

    moment = now or dt.datetime.now(dt.UTC)
    partition_column = read.get("partition_column") or None
    return Plan(
        job_name=job["name"],
        run_id=run_id,
        ingest_date=ingest_date,
        ingested_at=moment.strftime("%Y-%m-%d %H:%M:%S.") + f"{moment.microsecond // 1000:03d}",
        dialect=source["dialect"],
        driver=source["driver"],
        jdbc_url=render(source["url"], connection_params),
        username=str(connection_params["username"]),
        password=resolve_secret(str(connection_params["password"])),
        query=job["source"]["query"].strip().rstrip(";").rstrip(),
        fetch_size=int(read["fetch_size"]),
        partition_column=partition_column,
        partition_num=int(read["partition_num"]) if partition_column else 1,
        parallelism=(job.get("runtime") or {}).get("parallelism"),
        compression=str(sink_params["compression"]).upper(),
        staging_uri=staging_uri,
    )
