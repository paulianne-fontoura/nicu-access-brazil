# ADR-0004 - PySUS mirror first, DATASUS origin when needed

Status - accepted, 1 October 2026.

## Context

DATASUS publishes SINASC and CNES as `.dbc` files on an FTP server. PySUS 2.11.4
reads by default a parquet copy of these files on S3. On 1 October 2026 the two
sources behaved as follows.

| | PySUS mirror | DATASUS FTP |
|---|---|---|
| SINASC final | up to 2022, empty answer for 2023 and 2024 (Sergipe, São Paulo, Amazonas tested) | 1996 to 2024 |
| SINASC preliminary | none | 2025 complete, 2026 up to 24 August |
| CNES beds | October 2005 to August 2026 | October 2005 to August 2026 |
| Reliability | every request answered in seconds | often one to four timeouts of 12 to 20 s before a transfer starts, an auxiliary archive still incomplete after three minutes and 34 MB |

Where both have a file, row counts match (SINASC Sergipe 2010, 34,016 rows, CNES
beds Sergipe December 2005, 314, December 2010, 394, August 2026, 379). Types do
not. The mirror stores bed counts as text and PySUS returns `CODMUNRES` as an
integer, the DBF holds integers. File names on the FTP mix `.dbc` and `.DBC`.

An empty answer from the mirror is not an error for PySUS. Written as is, it would
become a year without births.

## Decision

- Final years - mirror first, origin when the mirror is empty.
- Preliminary years - origin only, the mirror holds final files.
- Both empty - the file fails, nothing is written, the run goes on and reports it.
- Downloads from the origin resume where they stopped (FTP `REST`), with up to
  eight attempts and a growing wait. A file takes its final name only when its size
  matches the server.
- The raw layer stores every column as trimmed text. Typing happens in DuckDB.
- Each file written is recorded in `data/manifest.jsonl` (versioned) with its
  source, row count and a content hash that ignores row order.
- `nicu compare-sources` reads the same file from both sources and compares rows
  as a multiset. Its results are added below.

## Consequences

A rerun may read the same file from the other source. The content hash shows
whether the data changed. The gap in the mirror is reported to PySUS.

## Comparisons

Run with `nicu compare-sources` on 1 October 2026, every column as text, rows
compared as a multiset.

| File | Mirror rows | Origin rows | Columns in one source only | Rows without an identical counterpart |
|---|---:|---:|---|---:|
| SINASC Sergipe 2010 | 34,016 | 34,016 | none | 0 |
| CNES beds Sergipe December 2010 | 394 | 394 | none | 0 |

Once types are aligned, the two sources hold the same data on the files where
both exist.
