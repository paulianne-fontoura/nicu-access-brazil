"""Numbers, tables and figures of the note, written by the pipeline.

Every number the note cites is a LaTeX macro in `report/numbers.tex`, the two
tables are `report/table_*.tex` and the figures are in `report/figures`. The
note itself holds no number typed by hand: run `nicu analyze` then
`nicu report` on new data and the text follows.

Some sentences of the note make a claim about the data rather than quote a
number, such as "most of the fall took place by 2010". These claims are
checked here, and the report stops if the data no longer supports one of them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no screen needed, in CI or on a server

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import patheffects  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from nicu import access as net  # noqa: E402
from nicu import analyze as A  # noqa: E402
from nicu import config as C  # noqa: E402
from nicu import manifest  # noqa: E402

REPORT_DIR = C.ROOT / "report"
MID_YEAR = 2010  # the year the note uses to split the period
SOLID_YEARS = 4  # a site chosen alone in at least 4 of the 5 years
TEN = 10
NORTE = "Norte"

# Colours (validated categorical and ordinal steps, see the dataviz notes in
# docs/design.md). Regions keep the same colour wherever they appear.
INK, MUTED, GRID = "#1a1a19", "#6b6a66", "#e4e3df"
REGION_COLOURS = {
    "Norte": "#2a78d6",
    "Nordeste": "#eb6834",
    "Centro-Oeste": "#1baf7a",
    "Sudeste": "#eda100",
    "Sul": "#e87ba4",
}
# Travel time classes for the map. Within reach is a neutral grey, beyond it one
# hue from light to dark, so the eye goes to the births out of reach.
TIME_CLASSES = [  # upper bound in minutes, label, colour
    (120, "Up to 2 hours", "#cfcdc6"),
    (240, "2 to 4 hours", "#3987e5"),
    (np.inf, "More than 4 hours", "#0d366b"),
]
SITE_COLOUR = "#eb6834"


class ReportError(RuntimeError):
    """The data no longer supports a sentence of the note."""


# --- formatting --------------------------------------------------------------------


def count(n: float) -> str:
    return f"{round(n):,}"


def pct(share: float, digits: int = 1) -> str:
    return f"{100 * share:.{digits}f}\\,\\%"


def points(change: float) -> str:
    """A change of share in percentage points, signed."""
    value = f"{100 * abs(change):.1f}"
    return f"$-${value}" if change < 0 else f"+{value}"


def pt_count(n: float) -> str:
    """Portuguese style, 3.010."""
    return count(n).replace(",", ".")


def pt_pct(share: float, digits: int = 1) -> str:
    """Portuguese style, 47,7 %."""
    return pct(share, digits).replace(".", ",")


WORDS = "no one two three four five six seven eight nine ten".split()


def word(n: int) -> str:
    """Small counts in words, as the text reads them."""
    return WORDS[n] if 0 <= n < len(WORDS) else count(n)


def minutes(value: float) -> str:
    return f"{value:.2f}"


def names(rows: pd.DataFrame) -> str:
    """Arcoverde (PE), Jacobina (BA) and Eunápolis (BA)."""
    items = [f"{r.name} ({r.uf})" for r in rows.itertuples()]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


# --- inputs --------------------------------------------------------------------------


@dataclass
class Inputs:
    access: pd.DataFrame
    bed_growth: pd.DataFrame
    reach_change: pd.DataFrame
    decomposition: pd.DataFrame
    sensitivity: pd.DataFrame
    site_coverage: pd.DataFrame
    sites: pd.DataFrame
    municipalities: pd.DataFrame
    build: dict
    states: pd.DataFrame
    network: dict
    raw_files: int

    @classmethod
    def load(
        cls,
        results: Path = C.RESULTS_DIR,
        processed: Path = C.PROCESSED_DIR,
        manifest_path: Path = C.MANIFEST,
    ) -> Inputs:
        def read(name: str) -> pd.DataFrame:
            return pd.read_csv(results / f"{name}.csv", dtype={"mun": str, "area": str})

        data = A.Data.load(processed)
        graph = net.build_graph(data.links, data.arranjos, data.seats)
        estimated = sum(1 for *_, e in graph.edges(data="estimated") if e)
        return cls(
            access=read("access"),
            bed_growth=read("bed_growth"),
            reach_change=read("reach_change"),
            decomposition=read("decomposition"),
            sensitivity=read("sensitivity"),
            site_coverage=read("site_coverage"),
            sites=read("sites"),
            municipalities=read("municipalities"),
            build=json.loads((processed / "build.json").read_text(encoding="utf-8")),
            states=pd.read_parquet(processed / "ibge_states.parquet"),
            network={
                "municipalities": graph.number_of_nodes(),
                "links": graph.number_of_edges(),
                "estimated": estimated,
                "pace": net.pace(data.links, data.seats),
            },
            raw_files=len(manifest.latest(manifest_path)),
        )


def _row(frame: pd.DataFrame, **where) -> pd.Series:
    rows = frame
    for column, value in where.items():
        rows = rows[rows[column] == value]
    if len(rows) != 1:
        raise ReportError(f"expected one row for {where}, found {len(rows)}")
    return rows.iloc[0]


# --- numbers -------------------------------------------------------------------------


def numbers(i: Inputs) -> dict[str, str]:
    """One entry per macro of the note."""
    years = [row["year"] for row in i.build["by_year"]]
    first, last = years[0], years[-1]
    by_year = {row["year"]: row for row in i.build["by_year"]}
    over = f"share_over_{A.MAIN_THRESHOLD}_min"

    def country(year: int, scope: str = "sus") -> pd.Series:
        return _row(i.access, year=year, scope=scope, level="country")

    def region(name: str, year: int) -> pd.Series:
        return _row(i.access, year=year, scope="sus", level="region", area=name)

    c_first, c_mid, c_last = country(first), country(MID_YEAR), country(last)
    all_first = int(i.access.query("scope == 'all'").year.min())
    a_first, a_last = country(all_first, "all"), country(last, "all")
    regions_last = i.access.query("level == 'region' and scope == 'sus' and year == @last")
    worst = regions_last.sort_values(over).iloc[-1]
    norte = {y: region(NORTE, y) for y in (first, MID_YEAR, last)}
    nordeste_last = region("Nordeste", last)

    growth = _row(i.bed_growth, scope="sus")
    growth_all = _row(i.bed_growth, scope="all")
    change = _row(i.reach_change, scope="sus")
    decomposition = _row(i.decomposition, scope="sus")
    decomposition_all = _row(i.decomposition, scope="all")

    sens = i.sensitivity
    main_last = _row(sens, risk_group=A.MAIN_GROUP, arrangement_minutes=60, year=last)
    arrangement = sens[(sens.risk_group == A.MAIN_GROUP) & (sens.year == last)]
    arrangement_spread = arrangement[over].max() - arrangement[over].min()
    gestation = sens[sens.risk_group == "g_under_32_only"]
    g_first, g_last = int(gestation.year.min()), int(gestation.year.max())
    g_last_row = _row(gestation, year=g_last)

    pooled = i.site_coverage.query("measure == 'network' and basis == 'pooled'")
    p_main = pooled[pooled.threshold == A.MAIN_THRESHOLD].set_index("units")
    p90 = pooled[pooled.threshold == 90].set_index("units")
    p180 = pooled[pooled.threshold == 180].set_index("units")
    line = i.site_coverage.query("measure == 'straight_line' and basis == 'pooled'")
    line = line.set_index("units")
    n_years = int(_row(p_main.reset_index(), units=TEN).years)
    uncovered = p_main.births_uncovered.iloc[0]
    ten = i.sites[i.sites.units == TEN]
    solid = ten[(ten.years_chosen >= SOLID_YEARS) & ten.also_straight_line]
    fragile = ten[ten.years_chosen <= 1]
    pooled_years = f"{last - n_years + 1}--{last}"

    m = i.municipalities
    far_last = m[m.minutes_last > A.MAIN_THRESHOLD]
    norte_far = far_last[far_last.region == NORTE].births_at_risk_last_years.sum()
    norte_sites = ten.mun.str[0].map(A.REGIONS).eq(NORTE).sum()

    risk_total = sum(row["w500_1499"] for row in i.build["by_year"])
    out = {
        # data
        "firstYear": str(first),
        "lastYear": str(last),
        "midYear": str(MID_YEAR),
        "nYears": str(len(years)),
        "lastFinalYear": str(C.LAST_FINAL_YEAR),
        "allBedsFrom": str(all_first),
        "rawFiles": count(i.raw_files),
        "birthsTotal": count(sum(row["births"] for row in i.build["by_year"])),
        "riskTotal": count(risk_total),
        "riskFirst": count(by_year[first]["w500_1499"]),
        "riskLast": count(by_year[last]["w500_1499"]),
        "underFiveFirst": count(by_year[first]["w_under_500"]),
        "underFiveLast": count(by_year[last]["w_under_500"]),
        "weightMissingFirst": count(by_year[first]["weight_missing"]),
        "weightMissingLast": count(by_year[last]["weight_missing"]),
        "susBedsFirst": count(growth.beds_first),
        "susBedsLast": count(growth.beds_last),
        "allBedsFirst": count(growth_all.beds_first),
        "allBedsLast": count(growth_all.beds_last),
        "netMunicipalities": count(i.network["municipalities"]),
        "netLinks": count(i.network["links"]),
        "netEstimated": count(i.network["estimated"]),
        "pace": minutes(i.network["pace"]),
        "speed": f"{60 / i.network['pace']:.0f}",
        # question 1
        "bornFirst": pct(c_first.share_born_in_nicu_facility),
        "bornMid": pct(c_mid.share_born_in_nicu_facility),
        "bornLast": pct(c_last.share_born_in_nicu_facility),
        "overFirst": pct(c_first[over]),
        "overMid": pct(c_mid[over]),
        "overLast": pct(c_last[over]),
        "overBirthsFirst": count(c_first.births_over_main),
        "overBirthsLast": count(c_last.births_over_main),
        "overNinetyLast": pct(c_last.share_over_90_min),
        "overOneEightyLast": pct(c_last.share_over_180_min),
        "outsideFirst": pct(c_first.share_born_outside_residence, 0),
        "outsideLast": pct(c_last.share_born_outside_residence, 0),
        "norteOverFirst": pct(norte[first][over]),
        "norteOverMid": pct(norte[MID_YEAR][over]),
        "norteOverLast": pct(norte[last][over]),
        "norteRiskShare": pct(norte[last].births / c_last.births, 0),
        "norteUncoveredShare": pct(norte[last].births_over_main / c_last.births_over_main, 0),
        "norteRiskShareFirst": pct(norte[first].births / c_first.births),
        "norteRiskShareLast": pct(norte[last].births / c_last.births),
        "nordesteOverBirthsLast": count(nordeste_last.births_over_main),
        "allBornFirst": pct(a_first.share_born_in_nicu_facility),
        "allBornLast": pct(a_last.share_born_in_nicu_facility),
        "allOverFirst": pct(a_first[over]),
        "allOverLast": pct(a_last[over]),
        "arrangementSpread": f"{100 * arrangement_spread:.1f}",
        "mainOverLast": pct(main_last[over]),
        "gestFirstYear": str(g_first),
        "gestOverLast": pct(g_last_row[over]),
        "gestBirthsLast": count(g_last_row.births),
        # question 2
        "bedsChange": count(growth.beds_change),
        "bedsWherePresent": count(growth.change_where_already_present),
        "bedsNewMunicipalities": count(growth.beds_in_new_municipalities),
        "munFirst": count(growth.municipalities_first),
        "munLast": count(growth.municipalities_last),
        "munOpened": count(change.municipalities_opened),
        "munOpenedBeyond": count(change.opened_beyond_threshold),
        "bedsOpenedBeyond": count(change.beds_opened_beyond_threshold),
        "munClosed": count(change.municipalities_closed),
        "bedsLostClosed": count(growth.beds_lost_there),
        "uncoveredFirst": count(change.uncovered_first),
        "broughtWithin": count(change.brought_within_reach),
        "broughtWithinShare": pct(change.brought_within_reach / change.uncovered_first, 0),
        "fellOut": count(change.fell_out_of_reach),
        "uncoveredLastMap": count(change.uncovered_with_last_map),
        "uncoveredLastMapShare": pct(decomposition.share_first_births_last_beds),
        "changeTotal": points(decomposition.change),
        "bedsEffect": points(decomposition.beds_effect),
        "birthsEffect": points(decomposition.births_effect),
        "allChangeTotal": points(decomposition_all.change),
        "allBedsEffect": points(decomposition_all.beds_effect),
        "allBirthsEffect": points(decomposition_all.births_effect),
        # question 3
        "pooledYears": pooled_years,
        "candidates": count(p_main.candidates.iloc[0]),
        "candidatesMin": count(i.site_coverage.query("basis == 'year'").candidates.min()),
        "candidatesMax": count(i.site_coverage.query("basis == 'year'").candidates.max()),
        "minBirths": count(A.MIN_BIRTHS),
        "uncoveredPooled": count(uncovered),
        "uncoveredPerYear": count(uncovered / n_years),
        "coverFive": count(p_main.births_newly_covered[5]),
        "coverTen": count(p_main.births_newly_covered[10]),
        "coverTwenty": count(p_main.births_newly_covered[20]),
        "shareFive": pct(p_main.births_newly_covered[5] / uncovered, 0),
        "shareTen": pct(p_main.births_newly_covered[10] / uncovered, 0),
        "shareTwenty": pct(p_main.births_newly_covered[20] / uncovered, 0),
        "ceiling": count(p_main.births_coverable.iloc[0]),
        "ceilingShare": pct(p_main.births_coverable.iloc[0] / uncovered, 0),
        "beyondCeiling": count(uncovered - p_main.births_coverable.iloc[0]),
        "tenNinetyShare": pct(p90.births_newly_covered[10] / p90.births_uncovered[10], 0),
        "tenOneEightyShare": pct(p180.births_newly_covered[10] / p180.births_uncovered[10], 0),
        "tenLineShare": pct(line.births_newly_covered[10] / line.births_uncovered[10], 0),
        "topSite": names(ten.head(1)),
        "topSitePerYear": f"{ten.births_within_reach_per_year.iloc[0]:.0f}",
        "solidSites": names(solid),
        "fragileSites": names(fragile),
        "norteFarShare": pct(norte_far / far_last.births_at_risk_last_years.sum(), 0),
        "norteSites": word(int(norte_sites)),
        # the summary in Portuguese
        "ptRiskTotal": pt_count(risk_total),
        "ptBornFirst": pt_pct(c_first.share_born_in_nicu_facility),
        "ptBornLast": pt_pct(c_last.share_born_in_nicu_facility),
        "ptOverFirst": pt_pct(c_first[over]),
        "ptOverLast": pt_pct(c_last[over]),
        "ptNorteOverLast": pt_pct(norte[last][over]),
        "ptShareTen": pt_pct(p_main.births_newly_covered[10] / uncovered, 0),
        "ptCeilingShare": pt_pct(p_main.births_coverable.iloc[0] / uncovered, 0),
    }
    check(
        {
            "access improved over the period": c_last[over] < c_first[over]
            and c_last.share_born_in_nicu_facility > c_first.share_born_in_nicu_facility,
            f"most of the fall took place by {MID_YEAR}": (c_first[over] - c_mid[over])
            > (c_first[over] - c_last[over]) / 2,
            "births fell by about a sixth": 0.14
            < 1 - by_year[last]["births"] / by_year[first]["births"]
            < 0.19,
            "the North is the region farthest from a unit": worst.area == NORTE,
            f"the North stopped improving after {MID_YEAR}": norte[last][over]
            >= norte[MID_YEAR][over] - 0.005,
            "the Northeast holds the most births beyond two hours": (
                regions_last.sort_values("births_over_main").iloc[-1].area == "Nordeste"
            ),
            "the North's share of births at risk grew": norte[last].births / c_last.births
            > norte[first].births / c_first.births,
            "the narrower gestational group is farther from units": g_last_row[over]
            > main_last[over],
            "most first units opened within reach of an existing one": (
                change.opened_beyond_threshold < change.municipalities_opened / 2
            ),
            "some births fell out of reach where units closed": change.fell_out_of_reach > 0,
            "new beds moved the share down, births moved it up": (
                decomposition.beds_effect < 0 < decomposition.births_effect
            ),
            "candidates cannot cover every uncovered birth": (
                p_main.births_coverable.iloc[0] < uncovered
            ),
            "at least one site is solid": len(solid) > 0,
            "at least one site is fragile": len(fragile) > 0,
            "the North gets fewer sites than its share of uncovered births": norte_sites / TEN
            < norte_far / far_last.births_at_risk_last_years.sum(),
            "the Northeast gets the most sites": (
                ten.mun.str[0].map(A.REGIONS).value_counts().idxmax() == "Nordeste"
            ),
        }
    )
    return out


def check(claims: dict[str, bool]) -> None:
    """Stop when a sentence of the note no longer holds on the data."""
    failed = [claim for claim, holds in claims.items() if not holds]
    if failed:
        raise ReportError(
            "the note says something the data no longer supports: " + "; ".join(failed)
        )


def write_numbers(values: dict[str, str], path: Path) -> None:
    lines = ["% Written by `nicu report` - do not edit by hand."]
    lines += [f"\\newcommand{{\\{key}}}{{{value}}}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


# --- tables --------------------------------------------------------------------------


def table_regions(i: Inputs) -> str:
    over = f"share_over_{A.MAIN_THRESHOLD}_min"
    years = sorted(i.access.year.unique())
    first, last = years[0], years[-1]
    rows = i.access.query("scope == 'sus' and level in ('region', 'country')")
    order = [*A.REGIONS.values(), "BR"]
    lines = [
        "% Written by `nicu report` - do not edit by hand.",
        "\\begin{tabular}{lrrrrrr}",
        "\\toprule",
        " & \\multicolumn{2}{c}{Births} & \\multicolumn{2}{c}{Born in a}"
        " & \\multicolumn{2}{c}{Living over} \\\\",
        " & \\multicolumn{2}{c}{500--1,499\\,g} & \\multicolumn{2}{c}{NICU facility}"
        " & \\multicolumn{2}{c}{2 hours away} \\\\",
        "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(lr){6-7}",
        f"Region & {first} & {last} & {first} & {last} & {first} & {last} \\\\",
        "\\midrule",
    ]
    for area in order:
        a, b = (_row(rows, area=area, year=y) for y in (first, last))
        label = "\\textit{Brazil}" if area == "BR" else area
        if area == "BR":
            lines.append("\\addlinespace")
        lines.append(
            f"{label} & {count(a.births)} & {count(b.births)}"
            f" & {pct(a.share_born_in_nicu_facility)} & {pct(b.share_born_in_nicu_facility)}"
            f" & {pct(a[over])} & {pct(b[over])} \\\\"
        )
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def table_sites(i: Inputs) -> str:
    ten = i.sites[i.sites.units == TEN]
    n_years = int(i.site_coverage.query("basis == 'pooled'").years.iloc[0])
    yes = "$\\bullet$"
    lines = [
        "% Written by `nicu report` - do not edit by hand.",
        "\\begin{tabular}{llrcccc}",
        "\\toprule",
        " & & Births & Years & \\multicolumn{2}{c}{Also chosen at} & Straight \\\\",
        "\\cmidrule(lr){5-6}",
        "Municipality & State & reached a year & chosen & 90 min & 180 min & line \\\\",
        "\\midrule",
    ]
    for r in ten.itertuples():
        lines.append(
            f"{r.name} & {r.uf} & {r.births_within_reach_per_year:.0f}"
            f" & {r.years_chosen} of {n_years}"
            f" & {yes if r.also_at_90_min else ''} & {yes if r.also_at_180_min else ''}"
            f" & {yes if r.also_straight_line else ''} \\\\"
        )
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


# --- figures -------------------------------------------------------------------------


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelcolor=INK, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def figure_access(i: Inputs, path: Path) -> None:
    """Born in a NICU facility (left), living over two hours away by region (right)."""
    over = f"share_over_{A.MAIN_THRESHOLD}_min"
    country = i.access.query("level == 'country'")
    regions = i.access.query("level == 'region' and scope == 'sus'")
    fig, (left, right) = plt.subplots(1, 2, figsize=(7.2, 3.1), layout="constrained")

    for scope, style, label in (("sus", "-", "SUS beds"), ("all", "--", "All beds")):
        rows = country[country.scope == scope]
        left.plot(rows.year, 100 * rows.share_born_in_nicu_facility, style, color=INK, lw=2)
        left.annotate(
            label,
            (rows.year.iloc[-1], 100 * rows.share_born_in_nicu_facility.iloc[-1]),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=INK,
        )
    left.set_title("Born in a facility with a NICU", fontsize=9, loc="left", color=INK)

    for name, colour in REGION_COLOURS.items():
        rows = regions[regions.area == name]
        right.plot(rows.year, 100 * rows[over], color=colour, lw=2, label=name)
    rows = country[country.scope == "sus"]
    right.plot(rows.year, 100 * rows[over], color=INK, lw=2, ls=(0, (1, 1)), label="Brazil")
    right.set_title("Living more than 2 hours from a SUS NICU", fontsize=9, loc="left", color=INK)
    right.legend(fontsize=7, frameon=False, ncol=2, loc="upper right")

    for ax in (left, right):
        _style(ax)
        ax.set_ylim(bottom=0)
        ax.set_xlim(rows.year.min(), rows.year.max() + (4.4 if ax is left else 0.3))
        ax.set_xticks([2006, 2010, 2015, 2020, 2025])
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    left.set_ylim(0, 100)
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _time_class(value: float) -> int:
    for k, (bound, *_rest) in enumerate(TIME_CLASSES):
        if value <= bound:
            return k
    return len(TIME_CLASSES) - 1


def _label_side(sites: pd.DataFrame) -> list[str]:
    """Labels go right of their site, left when another site sits just to the right."""
    sides = []
    for r in sites.itertuples():
        crowded = (sites.lon > r.lon) & (sites.lon < r.lon + 5) & ((sites.lat - r.lat).abs() < 1.2)
        sides.append("left" if crowded.any() else "right")
    return sides


def figure_map(i: Inputs, path: Path) -> None:
    """Travel time to the nearest SUS NICU in the last year, births at risk of the
    pooled years as dot size, the units in place and the ten sites of the model."""
    m = i.municipalities.copy()
    m["k"] = m.minutes_last.fillna(np.inf).map(_time_class)
    year = int(i.access.year.max())
    fig, ax = plt.subplots(figsize=(7.2, 6.9), layout="constrained")

    rings = list(i.states.groupby(["uf_code", "part", "ring"]))
    for _, ring in rings:
        ax.fill(ring.lon, ring.lat, facecolor="#f6f5f2", edgecolor="none", zorder=0)
    for _, ring in rings:
        ax.plot(ring.lon, ring.lat, color="#a9a8a2", lw=0.5, zorder=1)

    births = m.births_at_risk_last_years.clip(lower=0)
    size = 1.5 + 70 * np.sqrt(births / births.max())
    for k, (_, label, colour) in enumerate(TIME_CLASSES):
        rows = m[m.k == k]
        ax.scatter(
            rows.lon,
            rows.lat,
            s=size[rows.index],
            color=colour,
            edgecolor="white",
            linewidth=0.25,
            zorder=2 + k,
            label=label,
        )
    units = m[m.sus_beds_last > 0]
    ax.scatter(units.lon, units.lat, s=9, marker="+", color=INK, linewidth=0.7, zorder=8)

    ten = i.sites[i.sites.units == TEN].merge(m[["mun", "lat", "lon"]], on="mun")
    ax.scatter(
        ten.lon, ten.lat, s=80, facecolor="none", edgecolor=SITE_COLOUR, linewidth=1.8, zorder=9
    )
    halo = [patheffects.withStroke(linewidth=2.2, foreground="white")]
    for r, side in zip(ten.itertuples(), _label_side(ten), strict=True):
        ax.annotate(
            r.name,
            (r.lon, r.lat),
            xytext=(6, 4) if side == "right" else (-6, 4),
            textcoords="offset points",
            ha="left" if side == "right" else "right",
            fontsize=7,
            color=INK,
            path_effects=halo,
            zorder=10,
        )

    handles = [
        Line2D([], [], ls="", marker="o", ms=6, color=colour, label=label)
        for _, label, colour in TIME_CLASSES
    ]
    handles.append(
        Line2D([], [], ls="", marker="+", ms=6, mew=1, color=INK, label="SUS NICU in place")
    )
    handles.append(
        Line2D(
            [], [], ls="", marker="o", ms=8, mfc="none", mec=SITE_COLOUR, mew=1.8,
            label=f"{TEN} sites of the location model",
        )
    )  # fmt: skip
    ax.legend(
        handles=handles,
        loc="lower left",
        fontsize=7.5,
        frameon=False,
        title=f"Travel time to the nearest SUS NICU, {year}",
        title_fontsize=7.5,
        alignment="left",
    )
    ax.set_xlim(-74.2, -34.6)  # Fernando de Noronha, far offshore, is left out of the frame
    ax.set_aspect(1 / np.cos(np.radians(15)))
    ax.set_axis_off()
    fig.savefig(path, dpi=200)
    plt.close(fig)


# --- everything ----------------------------------------------------------------------


def run(inputs: Inputs | None = None, out: Path = REPORT_DIR) -> dict[str, str]:
    """Write the numbers, tables and figures of the note and return the numbers."""
    i = inputs or Inputs.load()
    values = numbers(i)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    write_numbers(values, out / "numbers.tex")
    (out / "table_regions.tex").write_text(table_regions(i), encoding="utf-8", newline="\n")
    (out / "table_sites.tex").write_text(table_sites(i), encoding="utf-8", newline="\n")
    figure_access(i, out / "figures" / "access.png")
    figure_map(i, out / "figures" / "map.png")
    return values
