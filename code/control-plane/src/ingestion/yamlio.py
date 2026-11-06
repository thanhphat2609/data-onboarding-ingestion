"""Reading and writing the YAML files of connections and jobs: the same layout every time, and atomic writes.

Written files hold only what the user set (empty values dropped), keys in the order of docs/configuration-spec.md, list
items indented under their key and multi-line text (SQL) as literal blocks, like the hand-written examples.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from ingestion.specs import InvalidSpec


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


def load_yaml(path: Path) -> dict[str, Any]:
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


def write_atomic(path: Path, text: str) -> None:
    # The temporary name doesn't end in .yaml, so the DAG factory ignores it.
    """Writes through a temporary file and a rename, so a reader never sees half a file."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
