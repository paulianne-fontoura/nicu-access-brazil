# ADR-0003 - SUS NICU beds, codes harmonised across 2007-2008

Status - accepted, 1 October 2026.

## Context

CNES records beds per facility and type every month (group LT, `CODLEITO`). Three
facts change what counts as a NICU bed.

1. **Codes changed.** Until 2008 CNES used one code for neonatal intensive care
   (63). Codes by type, 80 (type I), 81 (type II) and 82 (type III), are already in
   use in 2006 and replace 63 completely during 2008. In São Paulo, the two sets
   coexist in different facilities (one or two facilities with both, in every month
   checked from June 2006 to March 2008) and code 63 is empty by June 2008.
2. **December 2007 loses SUS beds.** In São Paulo, SUS beds under code 63 go from
   705 in November 2007 to 39 in December, then 8 in March 2008, while the new
   codes hold 117 to 146 SUS beds. In Sergipe, from 34 in December 2006 to 2 in
   December 2007. They are back under the new codes by December 2008 (854 SUS beds
   on codes 81 and 82 in São Paulo).
3. **Type I is private.** Code 80 held 2,559 beds in December 2010, 107 of them SUS,
   and 1,784 in December 2022, 20 of them SUS.

The choice changes the conclusion. In the prototype, births under 1,500 g living
more than two hours from a NICU fell from 8.8 % to 6.7 % between 2010 and 2022 when
counting every bed, and from 10.7 % to 9.8 % when counting SUS beds only.

## Decision

- NICU beds are codes 63, 80, 81 and 82. Intermediate neonatal units (65, then 92
  and 93) are not NICUs and are left out.
- Main measure - SUS beds (`QT_SUS`). A facility offers SUS neonatal intensive
  care when it has at least one SUS bed under these codes.
- Check - every existing bed (`QT_EXIST`), SUS or not.
- When a facility reports old and new codes in the same month, the larger count is
  kept, so no bed is counted twice.
- Beds are read in December of each year, in November for 2007.

## Consequences

The bed series runs over twenty years with one definition. Most of the population
depends on SUS, so the main measure follows the beds a public planner can act on,
and the check shows what private beds add. The 2007 exception is documented in the
configuration (`BED_MONTH_EXCEPTIONS`) and tested.
