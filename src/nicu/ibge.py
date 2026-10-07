"""IBGE reference files: the public transport network between municipalities,
the population arrangements and the municipal seats."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import urllib.request
import zipfile
from contextlib import closing
from pathlib import Path

import pandas as pd

from nicu import config as C
from nicu import manifest

# Brazilian municipality codes start with 1 to 5. The survey also lists towns
# across the border, coded 8 and 9.
FOREIGN_FROM = 6_000_000


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    tmp.replace(dest)
    return dest


def parse_links(xlsx: Path) -> pd.DataFrame:
    """One edge per pair of municipalities with a regular bus or boat line.

    Codes are cut to 6 digits (no check digit), the form used by SINASC and
    CNES. Pairs with a foreign end are dropped. When a pair appears twice the
    shortest time is kept.
    """
    raw = pd.read_excel(xlsx, sheet_name="Base de dados")
    raw = raw[(raw.CODMUNDV_A < FOREIGN_FROM) & (raw.CODMUNDV_B < FOREIGN_FROM)]
    a = (raw.CODMUNDV_A // 10).astype(str)
    b = (raw.CODMUNDV_B // 10).astype(str)
    edges = pd.DataFrame(
        {
            "mun_a": a.where(a < b, b),
            "mun_b": b.where(a < b, a),
            "minutes": raw.VAR04.astype(float),
            "cost_brl": raw.VAR03.astype(float),
            "departures_boat": raw.VAR05.astype(float),
            "departures_road": raw.VAR06.astype(float),
        }
    )
    edges = edges.sort_values("minutes").drop_duplicates(["mun_a", "mun_b"])
    return edges.sort_values(["mun_a", "mun_b"]).reset_index(drop=True)


def parse_arranjos(xlsx: Path) -> pd.DataFrame:
    """Municipalities belonging to a population arrangement (IBGE, 2nd ed.).

    The table lists each arrangement on a line of its own (no code), followed
    by its municipalities (with a code).
    """
    raw = pd.read_excel(xlsx, header=None, skiprows=2)
    rows, current = [], None
    for label, code in zip(raw[0], raw[1], strict=True):
        if pd.isna(code):
            current = None if pd.isna(label) else str(label).strip()
        elif current is not None:
            rows.append((current, str(int(code))[:6]))
    return pd.DataFrame(rows, columns=["arranjo", "mun"])


def parse_seats(gpkg_zip: Path) -> pd.DataFrame:
    """One point per municipality, its seat when it has one (IBGE Localidades 2022)."""
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(gpkg_zip) as zf:
            member = next(n for n in zf.namelist() if n.endswith(".gpkg"))
            path = Path(zf.extract(member, tmp))
        # closing() and not the connection's own context manager, which only
        # commits: on Windows an open file blocks the temporary folder cleanup
        with closing(sqlite3.connect(path)) as con:
            table = con.execute(
                "select table_name from gpkg_contents where data_type = 'features'"
            ).fetchone()[0]
            # one point per municipality: its seat, the federal capital for
            # Brasília, and failing that its first locality (Fernando de Noronha)
            seats = pd.read_sql(
                f"""select mun7, name, uf, lat, lon from (
                        select CD_MUN as mun7, NM_MUN as name, SIGLA_UF as uf,
                               LAT_LOCALIDADE as lat, LONG_LOCALIDADE as lon,
                               row_number() over (
                                   partition by CD_MUN
                                   order by case SCT_LOCALIDADE
                                       when 'Sede Municipal' then 0
                                       when 'Capital Federal' then 1
                                       else 2 end, rowid
                               ) as choice
                        from "{table}")
                    where choice = 1""",
                con,
            )
    seats.insert(0, "mun", seats.mun7.str[:6])
    return seats.sort_values("mun").reset_index(drop=True)


SOURCES = {
    # name: (url, source file, parser, year of the data)
    "ibge_links": (C.IBGE_LINKS_URL, "ligacoes_2016.xlsx", parse_links, 2016),
    "ibge_arranjos": (C.IBGE_ARRANJOS_URL, "arranjos_tab01.xlsx", parse_arranjos, 2015),
    "ibge_seats": (C.IBGE_SEATS_URL, "localidades_2022_gpkg.zip", parse_seats, 2022),
}


def ingest(root: Path = C.DATA_DIR, force: bool = False) -> dict[str, int | None]:
    """Download the IBGE files, write them as parquet and record them.

    A file already recorded and present is skipped (count None)."""
    done = manifest.latest(root / "manifest.jsonl")
    counts: dict[str, int | None] = {}
    for name, (url, filename, parser, year) in SOURCES.items():
        dest = root / "raw" / "ibge" / f"{name.removeprefix('ibge_')}.parquet"
        if not force and (name, "BR", year, None, "final") in done and dest.exists():
            counts[name] = None
            continue
        source = download(url, root / "raw" / "ibge" / "source" / filename)
        frame = parser(source)
        frame.to_parquet(dest, index=False)
        manifest.append(
            root / "manifest.jsonl",
            {
                "dataset": name,
                "uf": "BR",
                "year": year,
                "month": None,
                "status": "final",
                "source": url,
                "path": manifest.portable(dest, root.parent),
                "rows": int(len(frame)),
                "source_sha256": manifest.sha256(source),
            },
        )
        counts[name] = len(frame)
    return counts
