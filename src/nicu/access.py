"""Travel time between municipalities (ADR-0002).

The network is the IBGE survey of regular bus and boat lines (2016), completed
in two ways. Municipalities of one urban arrangement are linked to each other,
because the survey leaves out city transport. Municipalities absent from the
survey are attached to their nearest neighbours at the pace observed on the
surveyed lines.
"""

from __future__ import annotations

import itertools

import networkx as nx
import numpy as np
import pandas as pd

ARRANGEMENT_MINUTES = 60.0
NEIGHBOURS = 3
EARTH_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance, on scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


def pace(links: pd.DataFrame, seats: pd.DataFrame) -> float:
    """Median minutes per straight-line kilometre on the surveyed lines."""
    xy = seats.set_index("mun")[["lat", "lon"]]
    known = links[links.mun_a.isin(xy.index) & links.mun_b.isin(xy.index)]
    a, b = xy.loc[known.mun_a].to_numpy(), xy.loc[known.mun_b].to_numpy()
    km = haversine_km(a[:, 0], a[:, 1], b[:, 0], b[:, 1])
    keep = km > 5  # neighbouring seats give unstable ratios
    return float(np.median(known.minutes.to_numpy()[keep] / km[keep]))


def build_graph(
    links: pd.DataFrame,
    arranjos: pd.DataFrame,
    seats: pd.DataFrame,
    *,
    arrangement_minutes: float = ARRANGEMENT_MINUTES,
    neighbours: int = NEIGHBOURS,
) -> nx.Graph:
    """Weighted graph of municipalities, travel time in minutes on the edges."""
    graph = nx.Graph()
    for a, b, minutes in zip(links.mun_a, links.mun_b, links.minutes, strict=True):
        graph.add_edge(a, b, minutes=float(minutes))

    if arrangement_minutes > 0:
        for _, members in arranjos.groupby("arranjo").mun:
            for a, b in itertools.combinations(sorted(set(members)), 2):
                current = graph.get_edge_data(a, b, {}).get("minutes", np.inf)
                graph.add_edge(a, b, minutes=min(current, arrangement_minutes))

    if neighbours > 0:
        minutes_per_km = pace(links, seats)
        outside = set(seats.mun) - set(graph.nodes)
        _attach(graph, seats, outside, set(graph.nodes), minutes_per_km, neighbours)
        # a few surveyed towns are only linked to each other, the same rule joins
        # them to the rest
        parts = sorted(nx.connected_components(graph), key=len, reverse=True)
        for part in parts[1:]:
            _attach(graph, seats, part, parts[0], minutes_per_km, neighbours)
    return graph


def _attach(graph, seats, towns: set[str], anchors: set[str], minutes_per_km, neighbours) -> None:
    """Link each town to its nearest anchors, at the pace of the surveyed lines."""
    target = seats[seats.mun.isin(anchors)]
    if target.empty:
        return
    lat, lon, codes = target.lat.to_numpy(), target.lon.to_numpy(), target.mun.to_numpy()
    for row in seats[seats.mun.isin(towns)].itertuples():
        km = haversine_km(row.lat, row.lon, lat, lon)
        for i in np.argsort(km)[:neighbours]:
            graph.add_edge(row.mun, codes[i], minutes=float(km[i] * minutes_per_km), estimated=True)


def minutes_to_nearest(graph: nx.Graph, sources: set[str]) -> dict[str, float]:
    """Travel time from each municipality to the nearest source. A source is at
    zero. A municipality with no path is absent from the result."""
    inside = sources & set(graph.nodes)
    if not inside:
        return {}
    times = nx.multi_source_dijkstra_path_length(graph, inside, weight="minutes")
    return {**times, **{s: 0.0 for s in sources}}


def straight_minutes(seats: pd.DataFrame, sources: set[str], minutes_per_km: float) -> dict:
    """The same, on straight lines only. Used as a check on the network."""
    target = seats[seats.mun.isin(sources)]
    if target.empty:
        return {}
    lat, lon = target.lat.to_numpy(), target.lon.to_numpy()
    out = {}
    for mun, mlat, mlon in zip(seats.mun, seats.lat, seats.lon, strict=True):
        out[mun] = float(haversine_km(mlat, mlon, lat, lon).min() * minutes_per_km)
    return {**out, **{s: 0.0 for s in sources}}


def reach(graph: nx.Graph, origin: str, minutes: float) -> set[str]:
    """Municipalities within a travel time of one municipality."""
    return set(
        nx.single_source_dijkstra_path_length(graph, origin, cutoff=minutes, weight="minutes")
    )
