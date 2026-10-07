"""From the raw layer to five small tables the analysis reads.

Births are counted, never copied: one row per year, municipality of residence,
municipality and facility of birth and risk group. The tables are small enough
to be versioned, so the analysis can be rerun from a clone without the raw
files (`data/processed`).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import duckdb

from nicu import config as C

# Birth weight classes (ADR-0001). Under 500 g is kept apart: its registration
# rose over the period, which would read as a rise in demand.
BIRTHS_VIEW = """
create or replace temp view births as
select
    cast(regexp_extract(filename, 'DN[A-Z]{{2}}(\\d{{4}})', 1) as integer) as year,
    regexp_extract(filename, 'DN([A-Z]{{2}})', 1) as uf,
    case when filename like '%_prelim%' then 'prelim' else 'final' end as status,
    CODMUNRES as mun_res,
    CODMUNNASC as mun_birth,
    lpad(CODESTAB, 7, '0') as cnes,
    LOCNASC as place,
    try_cast(PESO as integer) as weight,
    GESTACAO as gestation
from read_parquet('{sinasc}', filename = true, union_by_name = true)
"""

# One pass over the births: every birth falls in one cell (year, residence,
# place and facility of birth, risk group or none). The three tables below are
# read from these cells, which is three times faster than three passes.
CELLS = """
create or replace temp table cells as
select year, status, mun_res, mun_birth, cnes, risk_group,
       count(*)::integer as n,
       count(*) filter (where weight is null or weight = 0 or weight >= 9000)::integer
           as n_weight_missing
from (
    select *, case
        when weight between 500 and 1499 then 'w500_1499'
        when weight between 1 and 499 then 'w_under_500'
        when year >= 2011 and gestation in ('1', '2', '3') then 'g_under_32_only'
    end as risk_group
    from births
)
group by all
"""

AT_RISK = """
select year, status, mun_res, mun_birth, cnes, risk_group, sum(n)::integer as n
from cells
where risk_group is not null
group by all
order by all
"""

BY_PLACE = """
select year, mun_birth, cnes, sum(n)::integer as n
from cells
where cnes is not null
group by all
order by all
"""

BY_RESIDENCE = """
select year, status, mun_res,
       sum(n)::integer as n,
       sum(n_weight_missing)::integer as n_weight_missing
from cells
group by all
order by all
"""

# Beds (ADR-0003). Code 63 until 2008, then 80, 81 and 82. A facility that
# reports both in the same month keeps the larger count.
BEDS = """
with lt as (
    select
        cast(regexp_extract(filename, 'LT[A-Z]{{2}}(\\d{{4}})', 1) as integer) as year,
        cast(regexp_extract(filename, 'LT[A-Z]{{2}}\\d{{4}}(\\d{{2}})', 1) as integer) as month,
        lpad(CNES, 7, '0') as cnes,
        CODUFMUN as mun,
        CODLEITO as code,
        coalesce(try_cast(QT_EXIST as integer), 0) as existing,
        coalesce(try_cast(QT_SUS as integer), 0) as sus
    from read_parquet('{cnes}', filename = true, union_by_name = true)
    where CODLEITO in ({codes})
),
facility as (
    select year, month, cnes, mun,
           max(existing) filter (where code = '63') as old_existing,
           sum(existing) filter (where code <> '63') as new_existing,
           max(sus) filter (where code = '63') as old_sus,
           sum(sus) filter (where code <> '63') as new_sus
    from lt
    group by all
)
select year, month, cnes, mun,
       greatest(coalesce(old_existing, 0), coalesce(new_existing, 0))::integer as beds,
       greatest(coalesce(old_sus, 0), coalesce(new_sus, 0))::integer as beds_sus
from facility
where greatest(coalesce(old_existing, 0), coalesce(new_existing, 0)) > 0
order by all
"""

TABLES = {
    "births_at_risk": AT_RISK,
    "births_by_place": BY_PLACE,
    "births_by_residence": BY_RESIDENCE,
    "nicu_beds": BEDS,
}


class BuildError(RuntimeError):
    """The raw layer does not hold what the study needs."""


def _glob(folder: Path) -> str:
    return (folder / "*.parquet").as_posix()


def _check(con: duckdb.DuckDBPyConnection, years: tuple[int, ...], n_states: int) -> None:
    """Every year must hold every state, for births and for beds."""
    # files are split by state of residence, so the residence code names the state
    births = dict(
        con.execute(
            "select year, count(distinct substr(mun_res, 1, 2)) from births_by_residence group by 1"
        ).fetchall()
    )
    beds = dict(
        con.execute(
            "select year, count(distinct substr(mun, 1, 2)) from nicu_beds group by 1"
        ).fetchall()
    )
    problems = []
    for year in years:
        if births.get(year, 0) != n_states:
            problems.append(f"births {year}: {births.get(year, 0)} states out of {n_states}")
        if year not in beds:
            problems.append(f"beds {year}: no file")
    wrong_month = con.execute("select distinct year, month from nicu_beds").fetchall()
    for year, month in wrong_month:
        if year in years and month != C.bed_month(year):
            problems.append(f"beds {year}: month {month}, expected {C.bed_month(year)}")
    if problems:
        raise BuildError("; ".join(problems))


def build(
    raw: Path = C.RAW_DIR,
    out: Path = C.PROCESSED_DIR,
    years: tuple[int, ...] = C.YEARS,
    n_states: int = len(C.UFS),
) -> dict:
    """Write the processed tables and return their summary."""
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(BIRTHS_VIEW.format(sinasc=_glob(raw / "sinasc")))
    con.execute(CELLS)
    codes = ", ".join(f"'{c}'" for c in C.NICU_CODES)
    summary: dict = {"tables": {}}
    for name, sql in TABLES.items():
        sql = sql.format(cnes=_glob(raw / "cnes_lt"), codes=codes)
        con.execute(f"create or replace temp table {name} as {sql}")
        if name == "nicu_beds":
            _check(con, years, n_states)
        con.execute(f"copy {name} to '{(out / (name + '.parquet')).as_posix()}' (format parquet)")
        summary["tables"][name] = con.execute(f"select count(*) from {name}").fetchone()[0]
    for name in ("links", "arranjos", "seats"):
        shutil.copyfile(raw / "ibge" / f"{name}.parquet", out / f"ibge_{name}.parquet")
    summary["by_year"] = [
        dict(zip(("year", "status", "births", "weight_missing"), row, strict=True))
        for row in con.execute(
            "select year, status, sum(n)::integer, sum(n_weight_missing)::integer"
            " from births_by_residence group by 1, 2 order by 1"
        ).fetchall()
    ]
    risk = con.execute(
        "select year, risk_group, sum(n)::integer from births_at_risk group by 1, 2 order by 1, 2"
    ).fetchall()
    beds = dict(
        (y, (b, s))
        for y, b, s in con.execute(
            "select year, sum(beds)::integer, sum(beds_sus)::integer from nicu_beds group by 1"
        ).fetchall()
    )
    for row in summary["by_year"]:
        row.update({g: n for y, g, n in risk if y == row["year"]})
        row["beds"], row["beds_sus"] = beds[row["year"]]
    (out / "build.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return summary
