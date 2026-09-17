# NYC-Access — Session Contract

Every Claude Code session reads this file. It is the persistent contract.
Derived from `ROADMAP.md`, which is authoritative on scope, phases, and gates.

---

## What this project is

An open benchmark for curbside access-point inference from taxi trajectory
exhaust. NYC TLC stop events are mapped to OSM building footprints; a
difficulty/access model is validated against human-labeled ground truth with
spatial holdout. The artifact is a public dataset, eval harness, and technical
report.

## Banned framing

The following must never appear in code comments, README, docs, commit messages,
or any generated text:

- "world model"
- autonomous vehicles, robo-taxis, self-driving
- "chassis"
- any startup or product narrative
- Foundry, Gotham, or Palantir lineage

This project is spatial inference plus a data flywheel. Nothing more.
No claim may appear in any doc unless a released artifact supports it.

---

## Commit discipline

- Small commits. **Hard ceiling: 150 changed lines per commit.** Ask before
  exceeding. The repo contains a 15,868-line commit; that is the anti-pattern
  being corrected.
- One concern per commit. Do not bundle a fix with a refactor.
- When work would exceed the ceiling, stop at a natural boundary, commit, and
  continue. Do not batch.

## DECISIONS.md discipline

This is the most important section. `DECISIONS.md` is the evidentiary record
for technical interviews. Fabricated rationale is worse than no rationale.

- Record only what was actually observed.
- You may write: the parameter value used, the alternative values actually run,
  the measured outputs of those runs, and the error messages actually seen.
- You may NOT write a rationale for a choice that was not empirically tested.
  Never produce text of the form "we chose X because it balances A and B"
  unless you ran the alternatives and can paste the numbers.
- If a parameter was chosen without testing alternatives, record it as
  `UNTESTED — inherited` and flag it for review. Do not invent justification.

## Test discipline

- Every bug fixed gets a regression test written before the fix.
- Tests run in CI on push. Do not mark work complete with red CI.

## Metrics discipline

- `METRICS.md` holds measured values only. Never write a target, estimate,
  projection, or placeholder number into it.
- Every number is accompanied by the command that produced it and the date.

## Handoff protocol

At the end of every phase, regenerate `HANDOFF.md` with:
- What changed this phase
- Commands run and their outputs
- Measured numbers added to METRICS.md
- Open decisions needing a human call
- Deviations from ROADMAP.md and why
- What the next session needs to know

---

## Ask-before-assume triggers

Stop and ask when:

1. A threshold, epsilon, radius, or cutoff needs a value and no measurement
   exists to set it.
2. Data is missing or a table is empty and you would otherwise proceed with
   synthetic or assumed data.
3. A change would exceed the 150-line commit ceiling.
4. The task as written appears to conflict with `ROADMAP.md`.

---

## Current phase

**P0 — Repo triage.** See `ROADMAP.md` §2 for exit criteria.
