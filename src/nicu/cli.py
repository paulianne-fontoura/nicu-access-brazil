"""Command line: nicu ingest ..., nicu status, nicu compare-sources."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from nicu import config as C
from nicu import fetch, ibge, ingest

app = typer.Typer(no_args_is_help=True, add_completion=False)
ingest_app = typer.Typer(no_args_is_help=True, help="Fill the raw layer.")
app.add_typer(ingest_app, name="ingest")

FromYear = Annotated[int, typer.Option("--from", help="First year.")]
ToYear = Annotated[int, typer.Option("--to", help="Last year.")]
States = Annotated[list[str] | None, typer.Option("--uf", help="Restrict to states.")]
Force = Annotated[bool, typer.Option(help="Fetch again files already recorded.")]
LAST_YEAR = max(C.YEARS)


def _years(first: int, last: int) -> list[int]:
    return [y for y in C.YEARS if first <= y <= last]


def _print(outcome: ingest.Outcome) -> None:
    if outcome.status == "written":
        typer.echo(f"{outcome.name:<20} {outcome.source:<7} {outcome.rows:>9,} rows")
    elif outcome.status == "skipped":
        typer.echo(f"{outcome.name:<20} already recorded")
    else:
        typer.secho(f"{outcome.name:<20} FAILED {outcome.error}", fg="red")


def _finish(outcomes: list[ingest.Outcome]) -> None:
    failed = [o for o in outcomes if o.status == "failed"]
    written = sum(o.status == "written" for o in outcomes)
    typer.echo(
        f"{written} written, {len(outcomes) - written - len(failed)} skipped, {len(failed)} failed"
    )
    if failed:
        typer.echo("Run the same command again: recorded files are skipped.")
        raise typer.Exit(1)


@ingest_app.command("sinasc")
def ingest_sinasc(
    first: FromYear = C.FIRST_YEAR,
    last: ToYear = LAST_YEAR,
    uf: States = None,
    force: Force = False,
) -> None:
    """Live births (SINASC), one file per state and year."""
    _finish(ingest.ingest_sinasc(_years(first, last), uf or C.UFS, force=force, report=_print))


@ingest_app.command("cnes")
def ingest_cnes(
    first: FromYear = C.FIRST_YEAR,
    last: ToYear = LAST_YEAR,
    uf: States = None,
    force: Force = False,
) -> None:
    """Hospital beds (CNES LT), one month per year and state."""
    _finish(ingest.ingest_cnes_lt(_years(first, last), uf or C.UFS, force=force, report=_print))


@ingest_app.command("ibge")
def ingest_ibge(force: Force = False) -> None:
    """Transport network, population arrangements and municipal seats."""
    for name, rows in ibge.ingest(force=force).items():
        typer.echo(
            f"{name:<20} already recorded" if rows is None else f"{name:<20} {rows:>9,} rows"
        )


@app.command()
def status() -> None:
    """Files the study needs that are not in the manifest yet."""
    gaps = ingest.missing()
    total = len(ingest.expected())
    typer.echo(f"{total - len(gaps)} / {total} raw files recorded")
    for dataset, uf, year, month, state in gaps[:30]:
        typer.echo(
            f"  missing {dataset} {uf} {year}{'' if month is None else f'-{month:02d}'} ({state})"
        )
    if len(gaps) > 30:
        typer.echo(f"  ... and {len(gaps) - 30} more")
    if gaps:
        raise typer.Exit(1)


@app.command("compare-sources")
def compare_sources(
    uf: Annotated[str, typer.Option(help="State.")],
    year: Annotated[int, typer.Option(help="Year.")],
    month: Annotated[int | None, typer.Option(help="Month, for CNES beds.")] = None,
) -> None:
    """Read the same file from the mirror and from the origin and compare them."""
    workdir = Path(C.CACHE_DIR / "origin")
    if month is None:
        name = f"SINASC {uf} {year}"
        mirror = fetch.mirror_sinasc(uf, year)
        origin = fetch.origin_sinasc(uf, year, False, workdir)
    else:
        name = f"CNES LT {uf} {year}-{month:02d}"
        mirror = fetch.mirror_cnes_lt(uf, year, month)
        origin = fetch.origin_cnes_lt(uf, year, month, workdir)
    if mirror.empty:
        typer.secho(f"{name}  the mirror returned no rows for this file", fg="yellow")
    c = ingest.compare(mirror, origin)
    typer.echo(f"{name}  mirror {c.rows_mirror:,} rows, origin {c.rows_origin:,} rows")
    typer.echo(
        f"  columns only in mirror {list(c.only_mirror)}, only in origin {list(c.only_origin)}"
    )
    typer.echo(f"  rows without an identical counterpart {c.rows_differing:,}")
    typer.echo("  IDENTICAL" if c.identical else "  DIFFERENT")
