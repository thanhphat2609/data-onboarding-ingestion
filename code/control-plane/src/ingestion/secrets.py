"""Resolves secret references (architecture §3.7). Values are used in memory only and never logged or returned."""

from __future__ import annotations

import os


class SecretError(Exception):
    pass


def resolve(ref: str) -> str:
    """The value behind an ``env://`` reference; ``kv://`` is prod only (Phase 6). Never log the result."""
    scheme, _, path = ref.partition("://")
    if scheme == "env":
        value = os.environ.get(path)
        if value is None:
            raise SecretError(f"environment variable {path} is not set in this container")
        return value
    if scheme == "kv":
        raise SecretError("kv:// references are resolved in prod only (Phase 6)")
    raise SecretError(f'"{ref}" is not a secret reference')
