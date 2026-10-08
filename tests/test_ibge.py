import gzip
import io
import json
import sqlite3
import zipfile
from contextlib import closing

import pandas as pd

from nicu import ibge


def test_links_keep_the_fastest_line_per_pair_and_drop_foreign_ends(tmp_path):
    rows = pd.DataFrame(
        {
            "CODMUNDV_A": [1302603, 2800308, 2800308, 1302603],
            "CODMUNDV_B": [1304260, 2804805, 2804805, 8000011],
            "VAR03": [50.0, 10.0, 12.0, 300.0],
            "VAR04": [2160, 45, 40, 900],
            "VAR05": [7.5, 0, 0, 1],
            "VAR06": [0, 30, 10, 0],
        }
    )
    # the same pair, written the other way round, with a faster line
    rows.loc[len(rows)] = [2804805, 2800308, 9.0, 35, 0, 5]
    xlsx = tmp_path / "links.xlsx"
    rows.to_excel(xlsx, sheet_name="Base de dados", index=False)

    links = ibge.parse_links(xlsx)
    assert links[["mun_a", "mun_b"]].values.tolist() == [["130260", "130426"], ["280030", "280480"]]
    assert links.minutes.tolist() == [2160.0, 35.0]


def test_arranjos_follow_the_heading_lines(tmp_path):
    table = pd.DataFrame(
        [
            ["Tabela 1.1", None],
            ["Arranjos populacionais e municípios brasileiros", "Código do município"],
            ["São Luís/MA", None],
            ["São Luís (MA)", 2111300],
            ["São José de Ribamar (MA)", 2111201],
            ["Goiânia/GO", None],
            ["Senador Canedo (GO)", 5220454],
            ["Fonte: IBGE", None],
        ]
    )
    xlsx = tmp_path / "tab01.xlsx"
    table.to_excel(xlsx, header=False, index=False)

    arr = ibge.parse_arranjos(xlsx)
    assert arr.values.tolist() == [
        ["São Luís/MA", "211130"],
        ["São Luís/MA", "211120"],
        ["Goiânia/GO", "522045"],
    ]


def test_seats_are_read_from_the_geopackage(tmp_path):
    gpkg = tmp_path / "loc.gpkg"
    with closing(sqlite3.connect(gpkg)) as con, con:
        con.execute("create table gpkg_contents (table_name text, data_type text)")
        con.execute("insert into gpkg_contents values ('BR_localidades_2022', 'features')")
        con.execute(
            "create table BR_localidades_2022 (CD_MUN text, NM_MUN text, SIGLA_UF text,"
            " SCT_LOCALIDADE text, LAT_LOCALIDADE real, LONG_LOCALIDADE real)"
        )
        con.executemany(
            "insert into BR_localidades_2022 values (?, ?, ?, ?, ?, ?)",
            [
                ("2800308", "Aracaju", "SE", "Sede Municipal", -10.91, -37.07),
                ("2800308", "Aracaju", "SE", "Povoado", -10.95, -37.10),
                ("1100015", "Alta Floresta D'Oeste", "RO", "Sede Municipal", -11.93, -62.00),
                ("5300108", "Brasília", "DF", "Outras Localidades", -15.70, -47.90),
                ("5300108", "Brasília", "DF", "Capital Federal", -15.78, -47.93),
            ],
        )
    archive = tmp_path / "loc.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(gpkg, "BR_localidades_2022.gpkg")

    seats = ibge.parse_seats(archive)
    assert seats.mun.tolist() == ["110001", "280030", "530010"]
    assert seats.loc[seats.mun == "280030", "lat"].item() == -10.91  # the seat, not the hamlet
    assert seats.loc[seats.mun == "530010", "lat"].item() == -15.78  # Brasília has no seat


def test_ingest_skips_recorded_files(tmp_path, monkeypatch):
    calls = []

    def fake_download(url, dest):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")
        return dest

    monkeypatch.setattr(ibge, "download", fake_download)
    parsers = {
        name: (url, f, lambda p: pd.DataFrame({"a": [1]}), y)
        for name, (url, f, _, y) in ibge.SOURCES.items()
    }
    monkeypatch.setattr(ibge, "SOURCES", parsers)
    assert set(ibge.ingest(root=tmp_path).values()) == {1}
    assert set(ibge.ingest(root=tmp_path).values()) == {None}
    assert len(calls) == len(ibge.SOURCES) == 4
    ibge.ingest(root=tmp_path, force=True)
    assert len(calls) == 8


def test_states_become_one_row_per_point(tmp_path):
    square = [[[0, 0], [1, 0], [1, 1], [0, 0]]]
    features = [
        {"type": "Feature", "properties": {"codarea": "28"},
         "geometry": {"type": "Polygon", "coordinates": square}},
        {"type": "Feature", "properties": {"codarea": "11"},
         "geometry": {"type": "MultiPolygon", "coordinates": [square, square]}},
    ]  # fmt: skip
    path = tmp_path / "states.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    states = ibge.parse_states(path)
    assert len(states) == 3 * 4
    assert states.groupby("uf_code").part.nunique().to_dict() == {"11": 2, "28": 1}
    assert states.iloc[0][["uf_code", "part", "ring", "point", "lon", "lat"]].tolist() == [
        "11",
        0,
        0,
        0,
        0,
        0,
    ]


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, encoding: str | None):
        super().__init__(body)
        self.headers = {"Content-Encoding": encoding} if encoding else {}


def test_download_undoes_gzip_when_the_server_compresses(tmp_path, monkeypatch):
    body = b'{"type": "FeatureCollection", "features": []}'
    answers = iter([FakeResponse(gzip.compress(body), "gzip"), FakeResponse(body, None)])
    monkeypatch.setattr(ibge.urllib.request, "urlopen", lambda url, timeout: next(answers))
    assert ibge.download("https://x", tmp_path / "a.json").read_bytes() == body
    assert ibge.download("https://x", tmp_path / "b.json").read_bytes() == body
