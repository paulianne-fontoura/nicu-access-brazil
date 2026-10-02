"""Read raw files from the PySUS mirror, or from the DATASUS FTP origin.

The mirror (parquet on S3, served by PySUS) is fast and stable but lags the
origin: on 1 October 2026 it had no SINASC file after 2022 and answered with
an empty result instead of an error. The FTP origin has every year, including
the preliminary ones, but drops connections often. Hence the order (ADR-0004):
mirror first, origin when the mirror is empty or when the year is
preliminary, and an error when both are empty. An empty frame is never
written as if it were data.
"""

from __future__ import annotations

import ftplib
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath

import pandas as pd

from nicu import config as C


class EmptySourceError(RuntimeError):
    """Neither the mirror nor the origin returned rows for a file."""


@dataclass(frozen=True)
class Fetched:
    frame: pd.DataFrame
    source: str  # "mirror" or "origin"


# --- text normalisation -------------------------------------------------------


def as_text(frame: pd.DataFrame) -> pd.DataFrame:
    """Every column as trimmed text, integers without a decimal part.

    The mirror and the origin do not type columns the same way (QT_EXIST is
    text in the mirror and an integer in the DBF), so the raw layer keeps text
    only and the comparison between sources works column by column.
    """
    out = {}
    for name, col in frame.items():
        if pd.api.types.is_bool_dtype(col):
            col = col.astype("string")
        elif pd.api.types.is_integer_dtype(col):
            col = col.astype("Int64").astype("string")
        elif pd.api.types.is_float_dtype(col):
            whole = col.dropna()
            if (whole == whole.round()).all():
                col = col.astype("Int64").astype("string")
            else:
                col = col.astype("string")
        else:
            col = col.astype("string")
        col = col.str.strip()
        out[name] = col.mask(col == "")
    return pd.DataFrame(out, index=frame.index)


