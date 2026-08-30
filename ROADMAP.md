# NYC-Access — Roadmap

Commit this at git-init. Update at every phase gate. Pairs with `DECISIONS.md`
(parameter history) and `METRICS.md` (measured numbers only).

---

## 0. Scope lock

**In (v1.0 artifact):**
- Partitioned PostGIS ingest of NYC TLC stop events → OSM building footprints
- Human-labeled access-point ground truth, spatially held out
- Pre-registered proxy validation (taxi curb stop vs labeled access point)
- Calibrated difficulty/access model vs hand-weighted baseline
- Public dataset release + eval harness + technical report

**In (v1.1, cheap once v1.0 exists):**
- Active-learning loop
- Chicago transfer

**Out (permanently, from repo and resume):**
- "World model" framing
- AV / robo-taxi / "chassis" framing
- Startup narrative, Foundry/Gotham lineage
- Anything the released data cannot support

Rationale: benchmark is the artifact. Vision is an interview answer, not a
README claim. Overclaim discredits the measured parts.

---

## 1. The three-rung generalization story

Spine of the whole project. Every phase serves this.

| Rung | Split | Question | Expected |
|---|---|---|---|
| 1 | Random building split | Can it fit? | High |
| 2 | Spatial block split (hold out whole NTAs) | Or did it memorize neighborhoods? | Lower |
| 3 | Cross-city (Manhattan → Chicago) | Or did it memorize a street grid? | Lower still |

Rung-1 minus rung-2 gap is a result, not a bug. Report all three.
Random-split-only numbers are inflated by spatial autocorrelation and an
interviewer will say so. Pre-empt it.

---

## 2. Phases

Each phase has an exit criterion. No phase starts before prior exit met.
Phases are not time-boxed. Order is load-bearing.

### P0 — Repo triage
1. Commit 21 untracked ingress files. Split by concern, not one blob.
2. Push all branches to remote.
3. Verify DB state: row counts per table, distinct `pipeline_run_id`, max
   `created_at`, whether any run touched real TLC data.
4. Fix multi-run read bug:
   - `pipeline_runs` table: `id`, `started_at`, `finished_at`, `status`, `is_current`
   - Read RPCs → `DISTINCT ON (building_id) ... ORDER BY building_id, run_started_at DESC`
     or join to `is_current`
   - Regression test: insert two runs, assert single deterministic row per building
5. Kill dwell-time factor. Replacement candidates (pick by measurement, not taste):
   stop-event count, hour-of-day entropy, pickup/dropoff ratio, cluster spatial
   dispersion, distance from cluster centroid to footprint centroid, nearest-edge
   road class.
6. Seed `DECISIONS.md`, `METRICS.md`, CI running tests on push.

**Exit:** clean tree, remote current, tests green in CI, one committed doc stating
what is actually in the database.

### P1 — Labeling protocol + 50-building pilot
Protocol drafted (§3) before any label written. Pilot 50 buildings.

Measures from pilot: seconds/building, ambiguity rate, fraction with no usable
imagery, intra-session drift.

**Exit:** per-building cost known, protocol revised once against real friction,
label schema frozen.

### P2 — Early proxy check (cheap kill gate)
Run existing baseline on the 50 pilot buildings. Compare inferred point to
labeled point.

Do not wait for 1,000 labels to find out the proxy fails. 50 is enough for a
directional read at ~20 percentage points resolution.

**Exit:** GO / REFRAME / KILL called and written to `DECISIONS.md` with the
number that drove it.

### P3 — Scaled ingest
Multi-year, all-borough. Partitioned by (year, borough). Incremental.
Instrumented: rows/sec, index build wall time, storage per year, % stops
assigned, assignment-distance distribution.

**Exit:** full-corpus run reproducible from clean DB by one command; numbers in
`METRICS.md`.

### P4 — Full ground truth
1,000+ buildings per §3 sampling. Spatial block split assigned *before*
labeling, so labeler does not know which are test.

**Exit:** labels released, test split sealed, intra-rater κ reported.

### P5 — Formal proxy validation
Pre-registered thresholds (§4). Overall and by building class. Building-class
breakdown is likely the interesting part: proxy probably holds for residential
towers and fails for warehouses/big-box.

**Exit:** validation result published, framing locked (delivery access vs
curbside access), README claim rewritten to match.

### P6 — Learned model + calibration
Baseline = hand-weighted (minus dwell). Report lift over it, not absolute
accuracy alone. Metrics: top-1 within 10m / 25m, median displacement, ECE
(15-bin), Brier. All three rungs where applicable.

**Exit:** model beats baseline on rung-2 split, or documented that it doesn't.

### P7 — Active learning
Operator queue emits labels. Retrain. Curve: labels vs accuracy, acquisition
strategy vs random. ≥5 seeds, CIs. Without seeds this claim is noise.

**Exit:** labels-to-90% ratio with CI, or documented null.

### P8 — Chicago transfer
Same pipeline, city as parameter. Both directions. Report Δpp.

