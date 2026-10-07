# ADR-0002 - Travel time on the IBGE bus and boat network

Status - accepted, 1 October 2026. Amended on 6 October 2026, measured pace.

## Context

Access is a matter of hours for a family without a car, and in the Amazon the trip
is often by boat. IBGE surveyed every regular intercity bus and boat line in 2016
(Ligações rodoviárias e hidroviárias). For each pair of linked municipalities it
gives the minimum travel time in minutes. The shortest path over this network
gives a travel time between any two connected municipalities.

Two gaps showed up in the prototype.

1. The survey leaves out lines inside an urban arrangement (city buses, metro).
   Without them, São José de Ribamar, next to São Luís, sat 168 minutes from the
   nearest NICU, Senador Canedo, next to Goiânia, 270 minutes, and Itaboraí, in the
   Rio de Janeiro area, 125 minutes. The location model picked such suburbs first.
2. 320 municipalities were left out of the survey, 191 of them because they have no
   public transport. In 2022, 2.7 % of births under 1,500 g lived in a municipality
   outside the network.

## Decision

- Edges are the IBGE pairs, minimum time kept when a pair appears twice.
- Every pair of municipalities in the same population arrangement (IBGE, 294
  arrangements) gets a 60-minute link. 30 and 90 minutes are tested.
- A municipality outside the network is linked to its three nearest surveyed
  municipalities by straight-line distance between seats, converted into time at
  the pace of the surveyed lines. This pace is the median over the IBGE pairs, 1.39
  minutes per straight-line kilometre (about 43 km/h).
- Straight-line distance alone is run as a check for the whole study. A
  recommendation must hold under both measures.

## Consequences

With arrangement links, births under 1,500 g living more than two hours from a
NICU in 2022 went from 3,085 to 2,562 in the prototype, and the suburbs left the
list of recommended sites. Travel times are those of public transport, slower than
a car and closer to what most families face. The network is frozen in 2016 and
applied to every year from 2006 to 2025, a limit the note states.

Three details settled with the full data.

- Towns across the border, which the survey lists, are dropped. A path between two
  Brazilian municipalities does not go through another country here.
- Two surveyed municipalities near Cuiabá are only linked to each other. Any group
  cut off from the rest is attached by the same rule as municipalities outside the
  survey.
- Brasília has no municipal seat in the IBGE file, its point is the federal
  capital.

Once completed the network holds the 5,571 municipalities in one piece, with
68,332 links, 378 of them estimated from straight-line distance.
