"""Template registry: source and sink templates from ``code/templates/``, their parameters and SQL snippets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jinja2
import yaml

SECRET_REF = re.compile(r"^(env|kv)://\S+$")
DURATION = re.compile(r"^[1-9][0-9]*(s|m|h)$")

_jinja = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False, keep_trailing_newline=False)


class TemplateNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Template:
    kind: str  # "sources" or "sinks"
    body: dict[str, Any]

    @property
    def name(self) -> str:
        """The template's name, for example ``mysql``."""
        return str(self.body["name"])

    @property
    def ref(self) -> str:
        """``<name>@<version>``, as connections and jobs refer to it."""
        return f"{self.body['name']}@{self.body['version']}"

    def params(self, section: str) -> dict[str, dict[str, Any]]:
        """The parameter definitions of a section, for example ``connection_params``."""
        return dict(self.body.get(section) or {})


def render(text: str, values: dict[str, Any]) -> str:
    """Renders a ``{{ param }}`` template string; a missing value is an error."""
    return _jinja.from_string(text).render(**values)


def validate_params(defs: dict[str, dict[str, Any]], values: dict[str, Any] | None) -> list[str]:
    """One message per invalid field, in the same words as the Web UI (code/ui/src/lib/templates.ts)."""
    values = values or {}
    errors = [f"{key}: unknown parameter" for key in values if key not in defs]
    for key, spec in defs.items():
        value = values.get(key)
        if value is None or value == "":
            if spec.get("required"):
                errors.append(f"{key}: required")
            continue
        kind = spec.get("type", "string")
        if kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"{key}: must be a whole number")
            elif "min" in spec and value < spec["min"]:
                errors.append(f"{key}: must be at least {spec['min']}")
            elif "max" in spec and value > spec["max"]:
                errors.append(f"{key}: must be at most {spec['max']}")
        elif kind == "bool":
            if not isinstance(value, bool):
                errors.append(f"{key}: must be true or false")
        elif kind == "enum":
            if value not in spec.get("values", []):
                errors.append(f"{key}: one of {', '.join(map(str, spec.get('values', [])))}")
        elif kind == "secret_ref":
            if not isinstance(value, str) or not SECRET_REF.match(value):
                errors.append(f"{key}: use a reference, env://VAR or kv://vault/secret, never the value")
        elif kind == "duration":
            if not isinstance(value, str) or not DURATION.match(value):
                errors.append(f"{key}: for example 30s, 15m or 2h")
        elif kind == "list":
            if not isinstance(value, list):
                errors.append(f"{key}: must be a list")
        elif not isinstance(value, str):
            errors.append(f"{key}: must be text")
    return errors


def with_defaults(defs: dict[str, dict[str, Any]], values: dict[str, Any] | None) -> dict[str, Any]:
    """The values plus the defaults of the parameters they leave out."""
    defaults = {key: spec["default"] for key, spec in defs.items() if "default" in spec}
    return {**defaults, **(values or {})}


class TemplateRegistry:
    """Reads templates on every call: files are small and may change while the API runs."""

    def __init__(self, templates_dir: Path) -> None:
        """A registry over ``templates_dir`` (``code/templates``)."""
        self.templates_dir = templates_dir

    def _all(self, kind: str) -> list[Template]:
        """Every template of a kind, read from the files."""
        return [
            Template(kind, yaml.safe_load(path.read_text(encoding="utf-8")))
            for path in sorted((self.templates_dir / kind).glob("*.yaml"))
        ]

    def sources(self) -> list[Template]:
        """All source templates."""
        return self._all("sources")

    def sinks(self) -> list[Template]:
        """All sink templates."""
        return self._all("sinks")

    def get(self, kind: str, ref: str) -> Template:
        """A template by ``name@version``; TemplateNotFound if the name or the version doesn't exist."""
        name, _, version = ref.partition("@")
        path = self.templates_dir / kind / f"{name}.yaml"
        if not path.exists():
            raise TemplateNotFound(f'template "{ref}" not found')
        template = Template(kind, yaml.safe_load(path.read_text(encoding="utf-8")))
        if str(template.body.get("version")) != version:
            raise TemplateNotFound(f'template "{ref}" not found (current version is {template.body.get("version")})')
        return template

    def source(self, ref: str) -> Template:
        """A source template by ``name@version``."""
        return self.get("sources", ref)

    def sink(self, ref: str) -> Template:
        """A sink template by ``name@version``."""
        return self.get("sinks", ref)

    def schema(self, name: str) -> dict[str, Any]:
        """A JSON Schema by name (``connection``, ``ingestion-job``)."""
        path = self.templates_dir / "schemas" / f"{name}.schema.json"
        if not path.exists():
            raise TemplateNotFound(f'schema "{name}" not found')
        result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return result
