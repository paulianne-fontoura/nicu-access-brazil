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

## Result tables

| File | Content |
|---|---|
| `access.csv` | Access indicators by year, bed scope (SUS, all) and area (country, region, state) |
| `bed_growth.csv` | Beds added where a unit existed and in municipalities opening their first one |
| `reach_change.csv` | Births of the first year brought within reach or out of reach by the change of units |
| `decomposition.csv` | Change in the share beyond two hours, beds effect and births effect |
| `sensitivity.csv` | National series under other risk groups and other times inside urban arrangements |
| `site_coverage.csv` | Births covered by 5, 10 and 20 units, and by every candidate, by travel time and basis |
| `sites_by_year.csv` | Sites chosen, pooled years and each year alone |
| `sites.csv` | The sites of the pooled answer and how solid each one is |
| `municipalities.csv` | One row per municipality, travel time, SUS beds, births at risk, candidate, for the map |