def keep(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Columns of interest, in a fixed order, missing ones as empty text."""
    frame = frame.copy()
    for name in columns:
        if name not in frame.columns:
            frame[name] = pd.Series(pd.NA, index=frame.index, dtype="string")
    return as_text(frame[list(columns)])


# --- PySUS mirror -------------------------------------------------------------


def _pysus():
    import pysus  # imported late, it prints a banner and pulls heavy dependencies

    pysus.set_cache(C.CACHE_DIR / "pysus")
    return pysus


MIRROR_FTP_PREFIX = "public/data/ftp/"


def ftp_files(files: list) -> list:
    """Catalog entries copied from the DATASUS FTP origin.

    PySUS keeps them with ``str(path).startswith("public/data/ftp/")``. On
    Windows ``str()`` of a path uses backslashes, the test never matches and
    ``pysus.ftp.*`` answers empty without an error. ``as_posix()`` gives the
    same answer on every system (reported upstream, see ADR-0004).
    """
    return [f for f in files if PurePath(f.path).as_posix().startswith(MIRROR_FTP_PREFIX)]


def _mirror(dataset: str, **filters) -> pd.DataFrame:
    _pysus()
    from pysus.api.bag import FileBag
    from pysus.api.client import PySUS, _run_sync

    async def query():
        async with PySUS() as client:
            return await client.query(dataset=dataset, **filters)

    files = ftp_files(_run_sync(query()))
    return FileBag(files).download().to_dataframe() if files else pd.DataFrame()


def mirror_sinasc(uf: str, year: int) -> pd.DataFrame:
    return _mirror("sinasc", state=uf, year=year)


def mirror_cnes_lt(uf: str, year: int, month: int) -> pd.DataFrame:
    return _mirror("cnes", group="LT", state=uf, year=year, month=month)


# --- FTP origin ---------------------------------------------------------------

Connect = Callable[[float], ftplib.FTP]

# Most failures happen when the server opens the passive data connection, a
# few at login. They are short-lived: waiting longer does not help, trying
# again does. Short timeout, short and capped waits, many attempts.
RETRIES = 15
TIMEOUT = 15.0


def backoff(attempt: int) -> float:
    return min(1.0 * attempt, 5.0)


def ftp_connect(timeout: float) -> ftplib.FTP:
    ftp = ftplib.FTP(C.FTP_HOST, timeout=timeout)
    ftp.login()
    return ftp


def _close(ftp) -> None:
    try:
        ftp.quit()
    except Exception:  # noqa: BLE001 - the connection may already be gone
        ftp.close()


_listings: dict[str, list[str]] = {}


def list_remote(
    directory: str,
    *,
    connect: Connect = ftp_connect,
    retries: int = RETRIES,
    timeout: float = TIMEOUT,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    """File names of a remote directory, cached for the process."""
    if directory in _listings:
        return _listings[directory]
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            ftp = connect(timeout)
            try:
                names = [PurePosixPath(n).name for n in ftp.nlst(directory)]
            finally:
                _close(ftp)
            _listings[directory] = names
            return names
        except (OSError, EOFError, ftplib.error_temp, ftplib.error_reply) as exc:
            last = exc
            sleep(backoff(attempt))
    raise ConnectionError(f"listing {directory}: {retries} attempts failed ({last})")


def resolve(directory: str, filename: str, names: list[str]) -> str:
    """Remote path of a file whose extension case varies (.dbc or .DBC)."""
    wanted = filename.upper()
    for name in names:
        if name.upper() == wanted:
            return f"{directory}/{name}"
    raise FileNotFoundError(f"{filename} not found in {directory}")


def download(
    remote: str,
    dest: Path,
    *,
    connect: Connect = ftp_connect,
    retries: int = RETRIES,
    timeout: float = TIMEOUT,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Download with resume. The file only takes its final name once complete."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            ftp = connect(timeout)
            try:
                ftp.voidcmd("TYPE I")
                size = ftp.size(remote)
                offset = part.stat().st_size if part.exists() else 0
                if size is not None and offset > size:
                    part.unlink()
                    offset = 0
                if size is None or offset < size:
                    with part.open("ab") as fh:
                        ftp.retrbinary(f"RETR {remote}", fh.write, rest=offset or None)
            finally:
                _close(ftp)
            done = part.stat().st_size if part.exists() else 0
            if size is not None and done != size:
                raise OSError(f"incomplete transfer {done}/{size} bytes")
            part.replace(dest)
            return dest
        except ftplib.error_perm as exc:
            if str(exc).startswith("550"):
                raise FileNotFoundError(remote) from exc
            raise
        except (OSError, EOFError, ftplib.error_temp, ftplib.error_reply) as exc:
            last = exc
            sleep(backoff(attempt))
    raise ConnectionError(f"{remote}: {retries} attempts failed ({last})")


def read_dbc(path: Path) -> pd.DataFrame:
    """DATASUS .dbc (compressed DBF) to a data frame."""
    from dbfread import DBF
    from pyreaddbc import dbc2dbf

    dbf = path.with_suffix(".dbf")
    dbc2dbf(str(path), str(dbf))
    try:
        table = DBF(str(dbf), encoding="latin-1", char_decode_errors="replace")
        return pd.DataFrame(iter(table))
    finally:
        dbf.unlink(missing_ok=True)


def origin_sinasc(uf: str, year: int, prelim: bool, workdir: Path) -> pd.DataFrame:
    directory = C.FTP_SINASC_PRELIM if prelim else C.FTP_SINASC_FINAL
    remote = resolve(directory, f"DN{uf}{year}.dbc", list_remote(directory))
    return read_dbc(download(remote, workdir / PurePosixPath(remote).name))


def origin_cnes_lt(uf: str, year: int, month: int, workdir: Path) -> pd.DataFrame:
    name = f"LT{uf}{year % 100:02d}{month:02d}.dbc"
    remote = resolve(C.FTP_CNES_LT, name, list_remote(C.FTP_CNES_LT))
    return read_dbc(download(remote, workdir / PurePosixPath(remote).name))


# --- mirror, then origin --------------------------------------------------------


def fetch_sinasc(
    uf: str,
    year: int,
    *,
    prelim: bool = False,
    workdir: Path = C.CACHE_DIR / "origin",
    mirror: Callable[..., pd.DataFrame] = mirror_sinasc,
    origin: Callable[..., pd.DataFrame] = origin_sinasc,
) -> Fetched:
    if not prelim:  # the mirror holds final files only
        frame = mirror(uf, year)
        if not frame.empty:
            return Fetched(frame, "mirror")
    frame = origin(uf, year, prelim, workdir)
    if frame.empty:
        raise EmptySourceError(f"SINASC {uf} {year}: no rows in mirror nor origin")
    return Fetched(frame, "origin")


def fetch_cnes_lt(
    uf: str,
    year: int,
    month: int,
    *,
    workdir: Path = C.CACHE_DIR / "origin",
    mirror: Callable[..., pd.DataFrame] = mirror_cnes_lt,
    origin: Callable[..., pd.DataFrame] = origin_cnes_lt,
) -> Fetched:
    frame = mirror(uf, year, month)
    if not frame.empty:
        return Fetched(frame, "mirror")
    frame = origin(uf, year, month, workdir)
    if frame.empty:
        raise EmptySourceError(f"CNES LT {uf} {year}-{month:02d}: no rows in mirror nor origin")
    return Fetched(frame, "origin")
