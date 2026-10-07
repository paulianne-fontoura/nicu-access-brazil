"""The three questions, from the processed tables to result tables.

1. How did access change over the period (`access`)?
2. Did the beds opened go where uncovered births were (`bed_growth`,
   `decomposition`)?
3. Where would new units cover the most uncovered births (`sites`)?
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_array

from nicu import access as net
from nicu import config as C

MAIN_GROUP = "w500_1499"  # ADR-0001
SCOPES = ("sus", "all")  # ADR-0003, SUS beds first
THRESHOLDS = (90, 120, 180)
MAIN_THRESHOLD = 120
UNITS = (5, 10, 20)
SITE_YEARS = 5
MIN_BIRTHS = 1000  # births a year in a municipality for it to be a candidate
ALL_BEDS_FROM = 2008  # type I beds enter the register with the new codes (ADR-0003)
REGIONS = {"1": "Norte", "2": "Nordeste", "3": "Sudeste", "4": "Sul", "5": "Centro-Oeste"}
STATES = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}  # fmt: skip


@dataclass
class Data:
    at_risk: pd.DataFrame
    by_place: pd.DataFrame
    by_residence: pd.DataFrame
    beds: pd.DataFrame
    links: pd.DataFrame
    arranjos: pd.DataFrame
    seats: pd.DataFrame

    @classmethod
    def load(cls, folder: Path = C.PROCESSED_DIR) -> Data:
        def read(name: str) -> pd.DataFrame:
            return pd.read_parquet(folder / f"{name}.parquet")

        return cls(
            at_risk=read("births_at_risk"),
            by_place=read("births_by_place"),
            by_residence=read("births_by_residence"),
            beds=read("nicu_beds"),
            links=read("ibge_links"),
            arranjos=read("ibge_arranjos"),
            seats=read("ibge_seats"),
        )

    @property
    def years(self) -> list[int]:
        return sorted(self.at_risk.year.unique().tolist())


# --- networks ----------------------------------------------------------------------


class GraphNetwork:
    """Bus and boat network, the main measure."""

    def __init__(self, graph: nx.Graph):
        self.graph = graph
        self.nodes = set(graph.nodes)

    def nearest(self, sources: set[str]) -> dict[str, float]:
        return net.minutes_to_nearest(self.graph, sources)

    def reach(self, origin: str, minutes: float) -> set[str]:
        return net.reach(self.graph, origin, minutes) if origin in self.nodes else set()


class StraightNetwork:
    """Straight lines between seats at the pace of the surveyed lines, the check."""

    def __init__(self, seats: pd.DataFrame, minutes_per_km: float):
        self.seats = seats.drop_duplicates("mun").reset_index(drop=True)
        self.minutes_per_km = minutes_per_km
        self.nodes = set(self.seats.mun)
        self._index = {m: i for i, m in enumerate(self.seats.mun)}

    def nearest(self, sources: set[str]) -> dict[str, float]:
        return net.straight_minutes(self.seats, sources, self.minutes_per_km)

    def reach(self, origin: str, minutes: float) -> set[str]:
        if origin not in self._index:
            return set()
        o = self.seats.iloc[self._index[origin]]
        km = net.haversine_km(o.lat, o.lon, self.seats.lat.to_numpy(), self.seats.lon.to_numpy())
        return set(self.seats.mun[km * self.minutes_per_km <= minutes])


def networks(data: Data) -> tuple[GraphNetwork, StraightNetwork]:
    graph = net.build_graph(data.links, data.arranjos, data.seats)
    return GraphNetwork(graph), StraightNetwork(data.seats, net.pace(data.links, data.seats))


# --- supply and demand ---------------------------------------------------------------


def nicu(beds: pd.DataFrame, year: int, scope: str) -> tuple[set[str], set[str]]:
    """Facilities and municipalities with a neonatal ICU in a year."""
    column = "beds_sus" if scope == "sus" else "beds"
    rows = beds[(beds.year == year) & (beds[column] > 0)]
    return set(rows.cnes), set(rows.mun)


def at_risk(data: Data, year: int, group: str = MAIN_GROUP) -> pd.DataFrame:
    rows = data.at_risk
    return rows[(rows.year == year) & (rows.risk_group == group)]


def demand(data: Data, year: int, group: str = MAIN_GROUP) -> pd.Series:
    """Births at risk by municipality of residence."""
    return at_risk(data, year, group).groupby("mun_res").n.sum()


def over(minutes: pd.Series, threshold: float) -> pd.Series:
    """Beyond a travel time. No path at all counts as beyond."""
    return minutes.isna() | (minutes > threshold)


# --- question 1 ----------------------------------------------------------------------


def access(data: Data, network: GraphNetwork, group: str = MAIN_GROUP) -> pd.DataFrame:
    """Access indicators by year, bed scope and area (country, region, state)."""
    out = []
    for year in data.years:
        births = at_risk(data, year, group).copy()
        births["region"] = births.mun_res.str[0].map(REGIONS)
        births["state"] = births.mun_res.str[:2].map(STATES)
        births["country"] = "BR"
        for scope in SCOPES:
            if scope == "all" and year < ALL_BEDS_FROM:
                continue  # not comparable with later years
            facilities, municipalities = nicu(data.beds, year, scope)
            minutes = births.mun_res.map(network.nearest(municipalities))
            flags = {
                "born_in_nicu_facility": births.cnes.isin(facilities),
                "born_in_nicu_municipality": births.mun_birth.isin(municipalities),
                "lives_in_nicu_municipality": minutes == 0,
                "born_outside_residence": births.mun_res != births.mun_birth,
                "no_path": minutes.isna(),
                **{f"over_{t}_min": over(minutes, t) for t in THRESHOLDS},
            }
            weighted = pd.DataFrame({k: v * births.n for k, v in flags.items()})
            weighted["births"] = births.n
            for level in ("country", "region", "state"):
                sums = weighted.groupby(births[level]).sum()
                shares = sums.drop(columns="births").div(sums.births, axis=0)
                table = shares.add_prefix("share_")
                table.insert(0, "births", sums.births)
                table.insert(1, "births_over_main", sums[f"over_{MAIN_THRESHOLD}_min"])
                table = table.reset_index(names="area")
                table.insert(0, "level", level)
                table.insert(0, "scope", scope)
                table.insert(0, "status", births.status.iloc[0])
                table.insert(0, "year", year)
                out.append(table)
    return pd.concat(out, ignore_index=True)


# --- question 2 ----------------------------------------------------------------------


def bed_growth(data: Data, first: int, last: int, scope: str) -> dict:
    """Where the beds added between two years are."""
    column = "beds_sus" if scope == "sus" else "beds"
    start = data.beds[data.beds.year == first].groupby("mun")[column].sum()
    end = data.beds[data.beds.year == last].groupby("mun")[column].sum()
    both = pd.concat([start.rename("start"), end.rename("end")], axis=1).fillna(0)
    both = both[(both.start > 0) | (both.end > 0)]
    had, new = both[both.start > 0], both[both.start == 0]
    lost = had[had.end == 0]
    return {
        "scope": scope,
        "first": first,
        "last": last,
        "beds_first": int(both.start.sum()),
        "beds_last": int(both.end.sum()),
        "beds_change": int(both.end.sum() - both.start.sum()),
        "change_where_already_present": int((had.end - had.start).sum()),
        "beds_in_new_municipalities": int(new.end.sum()),
        "new_municipalities": int(len(new)),
        "municipalities_that_lost_all": int(len(lost)),
        "beds_lost_there": int(lost.start.sum()),
        "municipalities_first": int((both.start > 0).sum()),
        "municipalities_last": int((both.end > 0).sum()),
    }


def uncovered(
    data: Data, network, births_year: int, beds_year: int, threshold: float, scope: str
) -> tuple[int, int]:
    """Births at risk of one year beyond the threshold, given the beds of another."""
    births = demand(data, births_year)
    _, municipalities = nicu(data.beds, beds_year, scope)
    minutes = pd.Series(births.index.map(network.nearest(municipalities)), index=births.index)
    return int(births[over(minutes, threshold)].sum()), int(births.sum())


def decomposition(
    data: Data,
    network,
    first: int,
    last: int,
    threshold: float = MAIN_THRESHOLD,
    scopes: tuple[str, ...] = SCOPES,
) -> pd.DataFrame:
    """Change in the uncovered share, split between the two things that moved.

    The beds effect is the change obtained by moving the NICU map from the
    first year to the last while births stay put. The births effect is the
    rest. Each is the average of the two possible orders, so they add up to
    the total change exactly.
    """
    rows = []
    for scope in scopes:
        share = {}
        for births_year in (first, last):
            for beds_year in (first, last):
                n, total = uncovered(data, network, births_year, beds_year, threshold, scope)
                share[births_year, beds_year] = n / total
        beds_effect = (
            (share[first, last] - share[first, first]) + (share[last, last] - share[last, first])
        ) / 2
        births_effect = (
            (share[last, first] - share[first, first]) + (share[last, last] - share[first, last])
        ) / 2
        rows.append(
            {
                "scope": scope,
                "first": first,
                "last": last,
                "threshold": threshold,
                "share_first": share[first, first],
                "share_last": share[last, last],
                "change": share[last, last] - share[first, first],
                "beds_effect": beds_effect,
                "births_effect": births_effect,
                "share_first_births_last_beds": share[first, last],
                "share_last_births_first_beds": share[last, first],
            }
        )
    return pd.DataFrame(rows)


# --- checks on question 1 ------------------------------------------------------------


def sensitivity(data: Data) -> pd.DataFrame:
    """The national series under other choices: risk group (ADR-0001) and time
    given to a trip inside an urban arrangement (ADR-0002). SUS beds."""
    keep = ["year", "births", "share_born_in_nicu_facility", f"share_over_{MAIN_THRESHOLD}_min"]
    out = []
    for minutes in (30.0, net.ARRANGEMENT_MINUTES, 90.0):
        graph = net.build_graph(data.links, data.arranjos, data.seats, arrangement_minutes=minutes)
        network = GraphNetwork(graph)
        groups = sorted(data.at_risk.risk_group.unique()) if minutes == 60 else [MAIN_GROUP]
        for group in groups:
            years = data.at_risk[data.at_risk.risk_group == group].year.unique()
            subset = Data(
                **{**data.__dict__, "at_risk": data.at_risk[data.at_risk.year.isin(years)]}
            )
            table = access(subset, network, group).query("level == 'country' and scope == 'sus'")
            table = table[keep].copy()
            table.insert(0, "arrangement_minutes", minutes)
            table.insert(0, "risk_group", group)
            out.append(table)
    return pd.concat(out, ignore_index=True)


# --- question 3 ----------------------------------------------------------------------


def candidates(data: Data, year: int, with_nicu: set[str], min_births: int) -> set[str]:
    """Municipalities without a NICU where enough births already take place."""
    place = data.by_place[data.by_place.year == year].groupby("mun_birth").n.sum()
    return set(place[place >= min_births].index) - with_nicu


def solve(births: pd.Series, cover: dict[str, set[str]], units: int) -> tuple[list[str], int]:
    """Maximal covering location problem, solved exactly.

    `births` are the uncovered births by municipality, `cover` the
    municipalities each candidate site brings within reach. Returns the sites
    chosen and the births they cover together.
    """
    cover = {c: reached & set(births.index) for c, reached in cover.items()}
    cover = {c: reached for c, reached in cover.items() if reached}
    if not cover or units <= 0:
        return [], 0
    sites = sorted(cover)
    places = sorted(set().union(*cover.values()))
    if units >= len(sites):
        return sites, int(births[places].sum())
    column = {p: len(sites) + i for i, p in enumerate(places)}
    rows, cols, values = [], [], []
    for j, site in enumerate(sites):  # place covered only if one of its sites is open
        for place in cover[site]:
            rows.append(column[place] - len(sites))
            cols.append(j)
            values.append(-1.0)
    for i in range(len(places)):
        rows.append(i)
        cols.append(len(sites) + i)
        values.append(1.0)
    n = len(sites) + len(places)
    covering = coo_array((values, (rows, cols)), shape=(len(places), n)).tocsr()
    open_sites = np.arange(len(sites))
    budget = coo_array((np.ones(len(sites)), (np.zeros_like(open_sites), open_sites)), shape=(1, n))
    objective = np.zeros(n)
    objective[len(sites) :] = -births[places].to_numpy(dtype=float)
    integrality = np.zeros(n)
    integrality[: len(sites)] = 1
    result = milp(
        objective,
        constraints=[
            LinearConstraint(covering, -np.inf, 0),
            LinearConstraint(budget.tocsr(), units, units),
        ],
        integrality=integrality,
        bounds=Bounds(0, 1),
    )
    if not result.success:
        raise RuntimeError(f"location model not solved: {result.message}")
    chosen = [s for s, x in zip(sites, result.x[: len(sites)], strict=True) if x > 0.5]
    covered = set().union(*(cover[s] for s in chosen)) if chosen else set()
    return chosen, int(births[sorted(covered)].sum())


def _place(far: pd.Series, cover: dict[str, set[str]], units: tuple[int, ...], labels: dict):
    """Solve for each number of units and return (chosen rows, coverage rows)."""
    chosen_rows, coverage_rows = [], []
    for k in units:
        picked, covered = solve(far, cover, k)
        coverage_rows.append(
            {
                **labels,
                "units": k,
                "births_uncovered": int(far.sum()),
                "births_newly_covered": covered,
            }
        )
        for site in picked:
            within = int(far[sorted(cover[site] & set(far.index))].sum())
            chosen_rows.append({**labels, "units": k, "mun": site, "births_within_reach": within})
    return chosen_rows, coverage_rows


def sites(
    data: Data,
    network,
    *,
    years: list[int] | None = None,
    units: tuple[int, ...] = UNITS,
    thresholds: tuple[int, ...] = THRESHOLDS,
    min_births: int = MIN_BIRTHS,
    scope: str = "sus",
    measure: str = "network",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sites chosen and births covered (ADR-0005).

    The answer is computed on the last years taken together, `basis` "pooled".
    Births at risk are summed over these years, the NICU map is the latest one,
    and a candidate needs the minimum number of births on average. Each year is
    then solved on its own, `basis` "year", to see how stable the choice is.
    """
    years = years or data.years[-SITE_YEARS:]
    chosen_rows, coverage_rows = [], []

    def add(far_from, births, options, labels):
        for threshold in thresholds:
            far = births[over(far_from, threshold)]
            cover = {c: network.reach(c, threshold) for c in sorted(options)}
            tags = {"measure": measure, **labels, "threshold": threshold}
            chosen, coverage = _place(far, cover, units, tags)
            chosen_rows.extend(chosen)
            coverage_rows.extend({**row, "candidates": len(options)} for row in coverage)

    # the last years together, against the latest NICU map
    _, with_nicu = nicu(data.beds, years[-1], scope)
    births = pd.concat([demand(data, y) for y in years]).groupby(level=0).sum()
    minutes = pd.Series(births.index.map(network.nearest(with_nicu)), index=births.index)
    place = data.by_place[data.by_place.year.isin(years)].groupby("mun_birth").n.sum() / len(years)
    options = (set(place[place >= min_births].index) - with_nicu) & network.nodes
    add(minutes, births, options, {"basis": "pooled", "year": years[-1], "years": len(years)})

    for year in years:
        _, with_nicu = nicu(data.beds, year, scope)
        births = demand(data, year)
        minutes = pd.Series(births.index.map(network.nearest(with_nicu)), index=births.index)
        options = candidates(data, year, with_nicu, min_births) & network.nodes
        add(minutes, births, options, {"basis": "year", "year": year, "years": 1})
    return pd.DataFrame(chosen_rows), pd.DataFrame(coverage_rows)


