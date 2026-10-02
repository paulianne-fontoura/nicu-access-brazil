"""Append-only record of every raw file written by the pipeline.

One JSON line per file, never rewritten. The manifest is versioned with the
code: it holds metadata only (source, row count, SHA-256), so anyone can check
that a rerun read the same data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable(path: Path, root: Path) -> str:
    """Relative path with forward slashes, whatever the operating system."""
    return PurePosixPath(*PureWindowsPath(path.relative_to(root)).parts).as_posix()


def key(entry: dict) -> tuple:
    return (entry["dataset"], entry["uf"], entry["year"], entry.get("month"), entry["status"])


def load(manifest: Path) -> list[dict]:
    if not manifest.exists():
        return []
    with manifest.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def latest(manifest: Path) -> dict[tuple, dict]:
    """Last entry for each (dataset, uf, year, month, status)."""
    return {key(e): e for e in load(manifest)}


def append(manifest: Path, entry: dict) -> dict:
    entry = {**entry, "recorded_at": datetime.now(UTC).isoformat(timespec="seconds")}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry
