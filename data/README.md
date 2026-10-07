# Data

| Folder | Content | Versioned |
|---|---|---|
| `raw/` | One parquet file per state and year, as downloaded (`nicu ingest`) | no, 330 MB |
| `cache/` | Downloads in progress | no |
| `manifest.jsonl` | Source, row count and content hash of every raw file | yes |
| `processed/` | Counts of births at risk and NICU beds, IBGE references (`nicu build`) | yes |
| `results/` | One CSV per result table (`nicu analyze`) | yes |

`processed/` holds counts only, by year, municipality and facility. With it the
analysis runs from a clone, without the raw files.