def ranking(chosen: pd.DataFrame, straight: pd.DataFrame, seats: pd.DataFrame) -> pd.DataFrame:
    """The sites chosen on the pooled years, with what makes each choice more or
    less solid: years in which it is also chosen, other travel times, and
    straight-line distances."""
    names = seats.drop_duplicates("mun").set_index("mun")[["name", "uf"]]

    def picked(frame: pd.DataFrame, basis: str, threshold: int) -> pd.DataFrame:
        return frame[(frame.basis == basis) & (frame.threshold == threshold)]

    main = picked(chosen, "pooled", MAIN_THRESHOLD)
    table = main[["units", "mun"]].copy()
    table["births_within_reach_per_year"] = (main.births_within_reach / main.years).round(1)
    yearly = picked(chosen, "year", MAIN_THRESHOLD).groupby(["units", "mun"]).year.nunique()
    keys = list(zip(table.units, table.mun, strict=True))
    table["years_chosen"] = [int(yearly.get(key, 0)) for key in keys]
    for threshold in THRESHOLDS:
        if threshold != MAIN_THRESHOLD:
            other = picked(chosen, "pooled", threshold)
            also = set(zip(other.units, other.mun, strict=True))
            table[f"also_at_{threshold}_min"] = [key in also for key in keys]
    line = picked(straight, "pooled", MAIN_THRESHOLD)
    also = set(zip(line.units, line.mun, strict=True))
    table["also_straight_line"] = [key in also for key in keys]
    table = table.join(names, on="mun")
    return table.sort_values(
        ["units", "births_within_reach_per_year"], ascending=[True, False]
    ).reset_index(drop=True)


