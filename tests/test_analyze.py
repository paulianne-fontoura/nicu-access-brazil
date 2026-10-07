import pandas as pd
import pytest

from nicu import analyze

# Towns in state 11 (region Norte). A has the NICU from the first year, D opens one
# in the second year. C is three hours from A and half an hour from D.
SEATS = pd.DataFrame(
    {
        "mun": ["110001", "110002", "110003", "110004"],
        "name": ["A", "B", "C", "D"],
        "uf": ["RO"] * 4,
        "lat": [0.0, 0.0, 0.0, 0.0],
        "lon": [0.0, 0.5, 1.5, 1.75],
    }
)
LINKS = pd.DataFrame(
    {
        "mun_a": ["110001", "110002", "110003"],
        "mun_b": ["110002", "110003", "110004"],
        "minutes": [60.0, 120.0, 30.0],
    }
)


def risk(year, rows):
    cols = ["mun_res", "mun_birth", "cnes", "n"]
    return pd.DataFrame(rows, columns=cols).assign(
        year=year, status="final", risk_group="w500_1499"
    )


@pytest.fixture
def data():
    at_risk = pd.concat(
        [
            risk(2020, [("110001", "110001", "0000001", 10), ("110002", "110001", "0000001", 6),
                        ("110002", "110002", "0000002", 4), ("110003", "110003", "0000003", 20)]),
            risk(2021, [("110001", "110001", "0000001", 10), ("110003", "110004", "0000004", 30)]),
        ]
    )  # fmt: skip
    beds = pd.DataFrame(
        [
            (2020, 12, "0000001", "110001", 8, 5),
            (2021, 12, "0000001", "110001", 10, 5),
            (2021, 12, "0000004", "110004", 6, 6),
        ],
        columns=["year", "month", "cnes", "mun", "beds", "beds_sus"],
    )
    by_place = pd.DataFrame(
        [(y, m, f"000000{m[-1]}", n) for y in (2020, 2021)
         for m, n in (("110001", 5000), ("110002", 400), ("110003", 1500), ("110004", 1200))],
        columns=["year", "mun_birth", "cnes", "n"],
    )  # fmt: skip
    return analyze.Data(
        at_risk=at_risk,
        by_place=by_place,
        by_residence=pd.DataFrame(),
        beds=beds,
        links=LINKS,
        arranjos=pd.DataFrame({"arranjo": [], "mun": []}),
        seats=SEATS,
    )


def test_access_shares_for_the_country(data):
    network, _ = analyze.networks(data)
    table = analyze.access(data, network)
    row = table.query("year == 2020 and scope == 'sus' and level == 'country'").iloc[0]
    assert row.births == 40
    assert row.share_born_in_nicu_facility == pytest.approx(16 / 40)
    assert row.share_lives_in_nicu_municipality == pytest.approx(10 / 40)
    assert row.share_over_120_min == pytest.approx(20 / 40)  # C is 180 minutes from A
    assert row.share_over_180_min == 0
    assert row.births_over_main == 20
    assert set(table.level) == {"country", "region", "state"}
    assert set(table.query("level == 'state'").area) == {"RO"}
    assert set(table.status) == {"final"}


def test_bed_growth_separates_old_and_new_municipalities(data):
    growth = analyze.bed_growth(data, 2020, 2021, "all")
    assert growth["beds_change"] == 8
    assert growth["change_where_already_present"] == 2
    assert (growth["beds_in_new_municipalities"], growth["new_municipalities"]) == (6, 1)


def test_decomposition_adds_up(data):
    network, _ = analyze.networks(data)
    row = analyze.decomposition(data, network, 2020, 2021).query("scope == 'sus'").iloc[0]
    assert row.share_first == pytest.approx(0.5)
    assert row.share_last == 0  # D now serves C
    assert row.beds_effect + row.births_effect == pytest.approx(row.change)
    assert row.share_first_births_last_beds == 0  # the new unit alone removes the gap


def test_candidates_need_enough_births_and_no_nicu(data):
    assert analyze.candidates(data, 2020, {"110001"}, 1000) == {"110003", "110004"}


def test_location_model_beats_the_greedy_choice():
    births = pd.Series({"a": 10, "b": 11, "c": 11, "d": 10})
    cover = {"middle": {"b", "c"}, "left": {"a", "b"}, "right": {"c", "d"}}
    assert analyze.solve(births, cover, 1) == (["middle"], 22)
    assert analyze.solve(births, cover, 2) == (["left", "right"], 42)  # greedy would stop at 32
    assert analyze.solve(births, cover, 5) == (["left", "middle", "right"], 42)
    assert analyze.solve(births, {"nowhere": {"z"}}, 1) == ([], 0)


def test_sites_and_ranking(data):
    network, straight = analyze.networks(data)
    chosen, coverage = analyze.sites(data, network, years=[2020], units=(1,), thresholds=(120,))
    assert set(chosen.basis) == {"pooled", "year"}
    assert set(chosen.mun) <= {"110003", "110004"}  # either serves C, 30 minutes apart
    row = coverage.query("basis == 'pooled'").iloc[0]
    assert (row.births_uncovered, row.births_newly_covered, row.candidates) == (20, 20, 2)
    line, _ = analyze.sites(data, straight, years=[2020], units=(1,), thresholds=(120,))
    ranking = analyze.ranking(chosen, line, data.seats)
    assert len(ranking) == 1
    assert ranking.years_chosen.iloc[0] in (0, 1)
    assert ranking.births_within_reach_per_year.iloc[0] == 20
    assert ranking.name.iloc[0] in {"C", "D"}


def test_pooled_years_use_the_latest_nicu_map(data):
    network, _ = analyze.networks(data)
    chosen, coverage = analyze.sites(data, network, units=(1,), thresholds=(120,))
    pooled = coverage.query("basis == 'pooled'").iloc[0]
    assert (pooled.year, pooled.years) == (2021, 2)
    assert pooled.births_uncovered == 0  # D opened in 2021 and serves C
    assert chosen.query("basis == 'pooled'").empty


def test_run_writes_one_csv_per_table(data, tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    names = {"at_risk": "births_at_risk", "by_place": "births_by_place", "beds": "nicu_beds",
             "by_residence": "births_by_residence", "links": "ibge_links",
             "arranjos": "ibge_arranjos", "seats": "ibge_seats"}  # fmt: skip
    for field, name in names.items():
        getattr(data, field).to_parquet(processed / f"{name}.parquet")
    tables = analyze.run(processed, tmp_path / "results")
    assert sorted(p.stem for p in (tmp_path / "results").glob("*.csv")) == sorted(tables)
    assert len(tables) == 7


def test_sensitivity_covers_groups_and_arrangement_times(data):
    table = analyze.sensitivity(data)
    assert set(table.arrangement_minutes) == {30.0, 60.0, 90.0}
    assert set(table.risk_group) == {"w500_1499"}
    assert len(table) == 3 * 2  # three settings, two years
