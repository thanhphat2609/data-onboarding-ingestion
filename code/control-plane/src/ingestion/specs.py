"""Validation of Connection and IngestionJob documents: JSON Schema, then template parameters.

Same rules as the DAG factory in data-onboarding-orchestration, plus the template parameter checks. The
factory moves onto this library in Phase 5.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft7Validator

from ingestion.templates import TemplateNotFound, TemplateRegistry, validate_params


class InvalidSpec(ValueError):
    """A document that can't be saved or turned into a DAG; ``errors`` are shown to users."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def schema_errors(document: Any, schema: dict[str, Any]) -> list[str]:
    validator = Draft7Validator(schema)
    return [
        f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda e: list(map(str, e.path)))
    ]


def validate_connection(connection: Any, registry: TemplateRegistry) -> None:
    errors = schema_errors(connection, registry.schema("connection"))
    if errors:
        raise InvalidSpec(errors)
    try:
        template = registry.source(connection["template"])
    except TemplateNotFound as error:
        raise InvalidSpec([f"template: {error}"]) from None
    errors = [f"params/{e}" for e in validate_params(template.params("connection_params"), connection["params"])]
    if errors:
        raise InvalidSpec(errors)


def validate_job(job: Any, connection: dict[str, Any] | None, registry: TemplateRegistry) -> None:
    """``connection`` is the job's connection document, or None when it doesn't exist."""
    errors = schema_errors(job, registry.schema("ingestion-job"))
    if errors:
        raise InvalidSpec(errors)
    if connection is None:
        raise InvalidSpec([f'connection: "{job["connection"]}" not found'])
    try:
        source = registry.source(connection["template"])
        sink = registry.sink(job["sink"]["template"])
    except TemplateNotFound as error:
        raise InvalidSpec([str(error)]) from None
    errors = [f"source/read/{e}" for e in validate_params(source.params("read_params"), job["source"].get("read"))]
    errors += [f"sink/params/{e}" for e in validate_params(sink.params("params"), job["sink"]["params"])]
    partition_num = (job["source"].get("read") or {}).get("partition_num")
    max_partition_num = (connection.get("limits") or {}).get("max_partition_num")
    if partition_num and max_partition_num and partition_num > max_partition_num:
        errors.append(f"source/read/partition_num: at most {max_partition_num} on connection {connection['name']}")
    if errors:
        raise InvalidSpec(errors)
