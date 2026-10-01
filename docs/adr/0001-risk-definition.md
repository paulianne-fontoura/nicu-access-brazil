# ADR-0001 - A birth at risk is a birth under 1,500 g

Status - accepted, 1 October 2026.

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

A birth at risk is a live birth under 1,500 g (very low birth weight), for every
year from 2006 to 2025. Births with a missing weight are counted and reported each
year, never imputed.

Sensitivity check, from 2011 only - under 1,500 g or under 32 weeks.

## Consequences

The series is comparable over twenty years. Weight leaves out some preterm births
of normal weight who also need intensive care, so the demand is a floor. The
national share under 1,500 g rose from 1.28 % (36,609 births) in 2010 to 1.50 %
(38,512) in 2022 in the prototype. Session 2 checks whether this is a change in
births or in registration (births under 500 g, deaths soon after birth).

Measured on 1 October 2026 with the prototype, figures recomputed by the pipeline
in session 2.