**Exit:** transfer number, both directions, with the spatial-split number beside
it for context.

### P9 — Release
- Dataset: HuggingFace + Zenodo DOI, CC-BY
- Eval harness: submission format, scoring script, held-out labels server-side
  or hashed
- `make reproduce` regenerates every number in the README
- Technical report: 6–10 pages, arXiv or repo PDF. Publish the negative result
  if negative.
- Distribution: OSM community forum, Overture Maps, r/gis, geospatial-ML
  channels, direct email to 3 researchers in last-mile logistics

**Exit:** a stranger reproduces a number without contacting you.

---

## 3. Labeling protocol (draft — revise after P1 pilot)

### Sampling frame
Buildings with ≥ N stop events (N set by measurement, recorded in `DECISIONS.md`).
Stratify by:
- borough
- building class (OSM tag / PLUTO land use)
- stop-density quartile

Plus a hard-negative stratum: high stop count, no plausible curb access
(plaza setback, no frontage, interior lot). These are where the model breaks and
where an honest benchmark earns its credibility.

### Split assignment
Spatial blocks (NTA or census tract), assigned before labeling begins.
~70/15/15. Whole blocks move together. No random building split for the
headline number.

### Unit of label
Point on or adjacent to footprint perimeter + category.

Schema:

| field | type | note |
|---|---|---|
| `building_id` | fk | |
| `labeler_id` | text | future-proofing for a second rater |
| `session_id` | uuid | one labeling sitting |
| `labeled_at` | timestamptz | |
| `access_point` | geometry(Point,4326) | |
| `access_type` | enum | `main_entrance`, `service_entrance`, `loading_dock`, `driveway`, `plaza_setback`, `ambiguous`, `no_access_visible` |
| `confidence` | int 1–3 | |
| `imagery_date` | date | buildings change; needed to explain misses |
| `seconds_spent` | int | fatigue/drift analysis |
| `is_calibration` | bool | recurring 25-building set |
| `notes` | text | |

Secondary candidate point recorded when `ambiguous`.

### Rules
- Ambiguous when two candidates and no principled pick. Do not force a choice.
  Ambiguity rate is a reported metric, not a failure.
- Never view model output while labeling. Not for any building, ever.
- Test-split labels never enter a dev loop. Score against them at most at
  declared checkpoints, logged.
- Max 90 min per session. Log start/end.

### Intra-rater reliability (single labeler, sittings weeks apart)
- 25-building calibration set re-labeled at the start of every session
- 10% blind re-label after ≥14 days
- Report Cohen's κ on `access_type` and median displacement in meters on point
- Drift beyond a pre-set bound → re-label the affected session's batch

### Optional accelerator (evaluate, don't assume)
VLM pre-proposes candidate access points; human adjudicates. Cuts per-building
time substantially.

Hard constraints if used:
- Test split stays 100% human-only, labeled without VLM exposure
- A ≥200-building human-only gold slice labeled *before* any VLM assistance
- Report human–VLM agreement against gold slice as its own result
- Disclose in README and dataset card

Done this way it is a methodological contribution and a fifth resume bullet.
Done sloppily it destroys the credibility of the entire benchmark. If unsure,
label by hand.

---

## 4. Pre-registered gates

Write thresholds to `DECISIONS.md` **before** running the check. Numbers below
are placeholders to be set at P1, not defaults.

- **Proxy holds (delivery framing):** taxi-inferred point within 25 m of labeled
  delivery access for ≥ __% of buildings
- **Proxy fails → reframe (curbside framing):** ≥ __% match against labeled
  curbside access
- **Kill:** both below threshold, no building-class stratum salvageable

Kill is a real outcome. A published, reproducible negative result on a real
dataset with a released ground-truth set is a stronger artifact than a
positive result nobody can check.

---

## 5. Metrics registry

`METRICS.md`. Measured values only. No aspirational entries.

**Ingest:** rows/sec, index build wall time, partitions, GB/year, % stops
assigned, assignment-distance p50/p90.

**Ground truth:** N labeled, ambiguity rate, no-imagery rate, κ (type),
median displacement (point), seconds/building.

**Model:** top-1 @10m, top-1 @25m, median displacement, ECE (15-bin), Brier —
each on random split, spatial split, cross-city.

**Active learning:** labels-to-90% vs random, ≥5 seeds, CI.

**Release:** downloads, leaderboard submissions, external forks.

---

## 6. Working rules

- Small commits. Never 1000+ lines. Existing 15,868-line commit is the
  anti-pattern being corrected.
- `DECISIONS.md` from commit one. Every parameter: value, alternatives tried,
  what happened at each. This is the interview answer that currently doesn't exist.
- Tests from commit one. Regression test for every bug fixed.
- Parallel agents allowed for: test generation, ingest parallelism, boilerplate,
  Chicago city-parameterization. Not for: labeling, threshold selection, any
  decision that belongs in `DECISIONS.md`.
- Ask before assuming.
