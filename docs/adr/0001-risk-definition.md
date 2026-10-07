# ADR-0001 - A birth at risk is a birth of 500 to 1,499 g

Status - accepted, 1 October 2026. Amended on 6 October 2026, lower bound of 500 g.

## Context

The project counts the births that need a NICU. SINASC gives two candidates, the
birth weight (`PESO`, in grams) and the gestational age (`GESTACAO`, six classes,
and from 2011 `SEMAGESTAC`, exact weeks).

The birth declaration form changed in 2011. Gestational age used to be reported
directly as a class. It is now computed from the date of the last menstrual period
and recorded in weeks. The change shows in the data.

| Sergipe | 2010 | 2011 | 2012 | 2024 |
|---|---:|---:|---:|---:|
| Births | 34,016 | 34,925 | 34,108 | 27,545 |
| `SEMAGESTAC` filled | 0.6 % | 95.8 % | 98.0 % | 99.4 % |
| Under 37 weeks | 6.47 % | 10.69 % | 9.20 % | 11.44 % |
| Under 32 weeks | 1.12 % | 1.89 % | 1.65 % | 1.63 % |
| Under 1,500 g | 1.28 % | 1.38 % | 1.33 % | 1.44 % |

Preterm births jump by two thirds in one year, weight barely moves. Weight is
missing for 0.26 % of births in Sergipe in 2006, and for 0.15 % (2010) and 0.02 %
(2022) of births nationwide.

## Decision

A birth at risk is a live birth of 500 to 1,499 g, for every year from 2006 to 2025.
Births under 500 g are counted apart, and births with a missing weight are counted
and reported each year, never imputed.

Sensitivity check, from 2011 only - births under 32 weeks whose weight is 1,500 g
or more.

## Why 500 g

The prototype counted every birth under 1,500 g and showed a rise, from 1.28 % of
births in 2010 to 1.50 % in 2022. The full series shows where it comes from.

| | 2006 | 2015 | 2022 | 2025 (preliminary) |
|---|---:|---:|---:|---:|
| Births | 2,944,928 | 3,017,668 | 2,561,922 | 2,456,688 |
| Under 500 g | 2,625 | 3,863 | 3,982 | 3,942 |
| 500 to 1,499 g | 34,171 | 36,739 | 34,530 | 31,151 |
| Weight missing | 10,394 | 1,209 | 397 | 204 |

Births under 500 g rose by half while births fell by a sixth. These births are at
the limit of viability and their registration as live births varies between
places and over time. Counted with the others, they would read as a rise in
demand. Births of 500 to 1,499 g follow the number of births, as expected.

## Consequences

The series is comparable over twenty years. Weight leaves out some preterm births
of normal weight who also need intensive care, so the demand is a floor.

Figures from the full ingestion (1,083 files), 6 October 2026.
