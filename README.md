# Where should Brazil open its next neonatal ICUs?

[![CI](https://github.com/paulianne-fontoura/nicu-access-brazil/actions/workflows/ci.yml/badge.svg)](https://github.com/paulianne-fontoura/nicu-access-brazil/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **Em português.** Onde o Brasil deveria abrir as próximas UTIs neonatais? O projeto
> mede, de 2006 a 2025, o acesso dos nascidos vivos de muito baixo peso (menos de
> 1.500 g) a leitos de UTI neonatal, verifica se os leitos abertos no período foram
> para onde estavam os nascimentos descobertos e indica, com um modelo de cobertura
> máxima, os municípios onde 5, 10 ou 20 novas unidades cobririam mais nascimentos.
> Dados abertos do DATASUS (SINASC, CNES) e do IBGE.

**Status - work in progress.** Session 1 of 5 (data ingestion). The design is in
[docs/design.md](docs/design.md), the decisions in [docs/adr](docs/adr).

A newborn under 1,500 g has the best chance of survival when born in a hospital
with a neonatal intensive care unit (NICU). Brazil added NICU beds over the last
twenty years, yet a share of these births still happens hours away from one.
Studies describe this inequality. This project asks the next question, the one
a planner faces. Where would the next units bring the most births within reach,
and does the answer hold from one year to the next?

## Questions

1. **How did access change from 2006 to 2025?** Share of very-low-birth-weight
   births born in a facility with a NICU, share living more than two hours from
   one, by region and state.
2. **Did the beds opened over the period go where uncovered births were?**
3. **Where would 5, 10 or 20 new units cover the most uncovered births?** A
   maximal covering location model, solved year by year, kept only where the
   answer is stable.

The project measures and ranks options under explicit assumptions. It does not
judge public policy.

## Data

| Source | Content | Years |
|---|---|---|
| SINASC (DATASUS) | Every live birth, with weight, municipality of residence, municipality and facility of birth | 2006-2024 final, 2025 preliminary |
| CNES, beds (DATASUS) | Beds per facility and type, monthly | December of each year (November in 2007) |
| IBGE, Ligações rodoviárias e hidroviárias 2016 | Minimum bus or boat travel time between 5,407 municipalities | 2016 |
| IBGE, Arranjos populacionais | Municipalities forming one urban area | 2015 |
| IBGE, Localidades | Coordinates of the 5,569 municipal seats | 2022 |

All sources are public. Births are de-identified microdata, only aggregates are
published here.

## Run it

```bash
uv sync                       # Python 3.12 and dependencies
uv run nicu ingest ibge       # transport network, arrangements, municipal seats
uv run nicu ingest cnes       # beds, one month per year and state
uv run nicu ingest sinasc     # births, one file per year and state
uv run nicu status            # what is still missing
uv run pytest -q
```

With `make` installed, `make setup`, `make ingest`, `make status` and `make test`
run the same commands.

Raw files come from the [PySUS](https://github.com/AlertaDengue/PySUS) mirror
when it has them, otherwise from the DATASUS FTP server, with resumed downloads.
Every file is recorded in `data/manifest.jsonl` with its source, row count and
content hash. The full ingestion writes 1,083 files, about 330 MB of parquet, and
takes several hours, most of them on the years that only the FTP server holds. It
can be stopped and started again, recorded files are skipped.

## Author

Paulianne Fontoura. This project extends published work on ICU bed planning
(Health Environments Research & Design Journal, 2026) and on obstetric decision
support, to the scale of a country.

## License

Code under the MIT license. Data from DATASUS and IBGE, public and open.
