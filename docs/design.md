# Design

Status - accepted, 1 October 2026. Changes go through a new ADR.

## Question

Where should Brazil open its next neonatal intensive care units (NICUs) so that the
largest number of very-low-birth-weight births gain access within a reasonable travel
time, and does the answer hold from one year to the next?

A newborn under 1,500 g depends on intensive care in the first hours of life. Being
born in a hospital that has a NICU, or close to one, is the condition the rest of
the care builds on. Brazil added NICU beds over the period, but where they went
matters as much as how many there are. The project answers three questions, each
building on the previous one.

1. **How did access change from 2006 to 2025?** For births under 1,500 g, the share
   born in a facility with a NICU, the share whose municipality of residence is more
   than 90, 120 or 180 minutes from the nearest NICU, and the trip actually made
   between residence and birth, by region and state.
2. **Did the beds opened over the period go where uncovered births were?** Bed
   growth split between municipalities that already had a NICU and municipalities
   that opened their first one, and the share of uncovered births that these openings
   brought within reach.
3. **Where would 5, 10 or 20 new units cover the most uncovered births?** A maximal
   covering location model, solved for each of the last five years (2021 to 2025),
   with demand adjusted for the fall in births. A municipality is recommended when it
   is selected in most years and at more than one travel-time threshold.

The project measures and ranks options under explicit assumptions. It does not
judge public policy, and the note says so.

## Data

| Source | Use | Coverage |
|---|---|---|
| SINASC, live births (DATASUS) | Demand, weight, residence, facility and municipality of birth | 2006-2024 final, 2025 preliminary |
| CNES, beds (DATASUS, group LT) | NICU beds per facility, SUS and non-SUS | December of each year, November in 2007 |
| IBGE, Ligações rodoviárias e hidroviárias 2016 | Bus and boat travel times between municipalities | 5,407 municipalities |
| IBGE, Arranjos populacionais (2nd ed.) | Municipalities forming one urban area | 294 arrangements, 953 municipalities |
| IBGE, Localidades 2022 | Coordinates of municipal seats | 5,569 seats |

Twenty years is the longest series the sources allow. SINASC goes back to 1996,
but CNES starts in August 2005, so 2006 is the first year with beds.

## Decisions

| ADR | Decision |
|---|---|
| [0001](adr/0001-risk-definition.md) | A birth at risk is a birth under 1,500 g. Gestational age is a sensitivity check from 2011 only |
| [0002](adr/0002-travel-time.md) | Travel time on the IBGE bus and boat network, with links inside urban arrangements, straight-line distance as a check |
| [0003](adr/0003-bed-scope.md) | SUS NICU beds as the main measure, all NICU beds as a check, codes harmonised across the 2007-2008 change |
| [0004](adr/0004-ingestion.md) | PySUS mirror first, DATASUS FTP origin when the mirror is empty or the year preliminary, never an empty file |

## Architecture

```mermaid
flowchart LR
  subgraph sources[Public sources]
    M[PySUS mirror<br/>parquet on S3]
    F[DATASUS FTP<br/>.dbc files]
    I[IBGE<br/>xlsx and gpkg]
  end
  M --> R
  F --> R
  I --> R
  R[raw layer<br/>parquet + manifest] --> W[DuckDB<br/>staging and marts]
  W --> G[travel times<br/>networkx]
  G --> O[location model<br/>PuLP / CBC]
  W --> N[LaTeX note<br/>figures and numbers written by the pipeline]
  O --> N
```

Python 3.11 with uv, typer command line `nicu`. The raw layer keeps every column
as text, typing happens in DuckDB. CI runs lint and tests on synthetic data only,
no network.

## Sessions

1. Repository, design, ingestion with resume and source comparison.
2. Warehouse and access measure, question 1.
3. Bed growth, question 2.
4. Location model, question 3, with its robustness checks.
5. Note in LaTeX, README, map, final CI.

## Out of scope

Bed occupancy and staffing, transfers after birth (they would need hospital
admission records), private insurance coverage, costs, road routing. Each would
change the answer and is named as a limit in the note.

## Known limits

The 2016 transport network is applied to every year, ten years before and nine
after. A municipality is reduced to its seat, distances inside a municipality are
zero. Beds are read once a year. SINASC records where a child was born, not
where it was treated.
