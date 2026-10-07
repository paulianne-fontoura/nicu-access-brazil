# ADR-0005 - Where to open units, a maximal covering location model

Status - accepted, 6 October 2026.

## Context

Question 3 asks where a given number of new units would bring the most births at
risk within reach. Ranking municipalities by their own uncovered births is not
enough. Two neighbours can both rank high and cover the same births, and a town
with few births of its own can be the best site because of the towns around it.

## Decision

- The model is the maximal covering location problem. Given the births at risk
  living beyond a travel time from any SUS NICU, it chooses the municipalities
  that bring the largest number of them within that time. It is solved exactly as
  an integer program (SciPy, HiGHS solver), not by a greedy rule.
- A candidate is a municipality without a SUS NICU where at least 1,000 births a
  year already take place. A NICU is attached to a maternity of some size, and
  the model should not propose a site with no obstetric activity. Between 197
  and 254 municipalities qualify each year from 2021 to 2025.
- It is solved for 5, 10 and 20 units, at 90, 120 and 180 minutes.
- The answer is computed on the last five years taken together. Births at risk
  are summed over these years and set against the latest NICU map. One year alone
  is too thin, a municipality has a handful of such births a year and the choice
  would follow the noise.
- Each of the five years is then solved on its own. For every site of the answer,
  the result table gives the number of years in which it is also chosen, whether
  it is still chosen at 90 and at 180 minutes, and whether it is still chosen
  under straight-line distances. A site that holds on all counts is a solid
  candidate, a site chosen on the pooled years only is a fragile one, and the
  note says which is which.
- Pooling the last five years lets the fall in births weigh on the result. A site
  whose uncovered births are shrinking counts for less.

## Consequences

The model says where coverage would increase the most under these assumptions. It
says nothing about the capacity of the new units, about staff, or about cost, and
a unit is assumed to serve every birth within the travel time. Births beyond the
reach of any candidate stay uncovered whatever the number of units, which bounds
what new units alone can do.
