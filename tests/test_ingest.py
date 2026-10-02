import json

import pandas as pd
import pytest

from nicu import config as C
from nicu import fetch, ingest

BIRTHS = pd.DataFrame(
    {
        "CODMUNRES": pd.array([280030, 280480], dtype="Int64"),  # the mirror types it
        "CODESTAB": ["0002232", "2546027"],
        "PESO": ["1200", "3400"],
        "contador": [1, 2],  # dropped, not in the kept columns
    }
)


def fake_births(uf, year, prelim=False):
    return fetch.Fetched(BIRTHS, "origin" if prelim else "mirror")


def lines(root):
    return [json.loads(x) for x in (root / "manifest.jsonl").read_text().splitlines()]


def test_writes_one_file_per_state_and_year_and_records_it(tmp_path):
    out = ingest.ingest_sinasc([2010], ["SE", "AL"], root=tmp_path, fetcher=fake_births)
    assert [o.status for o in out] == ["written", "written"]
    frame = pd.read_parquet(tmp_path / "raw" / "sinasc" / "DNSE2010.parquet")
    assert list(frame.columns) == list(C.SINASC_COLUMNS)
    assert frame.CODMUNRES.tolist() == ["280030", "280480"]
    entry = lines(tmp_path)[0]
    assert entry["path"] == f"{tmp_path.name}/raw/sinasc/DNSE2010.parquet"
    assert (entry["source"], entry["rows"], entry["status"]) == ("mirror", 2, "final")


def test_rerun_skips_recorded_files_unless_forced(tmp_path):
    ingest.ingest_sinasc([2010], ["SE"], root=tmp_path, fetcher=fake_births)
    again = ingest.ingest_sinasc([2010], ["SE"], root=tmp_path, fetcher=pytest.fail)
    assert again[0].status == "skipped"
    forced = ingest.ingest_sinasc([2010], ["SE"], root=tmp_path, fetcher=fake_births, force=True)
    assert forced[0].status == "written" and len(lines(tmp_path)) == 2


def test_a_failure_is_reported_and_the_run_goes_on(tmp_path):
    def flaky(uf, year, prelim=False):
        if uf == "SE":
            raise ConnectionError("FTP down")
        return fake_births(uf, year)

    out = ingest.ingest_sinasc([2010], ["SE", "AL"], root=tmp_path, fetcher=flaky)
    assert [o.status for o in out] == ["failed", "written"]
    assert "FTP down" in out[0].error
    assert [e["uf"] for e in lines(tmp_path)] == ["AL"]  # nothing recorded for the failure


def test_preliminary_year_is_labelled(tmp_path):
    out = ingest.ingest_sinasc([2025], ["SE"], root=tmp_path, fetcher=fake_births)
    assert out[0].source == "origin"
    assert (tmp_path / "raw" / "sinasc" / "DNSE2025_prelim.parquet").exists()
    assert lines(tmp_path)[0]["status"] == "prelim"


def test_beds_of_2007_are_read_in_november(tmp_path):
    calls = []

    def beds(uf, year, month):
        calls.append(month)
        return fetch.Fetched(pd.DataFrame({"CNES": ["2421488"], "QT_EXIST": [7]}), "mirror")

    ingest.ingest_cnes_lt([2006, 2007], ["SE"], root=tmp_path, fetcher=beds)
    assert calls == [12, 11]
    assert (tmp_path / "raw" / "cnes_lt" / "LTSE200711.parquet").exists()


def test_missing_lists_what_the_study_still_needs(tmp_path):
    ingest.ingest_sinasc([2010], ["SE"], root=tmp_path, fetcher=fake_births)
    gaps = ingest.missing(root=tmp_path, years=[2010], ufs=["SE"])
    assert gaps == ingest.IBGE_KEYS + [("cnes_lt", "SE", 2010, 12, "final")]


def test_expected_covers_twenty_years_of_both_datasets_and_ibge():
    assert len(ingest.expected()) == 20 * 27 * 2 + 3


def test_compare_ignores_types_and_row_order():
    mirror = pd.DataFrame({"QT_EXIST": ["7", "0"], "CNES": ["1", "2"]})
    origin = pd.DataFrame({"CNES": ["2", "1"], "QT_EXIST": [0, 7]})
    assert ingest.compare(mirror, origin).identical


def test_compare_counts_rows_that_differ_and_extra_columns():
    mirror = pd.DataFrame({"A": ["1", "2"], "EXTRA": ["x", "y"]})
    origin = pd.DataFrame({"A": ["1", "3"]})
    c = ingest.compare(mirror, origin)
    assert (c.rows_differing, c.only_mirror, c.identical) == (2, ("EXTRA",), False)


def test_content_hash_does_not_depend_on_row_order():
    a = pd.DataFrame({"A": ["1", "2"], "B": ["x", None]})
    assert ingest._content_hash(a) == ingest._content_hash(a.iloc[::-1])


def test_compare_with_an_empty_source_reports_every_row_as_unmatched():
    origin = pd.DataFrame({"A": ["1", "2"]})
    c = ingest.compare(pd.DataFrame(), origin)
    assert (c.rows_mirror, c.rows_origin, c.rows_differing, c.identical) == (0, 2, 2, False)
