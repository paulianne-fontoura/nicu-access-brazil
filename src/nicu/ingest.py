"""Raw layer: one parquet file per state and year (births) or per state and
month (beds), recorded in the manifest. A file already recorded and present on
disk is skipped, so an interrupted run resumes where it stopped."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from nicu import config as C
from nicu import fetch, manifest


@dataclass(frozen=True)
class Outcome:
    name: str
    status: str  # "written", "skipped" or "failed"
    source: str | None = None
    rows: int | None = None
    error: str | None = None


def _write(frame: pd.DataFrame, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    frame.to_parquet(tmp, index=False)
    tmp.replace(dest)


def _content_hash(frame: pd.DataFrame) -> str:
    """Hash of the rows, independent of their order and of the parquet writer."""
    rows = pd.util.hash_pandas_object(frame.fillna("\x00"), index=False)
    return hashlib.sha256(rows.sort_values().to_numpy().tobytes()).hexdigest()


def _record(root: Path, entry: dict, frame: pd.DataFrame, dest: Path) -> None:
    manifest.append(
        root / "manifest.jsonl",
        {
            **entry,
            "path": manifest.portable(dest, root.parent),
            "rows": int(len(frame)),
            "content_sha256": _content_hash(frame),
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )


def sinasc_path(root: Path, uf: str, year: int, prelim: bool) -> Path:
    suffix = "_prelim" if prelim else ""
    return root / "raw" / "sinasc" / f"DN{uf}{year}{suffix}.parquet"


def cnes_lt_path(root: Path, uf: str, year: int, month: int) -> Path:
    return root / "raw" / "cnes_lt" / f"LT{uf}{year}{month:02d}.parquet"


def ingest_sinasc(
    years: Iterable[int],
    ufs: Iterable[str] = C.UFS,
    *,
    root: Path = C.DATA_DIR,
    force: bool = False,
    fetcher: Callable[..., fetch.Fetched] = fetch.fetch_sinasc,
    report: Callable[[Outcome], None] = lambda o: None,
) -> list[Outcome]:
    done = manifest.latest(root / "manifest.jsonl")
    outcomes = []
    for year in years:
        prelim = year in C.PRELIM_YEARS
        status = "prelim" if prelim else "final"
        for uf in ufs:
            name = f"DN{uf}{year}" + (" (prelim)" if prelim else "")
            dest = sinasc_path(root, uf, year, prelim)
            if not force and ("sinasc", uf, year, None, status) in done and dest.exists():
                outcome = Outcome(name, "skipped")
            else:
                try:
                    got = fetcher(uf, year, prelim=prelim)
                    frame = fetch.keep(got.frame, C.SINASC_COLUMNS)
                    _write(frame, dest)
                    entry = {"dataset": "sinasc", "uf": uf, "year": year, "month": None}
                    _record(root, {**entry, "status": status, "source": got.source}, frame, dest)
                    outcome = Outcome(name, "written", got.source, len(frame))
                except Exception as exc:  # noqa: BLE001 - reported, the run goes on
                    outcome = Outcome(name, "failed", error=f"{type(exc).__name__}: {exc}")
            report(outcome)
            outcomes.append(outcome)
    return outcomes


def ingest_cnes_lt(
    years: Iterable[int],
    ufs: Iterable[str] = C.UFS,
    *,
    root: Path = C.DATA_DIR,
    force: bool = False,
    fetcher: Callable[..., fetch.Fetched] = fetch.fetch_cnes_lt,
    report: Callable[[Outcome], None] = lambda o: None,
) -> list[Outcome]:
    done = manifest.latest(root / "manifest.jsonl")
    outcomes = []
    for year in years:
        month = C.bed_month(year)
        for uf in ufs:
            name = f"LT{uf}{year}-{month:02d}"
            dest = cnes_lt_path(root, uf, year, month)
            if not force and ("cnes_lt", uf, year, month, "final") in done and dest.exists():
                outcome = Outcome(name, "skipped")
            else:
                try:
                    got = fetcher(uf, year, month)
                    frame = fetch.keep(got.frame, C.CNES_LT_COLUMNS)
                    _write(frame, dest)
                    entry = {"dataset": "cnes_lt", "uf": uf, "year": year, "month": month}
                    _record(root, {**entry, "status": "final", "source": got.source}, frame, dest)
                    outcome = Outcome(name, "written", got.source, len(frame))
                except Exception as exc:  # noqa: BLE001 - reported, the run goes on
                    outcome = Outcome(name, "failed", error=f"{type(exc).__name__}: {exc}")
            report(outcome)
            outcomes.append(outcome)
    return outcomes


IBGE_KEYS = [
    ("ibge_links", "BR", 2016, None, "final"),
    ("ibge_arranjos", "BR", 2015, None, "final"),
    ("ibge_seats", "BR", 2022, None, "final"),
]


def expected(years: Iterable[int] = C.YEARS, ufs: Iterable[str] = C.UFS) -> list[tuple]:
    """Every raw file the study needs, as manifest keys."""
    keys = list(IBGE_KEYS)
    for year in years:
        status = "prelim" if year in C.PRELIM_YEARS else "final"
        for uf in ufs:
            keys.append(("sinasc", uf, year, None, status))
            keys.append(("cnes_lt", uf, year, C.bed_month(year), "final"))
    return keys


def missing(root: Path = C.DATA_DIR, **kwargs) -> list[tuple]:
    done = manifest.latest(root / "manifest.jsonl")
    return [k for k in expected(**kwargs) if k not in done]


# --- mirror against origin -----------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    rows_mirror: int
    rows_origin: int
    only_mirror: tuple[str, ...]
    only_origin: tuple[str, ...]
    rows_differing: int  # rows of one source without an identical row in the other

    @property
    def identical(self) -> bool:
        return (
            self.rows_mirror == self.rows_origin
            and not self.only_mirror
            and not self.only_origin
            and self.rows_differing == 0
        )


def compare(mirror: pd.DataFrame, origin: pd.DataFrame) -> Comparison:
    """Compare two versions of the same file, rows taken as a multiset."""
    a, b = fetch.as_text(mirror), fetch.as_text(origin)
    common = sorted(set(a.columns) & set(b.columns))
    if a.empty or b.empty or not common:
        gap = len(a) + len(b)  # nothing to match: every row is unmatched
    else:
        ha = pd.util.hash_pandas_object(a[common].fillna("\x00"), index=False).value_counts()
        hb = pd.util.hash_pandas_object(b[common].fillna("\x00"), index=False).value_counts()
        both = ha.index.union(hb.index)
        gap = (ha.reindex(both, fill_value=0) - hb.reindex(both, fill_value=0)).abs().sum()
    return Comparison(
        rows_mirror=len(a),
        rows_origin=len(b),
        only_mirror=tuple(sorted(set(a.columns) - set(b.columns))),
        only_origin=tuple(sorted(set(b.columns) - set(a.columns))),
        rows_differing=int(gap),
    )
