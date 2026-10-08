# ADR-0006 - The note is written by the pipeline, its claims are checked

Status - accepted, 8 October 2026.

## Context

The deliverable is a technical note in LaTeX, in the same format as the note of
the CépiDc project. A note written by hand drifts from the data. The 2025 births
are preliminary and will be revised, and any change of method reruns the
analysis. A number copied by hand would then be wrong without anyone noticing.

Numbers are not the only risk. Some sentences state a fact about the data
without quoting a number, such as "the North remains the region farthest from a
unit" or "most of the fall took place by 2010". New data could make them false
while every number stays correct.

## Decision

- `nicu report` reads `data/results` and `data/processed` only and writes every
  number cited by the note as a LaTeX macro (`report/numbers.tex`), the two
  tables (`report/table_*.tex`) and the two figures (`report/figures`). The note
  holds no number typed by hand.
- Each sentence that states a fact about the data has a check in
  `nicu.report`. If the data no longer supports one of them, the report stops and
  names the sentence.
- A test regenerates the numbers and tables from the versioned results and
  compares them with the committed files, and another checks that every macro
  written is cited by the note. Continuous integration compiles the note on every
  change.
- The map draws on the state boundaries of the IBGE malhas service, lowest
  resolution, stored as one row per point so that no geographic library is
  needed.
- The Portuguese summary is set without hyphenation, so the note compiles with
  any TeX installation that has `lmodern`, without the Portuguese patterns.

## Consequences

Rerunning `nicu analyze` then `nicu report` on revised data updates the note,
or stops on the sentence that needs rewriting. Figures are regenerated but not
compared byte for byte, since their pixels depend on the version of matplotlib.