# --- everything ----------------------------------------------------------------------


def run(
    processed: Path = C.PROCESSED_DIR, results: Path = C.RESULTS_DIR
) -> dict[str, pd.DataFrame]:
    """Answer the three questions and write one CSV per table."""
    data = Data.load(processed)
    network, straight = networks(data)
    first, last = data.years[0], data.years[-1]
    chosen, coverage = sites(data, network)
    chosen_line, coverage_line = sites(
        data, straight, thresholds=(MAIN_THRESHOLD,), measure="straight_line"
    )
    tables = {
        "access": access(data, network),
        "bed_growth": pd.DataFrame(
            [
                bed_growth(data, first, last, "sus"),
                bed_growth(data, max(first, ALL_BEDS_FROM), last, "all"),
            ]
        ),
        "sensitivity": sensitivity(data),
        "decomposition": pd.concat(
            [
                decomposition(data, network, first, last, scopes=("sus",)),
                decomposition(data, network, max(first, ALL_BEDS_FROM), last, scopes=("all",)),
            ],
            ignore_index=True,
        ),
        "site_coverage": pd.concat([coverage, coverage_line], ignore_index=True),
        "sites_by_year": pd.concat([chosen, chosen_line], ignore_index=True),
        "sites": ranking(chosen, chosen_line, data.seats),
    }
    results.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(results / f"{name}.csv", index=False, float_format="%.6g", lineterminator="\n")
    return tables
