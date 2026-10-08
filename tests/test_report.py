"""The note's numbers, on the versioned results.

`data/processed` and `data/results` are small and versioned, so these tests run
on the real counts, without network and without the raw files.
"""

import re

import pandas as pd
import pytest

from nicu import report

NOTE = report.REPORT_DIR / "note.tex"


@pytest.fixture(scope="module")
def inputs():
    return report.Inputs.load()


@pytest.fixture(scope="module")
def written(inputs, tmp_path_factory):
    out = tmp_path_factory.mktemp("report")
    values = report.run(inputs, out)
    return out, values


def test_numbers_are_written_the_english_and_the_portuguese_way():
    assert report.count(2312.0) == "2,312"
    assert report.pct(0.13985) == "14.0\\,\\%"
    assert report.pct(0.195, 0) == "20\\,\\%"
    assert report.points(-0.047) == "$-$4.7"
    assert report.points(0.024) == "+2.4"
    assert report.pt_count(693038) == "693.038"
    assert report.pt_pct(0.4768) == "47,7\\,\\%"
    assert report.word(2) == "two"
    sites = pd.DataFrame({"name": ["Arcoverde", "Jacobina", "Crateús"], "uf": ["PE", "BA", "CE"]})
    assert report.names(sites) == "Arcoverde (PE), Jacobina (BA) and Crateús (CE)"
    assert report.names(sites.head(1)) == "Arcoverde (PE)"


def test_every_macro_of_the_note_is_written(written):
    out, values = written
    used = set(re.findall(r"\\([A-Za-z]+)", NOTE.read_text(encoding="utf-8")))
    numbers = (out / "numbers.tex").read_text(encoding="utf-8")
    defined = set(re.findall(r"\\newcommand\{\\(\w+)\}", numbers))
    assert defined == set(values)
    unused = defined - used
    assert not unused, f"numbers written but never cited: {sorted(unused)}"
    for name in ("access.png", "map.png"):
        assert (out / "figures" / name).stat().st_size > 10_000


def test_committed_numbers_and_tables_match_the_results(written):
    """Rerun `nicu report` and commit when the results change."""
    out, _ = written
    for name in ("numbers.tex", "table_regions.tex", "table_sites.tex"):
        committed = (report.REPORT_DIR / name).read_text(encoding="utf-8")
        assert (out / name).read_text(encoding="utf-8") == committed, name


def test_tables_have_one_row_per_region_and_per_site(written):
    out, _ = written
    regions = (out / "table_regions.tex").read_text(encoding="utf-8")
    assert all(name in regions for name in ("Norte", "Nordeste", "Sudeste", "Sul", "Centro-Oeste"))
    assert regions.count("\\\\") == 3 + 6  # three header lines, five regions and Brazil
    sites = (out / "table_sites.tex").read_text(encoding="utf-8")
    assert sites.count(" of ") == report.TEN


def test_a_claim_the_data_no_longer_supports_stops_the_report(inputs):
    access = inputs.access.copy()
    north = (access.level == "region") & (access.area == report.NORTE)
    access.loc[north, "share_over_120_min"] = 0.0
    changed = report.Inputs(**{**inputs.__dict__, "access": access})
    with pytest.raises(report.ReportError, match="the North is the region farthest"):
        report.numbers(changed)
