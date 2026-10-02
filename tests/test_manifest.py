from pathlib import Path

from nicu import manifest


def test_paths_are_portable(tmp_path):
    dest = tmp_path / "data" / "raw" / "sinasc" / "DNSE2010.parquet"
    assert manifest.portable(dest, tmp_path) == "data/raw/sinasc/DNSE2010.parquet"


def test_latest_keeps_the_last_entry_per_file(tmp_path):
    path = tmp_path / "manifest.jsonl"
    base = {"dataset": "sinasc", "uf": "SE", "year": 2010, "month": None, "status": "final"}
    manifest.append(path, {**base, "rows": 1})
    manifest.append(path, {**base, "rows": 2})
    manifest.append(path, {**base, "uf": "AL", "rows": 3})
    latest = manifest.latest(path)
    assert latest[("sinasc", "SE", 2010, None, "final")]["rows"] == 2
    assert len(latest) == 2
    assert "\r\n" not in path.read_bytes().decode()


def test_missing_manifest_is_empty(tmp_path):
    assert manifest.load(Path(tmp_path / "none.jsonl")) == []
