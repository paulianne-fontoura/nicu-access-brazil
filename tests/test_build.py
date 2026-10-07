import json

import pandas as pd
import pytest

from nicu import build


def births(rows):
    cols = ["CODMUNRES", "CODMUNNASC", "CODESTAB", "LOCNASC", "PESO", "GESTACAO"]
    return pd.DataFrame(rows, columns=cols, dtype="string")


def beds(rows):
    cols = ["CNES", "CODUFMUN", "CODLEITO", "QT_EXIST", "QT_SUS"]
    return pd.DataFrame(rows, columns=cols, dtype="string")


@pytest.fixture
def raw(tmp_path):
    """Two states (codes 11 and 12), two years, the second one preliminary."""
    folder = tmp_path / "raw"
    for sub in ("sinasc", "cnes_lt", "ibge"):
        (folder / sub).mkdir(parents=True)
    state_a = births(
        [
            ("110001", "110001", "0000011", "1", "1200", "3"),  # at risk, born at home town
            ("110001", "110002", "12345", "1", "1200", "3"),  # at risk, short facility code
            ("110001", "110002", "0000022", "1", "400", "1"),  # under 500 g
            ("110002", "110002", "0000022", "1", "3000", "2"),  # under 32 weeks, normal weight
            ("110002", "110002", None, "3", None, "5"),  # weight missing, born at home
            ("110002", "110002", "0000022", "1", "3200", "5"),
        ]
    )
    state_b = births([("120001", "120001", "0000033", "1", "1499", "4")])
    for year, suffix in ((2010, ""), (2011, "_prelim")):
        state_a.to_parquet(folder / "sinasc" / f"DNAA{year}{suffix}.parquet")
        state_b.to_parquet(folder / "sinasc" / f"DNBB{year}{suffix}.parquet")
    for year in (2010, 2011):
        beds(
            [
                ("0000022", "110002", "63", "10", "6"),  # old code
                ("0000022", "110002", "81", "4", "4"),  # and new code, same facility
                ("0000022", "110002", "33", "50", "50"),  # not a NICU bed
                ("0000011", "110001", "80", "3", "0"),  # type I, no SUS bed
            ]
        ).to_parquet(folder / "cnes_lt" / f"LTAA{year}12.parquet")
        beds([("0000033", "120001", "82", "2", "2")]).to_parquet(
            folder / "cnes_lt" / f"LTBB{year}12.parquet"
        )
    for name in ("links", "arranjos", "seats"):
        pd.DataFrame({"x": [1]}).to_parquet(folder / "ibge" / f"{name}.parquet")
    return folder


def run(raw, tmp_path, years=(2010, 2011)):
    out = tmp_path / "processed"
    summary = build.build(raw, out, years=years, n_states=2)
    return out, summary


def test_risk_groups_follow_weight_then_gestation(raw, tmp_path):
    out, _ = run(raw, tmp_path)
    risk = pd.read_parquet(out / "births_at_risk.parquet")
    groups = risk.groupby(["year", "risk_group"]).n.sum().to_dict()
    assert groups == {
        (2010, "w500_1499"): 3,
        (2010, "w_under_500"): 1,
        (2011, "w500_1499"): 3,
        (2011, "w_under_500"): 1,
        (2011, "g_under_32_only"): 1,  # gestational age only counts from 2011
    }
    assert set(risk.status[risk.year == 2011]) == {"prelim"}
    assert "0012345" in set(risk.cnes)  # facility codes padded to seven digits


def test_births_are_counted_by_residence_and_by_place(raw, tmp_path):
    out, _ = run(raw, tmp_path)
    home = pd.read_parquet(out / "births_by_residence.parquet")
    row = home[(home.year == 2010) & (home.mun_res == "110002")].iloc[0]
    assert (row.n, row.n_weight_missing) == (3, 1)
    place = pd.read_parquet(out / "births_by_place.parquet")
    assert place[(place.year == 2010) & (place.cnes == "0000022")].n.sum() == 3


def test_beds_keep_the_larger_of_old_and_new_codes(raw, tmp_path):
    out, _ = run(raw, tmp_path)
    nicu = pd.read_parquet(out / "nicu_beds.parquet").query("year == 2010").set_index("cnes")
    assert (nicu.loc["0000022", "beds"], nicu.loc["0000022", "beds_sus"]) == (10, 6)
    assert (nicu.loc["0000011", "beds"], nicu.loc["0000011", "beds_sus"]) == (3, 0)
    assert len(nicu) == 3


def test_summary_is_written(raw, tmp_path):
    out, summary = run(raw, tmp_path)
    saved = json.loads((out / "build.json").read_text())
    assert saved == summary
    first = summary["by_year"][0]
    assert (first["year"], first["births"], first["w500_1499"], first["beds_sus"]) == (
        2010,
        7,
        3,
        8,
    )
    assert (out / "ibge_links.parquet").exists()


def test_a_missing_state_stops_the_build(raw, tmp_path):
    (raw / "sinasc" / "DNBB2010.parquet").unlink()
    with pytest.raises(build.BuildError, match="births 2010: 1 states out of 2"):
        run(raw, tmp_path)


def test_a_missing_year_of_beds_stops_the_build(raw, tmp_path):
    with pytest.raises(build.BuildError, match="beds 2012: no file"):
        run(raw, tmp_path, years=(2010, 2011, 2012))
