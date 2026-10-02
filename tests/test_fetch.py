import ftplib

import pandas as pd
import pytest

from nicu import fetch


class FakeFTP:
    """Just enough of ftplib.FTP: a few files, and a connection that can drop."""

    def __init__(self, files, drop_after=None, listing_error=None):
        self.files = files
        self.drop_after = drop_after
        self.listing_error = listing_error
        self.rests = []

    def voidcmd(self, cmd):
        pass

    def size(self, remote):
        if remote not in self.files:
            raise ftplib.error_perm("550 Could not get file size.")
        return len(self.files[remote])

    def retrbinary(self, cmd, callback, rest=None):
        remote = cmd.split(" ", 1)[1]
        if remote not in self.files:
            raise ftplib.error_perm("550 Failed to open file.")
        self.rests.append(rest)
        data = self.files[remote][rest or 0 :]
        if self.drop_after is not None:
            callback(data[: self.drop_after])
            raise TimeoutError("connection dropped")
        callback(data)

    def nlst(self, directory):
        if self.listing_error:
            raise self.listing_error
        return [f"{directory}/{name.rsplit('/', 1)[1]}" for name in self.files]

    def quit(self):
        pass

    def close(self):
        pass


def connections(*ftps):
    pending = list(ftps)
    return lambda timeout: pending.pop(0)


REMOTE = "/dissemin/DNSE2024.dbc"
PAYLOAD = bytes(range(256)) * 4


def test_download_resumes_after_a_dropped_connection(tmp_path):
    first = FakeFTP({REMOTE: PAYLOAD}, drop_after=100)
    second = FakeFTP({REMOTE: PAYLOAD})
    dest = fetch.download(
        REMOTE, tmp_path / "DNSE2024.dbc", connect=connections(first, second), sleep=lambda s: None
    )
    assert dest.read_bytes() == PAYLOAD
    assert second.rests == [100]  # restarted from the byte where the first transfer stopped
    assert not (tmp_path / "DNSE2024.dbc.part").exists()


def test_download_gives_up_after_the_last_attempt(tmp_path):
    drops = [FakeFTP({REMOTE: PAYLOAD}, drop_after=0) for _ in range(3)]
    with pytest.raises(ConnectionError, match="3 attempts"):
        fetch.download(
            REMOTE, tmp_path / "x.dbc", connect=connections(*drops), retries=3, sleep=lambda s: None
        )
    assert not (tmp_path / "x.dbc").exists()  # never a final name for a partial file


def test_missing_remote_file_is_not_retried(tmp_path):
    with pytest.raises(FileNotFoundError):
        fetch.download(
            "/nowhere.dbc",
            tmp_path / "x.dbc",
            connect=connections(FakeFTP({})),
            sleep=lambda s: None,
        )


def test_listing_is_retried_then_cached():
    fetch._listings.clear()
    flaky = FakeFTP({}, listing_error=TimeoutError("timeout"))
    ok = FakeFTP({"/d/DNSE2010.DBC": b"", "/d/DNSE2024.dbc": b""})
    names = fetch.list_remote("/d", connect=connections(flaky, ok), sleep=lambda s: None)
    assert names == ["DNSE2010.DBC", "DNSE2024.dbc"]
    assert fetch.list_remote("/d", connect=connections()) == names  # no new connection


def test_resolve_ignores_extension_case():
    names = ["DNSE2010.DBC", "DNSE2024.dbc"]
    assert fetch.resolve("/d", "DNSE2010.dbc", names) == "/d/DNSE2010.DBC"
    assert fetch.resolve("/d", "DNSE2024.dbc", names) == "/d/DNSE2024.dbc"
    with pytest.raises(FileNotFoundError):
        fetch.resolve("/d", "DNSE2030.dbc", names)


ROWS = pd.DataFrame({"PESO": ["1200"]})
EMPTY = pd.DataFrame()


def test_mirror_first():
    got = fetch.fetch_sinasc("SE", 2010, mirror=lambda uf, y: ROWS, origin=pytest.fail)
    assert got.source == "mirror"


def test_origin_when_the_mirror_is_empty():
    got = fetch.fetch_sinasc(
        "SE", 2024, mirror=lambda uf, y: EMPTY, origin=lambda uf, y, prelim, wd: ROWS
    )
    assert got.source == "origin"


def test_preliminary_years_skip_the_mirror():
    calls = []
    got = fetch.fetch_sinasc(
        "SE",
        2025,
        prelim=True,
        mirror=pytest.fail,
        origin=lambda uf, y, prelim, wd: calls.append(prelim) or ROWS,
    )
    assert got.source == "origin" and calls == [True]


def test_both_empty_is_an_error():
    with pytest.raises(fetch.EmptySourceError):
        fetch.fetch_cnes_lt(
            "SE", 2010, 12, mirror=lambda uf, y, m: EMPTY, origin=lambda uf, y, m, wd: EMPTY
        )


def test_as_text_aligns_typed_and_text_columns():
    typed = pd.DataFrame({"QT": [7, 0], "F": [3.0, None], "S": [" 0002232 ", ""]})
    text = fetch.as_text(typed)
    assert text.QT.tolist() == ["7", "0"]
    assert text.F.tolist()[0] == "3" and pd.isna(text.F.tolist()[1])
    assert text.S.tolist()[0] == "0002232" and pd.isna(text.S.tolist()[1])


def test_keep_adds_missing_columns_in_order():
    out = fetch.keep(pd.DataFrame({"B": [1], "A": [2], "Z": [3]}), ("A", "B", "C"))
    assert list(out.columns) == ["A", "B", "C"]
    assert pd.isna(out.C.iloc[0])


def test_backoff_is_short_and_capped():
    assert [fetch.backoff(a) for a in (1, 2, 5, 12)] == [1.0, 2.0, 5.0, 5.0]


def test_mirror_keeps_ftp_files_whatever_the_path_flavour():
    from pathlib import PurePosixPath, PureWindowsPath
    from types import SimpleNamespace

    key = "public/data/ftp/sinasc/DN/2010/_/SE/DNSE2010.parquet"
    files = [
        SimpleNamespace(path=PureWindowsPath(key)),  # what PySUS holds on Windows
        SimpleNamespace(path=PurePosixPath(key)),
        SimpleNamespace(path=PurePosixPath("public/data/dadosgov/sinasc/x.parquet")),
    ]
    assert fetch.ftp_files(files) == files[:2]
    assert not str(files[0].path).startswith(fetch.MIRROR_FTP_PREFIX)  # the upstream test fails
