import pandas as pd
import pytest

from nicu import access

# Five towns on the equator, one degree apart (about 111 km). A, B and C are on a
# surveyed line, D shares an urban arrangement with C, E is outside the survey.
SEATS = pd.DataFrame(
    {
        "mun": list("ABCDE"),
        "lat": [0.0] * 5,
        "lon": [0.0, 1.0, 2.0, 2.1, -0.5],
    }
)
LINKS = pd.DataFrame({"mun_a": ["A", "B"], "mun_b": ["B", "C"], "minutes": [111.0, 222.0]})
ARRANJOS = pd.DataFrame({"arranjo": ["C-D", "C-D"], "mun": ["C", "D"]})


def test_pace_is_the_median_minutes_per_kilometre():
    assert access.pace(LINKS, SEATS) == pytest.approx(1.5, rel=0.01)  # 1 and 2 min per km


def test_times_follow_the_lines_then_the_arrangement_link():
    graph = access.build_graph(LINKS, ARRANJOS, SEATS)
    times = access.minutes_to_nearest(graph, {"A"})
    assert times["A"] == 0
    assert times["B"] == 111
    assert times["C"] == 333
    assert times["D"] == 333 + access.ARRANGEMENT_MINUTES


def test_a_town_outside_the_survey_is_attached_at_the_observed_pace():
    graph = access.build_graph(LINKS, ARRANJOS, SEATS)
    times = access.minutes_to_nearest(graph, {"A"})
    assert times["E"] == pytest.approx(55.6 * 1.5, rel=0.01)  # half a degree from A
    assert graph["E"]["A"]["estimated"]


def test_without_arrangement_links_the_suburb_has_no_path():
    graph = access.build_graph(LINKS, ARRANJOS, SEATS, arrangement_minutes=0, neighbours=0)
    assert "D" not in access.minutes_to_nearest(graph, {"A"})


def test_a_source_outside_the_network_is_still_at_zero():
    graph = access.build_graph(LINKS, ARRANJOS, SEATS, neighbours=0)
    assert access.minutes_to_nearest(graph, {"A", "Z"})["Z"] == 0
    assert access.minutes_to_nearest(graph, {"Z"}) == {}


def test_reach_stops_at_the_travel_time():
    graph = access.build_graph(LINKS, ARRANJOS, SEATS)
    assert access.reach(graph, "B", 120) == {"A", "B"}


def test_straight_lines_ignore_the_network():
    times = access.straight_minutes(SEATS, {"A"}, minutes_per_km=1.0)
    assert times["C"] == pytest.approx(222.4, rel=0.01)
    assert times["A"] == 0


def test_towns_linked_only_to_each_other_are_joined_to_the_rest():
    pair = pd.DataFrame({"mun": ["F", "G"], "lat": [1.0, 1.0], "lon": [1.0, 1.1]})
    seats = pd.concat([SEATS[SEATS.mun != "E"], pair])
    links = pd.concat([LINKS, pd.DataFrame({"mun_a": ["F"], "mun_b": ["G"], "minutes": [20.0]})])
    alone = access.build_graph(links, ARRANJOS, seats, neighbours=0)
    assert "F" not in access.minutes_to_nearest(alone, {"A"})
    graph = access.build_graph(links, ARRANJOS, seats)
    assert graph["F"]["B"]["estimated"]  # B is the nearest town of the main network
    times = access.minutes_to_nearest(graph, {"B"})
    assert times["F"] == pytest.approx(111.2 * access.pace(links, seats), rel=0.01)
    assert times["G"] <= times["F"] + 20
