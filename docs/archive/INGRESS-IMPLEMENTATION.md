# NAVRA Ingress — Implementation Plan

## Context

NAVRA already has a functioning geospatial pipeline: OSM building footprints, NYC TLC taxi stop events, DBSCAN entrance clustering, and difficulty scoring — all stored in Supabase/PostGIS with a Next.js + deck.gl map frontend. The existing `/` page is a viewport-driven explorer with an evidence panel.

**NAVRA Ingress** adds a new `/ingress` route: a case-driven operator workflow for resolving ambiguous building access points. Instead of exploring the map freely, operators work through a ranked queue of buildings where the system can't determine a clear access point, inspect evidence, and confirm/reject canonical drop points.

This turns the existing analytics pipeline into a **decision system**.

---

## New Files to Create

```
supabase/migrations/
  009_ingress_tables.sql                    # 3 tables + seed query + 4 RPC functions

web/src/app/ingress/
  page.tsx                                  # Route at /ingress

web/src/components/ingress/
  IngressLayout.tsx                         # 3-panel grid shell + state orchestration
  CaseQueue.tsx                             # Left panel: ranked scrollable list
  CaseQueueItem.tsx                         # Individual case card
  IngressMap.tsx                            # Center: deck.gl map for selected case
  CaseDetailPanel.tsx                       # Right panel: evidence + actions
  ScoreBreakdown.tsx                        # Visual bars for score components
  EntranceCandidateList.tsx                 # Selectable candidate cards
  ReviewActions.tsx                         # Action buttons + note field
  MetricsStrip.tsx                          # Top bar summary counts

web/src/lib/hooks/
  useIngressCases.ts                        # SWR: case queue
  useIngressCase.ts                         # SWR: single case detail
  useIngressStats.ts                        # SWR: summary metrics
  useIngressReview.ts                       # POST mutation for review submission

web/src/app/api/ingress/
  cases/route.ts                            # GET /api/ingress/cases
  cases/[id]/route.ts                       # GET /api/ingress/cases/:id
  cases/[id]/review/route.ts                # POST /api/ingress/cases/:id/review
  stats/route.ts                            # GET /api/ingress/stats
```

**Existing file to modify:** `web/src/lib/utils/colors.ts` — add `ambiguityToRGBA` helper.

**Total:** 19 new files + 1 modification.

---

## Database Migration: `009_ingress_tables.sql`

### New Tables

**`logistics.ingress_cases`** — Ambiguity cases derived from existing scores + entrance data
- `id` BIGINT PK, `building_id` BIGINT UNIQUE FK → buildings
- `ambiguity_score` DOUBLE (0-1), `review_status` TEXT (pending|resolved|skipped)
- `cluster_type` TEXT (multi_entrance|low_confidence|facade_spread|high_distance|mixed)
- `candidate_count` INT, `evidence_summary` JSONB
- `recommended_candidate_id` BIGINT FK → entrance_candidates
- Indexes: status, ambiguity_score DESC, building_id

**`logistics.operator_reviews`** — Operator decisions
- `id` BIGINT PK, `case_id` BIGINT FK → ingress_cases
- `selected_candidate_id` BIGINT FK nullable → entrance_candidates
- `resolution_type` TEXT (canonicalized|wrong_building|diffuse_cluster|ambiguous_entrance|skip)
- `note` TEXT, `created_at` TIMESTAMPTZ

**`logistics.canonical_drop_points`** — Confirmed access points
- `id` BIGINT PK, `building_id` BIGINT FK → buildings
- `location` GEOMETRY(POINT, 4326), `source_review_id` BIGINT FK → operator_reviews
- `confidence` DOUBLE (0-1), `active` BOOLEAN
- GIST index on location, partial index on active=true

### Seed Query

Populate `ingress_cases` from existing data by selecting buildings where:
- `difficulty > 0.5` AND `entrance_count >= 2`
- No dominant entrance: `max_confidence < 0.7` OR `confidence_gap < 0.2` between top two

Ambiguity score formula:
```
0.30 * difficulty
+ 0.25 * normalized_entrance_count
+ 0.25 * (1 - max_confidence)
+ 0.20 * (1 - confidence_gap)
```

Cluster type classification:
- `multi_entrance`: ≥3 candidates, gap < 0.15
- `low_confidence`: max confidence < 0.5
- `facade_spread`: stop_variance > 0.7
- `high_distance`: road_distance > 0.7
- `mixed`: everything else

### RPC Functions

1. **`get_ingress_cases(p_limit, p_offset, p_status_filter)`** → `{cases: [...], total: N}`
   - Joins ingress_cases + buildings for name/address/centroid
   - Orders: pending first, then by ambiguity_score DESC

2. **`get_ingress_case_detail(p_case_id)`** → full case object
   - Reuses existing `get_building()` for building+entrances+score
   - Adds stops (GeoJSON FeatureCollection), stop_count, reviews, canonical_point

3. **`submit_ingress_review(p_case_id, p_resolution_type, p_selected_candidate_id, p_note)`** → `{review_id, status}`
   - PL/pgSQL transactional function
   - Inserts review, updates case status
   - If canonicalized: copies entrance candidate location → canonical_drop_points, deactivates previous

4. **`get_ingress_stats()`** → `{total, pending, resolved, skipped, canonicalized, by_cluster_type, avg_ambiguity}`

---

## API Routes

All follow the existing pattern in `web/src/app/api/buildings/route.ts`: `createClient()` → `supabase.rpc()` → `NextResponse.json()`.

| Method | Path | RPC | Notes |
|--------|------|-----|-------|
| GET | `/api/ingress/cases` | `get_ingress_cases` | Query: limit, offset, status |
| GET | `/api/ingress/cases/[id]` | `get_ingress_case_detail` | Path param: case ID |
| POST | `/api/ingress/cases/[id]/review` | `submit_ingress_review` | Body: resolution_type, selected_candidate_id?, note? |
| GET | `/api/ingress/stats` | `get_ingress_stats` | No params |

---

## UI Component Architecture

### IngressLayout (orchestrator)
- CSS Grid: `grid-cols-[320px_1fr_400px]` full viewport
- MetricsStrip spanning top (h-12)
- Manages: `selectedCaseId`, `statusFilter`
- Keyboard: `j`/`k` navigate queue, `Escape` deselect

### Left Panel: CaseQueue + CaseQueueItem
- Status filter tabs: All | Pending | Resolved
- Scrollable list, selected case highlighted with `ring-2 ring-blue-500`
- Each item shows: building name, ambiguity score badge (colored), candidate count, cluster type, status dot

### Center Panel: IngressMap
- Reuse deck.gl + react-map-gl + Mapbox dark-v11 pattern from `web/src/components/map/MapContainer.tsx`
- Layers: building footprint (GeoJsonLayer), entrance candidates (ScatterplotLayer, confidence colors), stop events (ScatterplotLayer, event type colors)
- FlyTo on case selection using `FlyToInterpolator`
- **Case-driven** — all data comes from selected case detail, no bbox fetching
- Candidate click selects for canonicalization

### Right Panel: CaseDetailPanel
- Building header (name, address, area)
- ScoreBreakdown: horizontal bars for each difficulty sub-component + ambiguity score
- EntranceCandidateList: selectable cards with confidence, cluster_size, side, dwell
- ReviewActions: Canonicalize (green), Wrong Building (red), Diffuse Cluster (orange), Ambiguous Entrance (yellow), Skip (gray)
- Optional note textarea
- After submit: auto-advance to next pending case, optimistic UI update

### MetricsStrip
- Horizontal bar: Total | Pending | Resolved | Skipped | Canonicalized
- Clickable filters
- Auto-refresh via `useIngressStats` with `refreshInterval: 30000`

---

## Reuse Map

| Existing Code | Reuse In |
|---|---|
| `web/src/components/map/MapContainer.tsx` | Pattern for IngressMap (deck.gl + react-map-gl setup) |
| `web/src/components/panels/EvidencePanel.tsx` | Pattern for CaseDetailPanel (section layout, score display) |
| `web/src/lib/utils/colors.ts` — `difficultyToRGBA`, `confidenceToRGBA` | Direct import in IngressMap and ScoreBreakdown |
| `web/src/lib/utils/geo.ts` — `viewportToBBox` | Not needed (case-driven, not viewport-driven) |
| `web/src/lib/hooks/useEvidence.ts` | Pattern for useIngressCase SWR hook |
| `web/src/app/api/buildings/route.ts` | Pattern for all API routes |
| `web/src/lib/supabase/server.ts` — `createClient` | Direct import in all API routes |
| `get_building()` RPC | Called inside `get_ingress_case_detail` for building+entrances+score |

---

## Implementation Phases

### Phase 1: Database (1-2 hours)
1. Write `009_ingress_tables.sql` — tables, indexes, seed INSERT, 4 RPC functions
2. Apply migration via Supabase CLI
3. Verify seed data populated and RPCs return expected results

### Phase 2: API Layer (1 hour)
1. Create 4 API route files following existing pattern
2. GET cases, GET case detail, POST review, GET stats
3. Test with curl

### Phase 3: Data Hooks (30 min)
1. `useIngressCases` — SWR with status filter + pagination
2. `useIngressCase` — SWR keyed on case ID
3. `useIngressStats` — SWR with refresh interval
4. `useIngressReview` — POST + SWR mutate to invalidate caches
5. Add `ambiguityToRGBA` to colors.ts

### Phase 4: Layout + Queue (2 hours)
1. `/ingress/page.tsx` — full-screen IngressLayout
2. `IngressLayout` — 3-column grid, state management
3. `MetricsStrip` — top bar with stats
4. `CaseQueue` + `CaseQueueItem` — left panel

### Phase 5: Map + Detail Panel (3 hours)
1. `IngressMap` — deck.gl layers, FlyTo, candidate click
2. `CaseDetailPanel` — composed from sub-components
3. `ScoreBreakdown` — horizontal bar charts
4. `EntranceCandidateList` — selectable candidate cards
5. `ReviewActions` — action buttons + note + submit

### Phase 6: Polish (1-2 hours)
1. Keyboard shortcuts (j/k/Enter/Escape)
2. Auto-advance after review
3. Optimistic UI on submit
4. Loading skeletons and empty states
5. URL state sync (?case=123)

---

## Demo Script (3 minutes)

**[0:00–0:20] The Problem** — Show existing map at `/`, click high-difficulty buildings, narrate that the system detects ambiguity but can't resolve it alone.

**[0:20–0:45] The Queue** — Navigate to `/ingress`. Show metrics strip, scroll ranked queue, point out ambiguity scores and cluster type badges.

**[0:45–1:30] Inspect a Case** — Click a high-ambiguity case. Map flies to building. Show footprint, entrance dots, stop scatter. Right panel: score breakdown bars, entrance candidates with confidence percentages.

**[1:30–2:15] Make a Decision** — Click through candidates on map and in list. Select the best one. Click "Canonicalize", add a note, submit. Case turns green in queue, auto-advances. Metrics update.

**[2:15–2:45] Quick Triage** — Resolve 2-3 more cases rapidly. One "Wrong Building", one "Skip". Show queue shrinking, metrics updating.

**[2:45–3:00] Closing** — Narrate: "Every resolution becomes canonical truth for downstream routing. The queue is ranked by ambiguity so operators fix the hardest cases first."

---

## Verification

1. Run migration, confirm `SELECT COUNT(*) FROM logistics.ingress_cases` returns cases
2. `curl /api/ingress/cases` returns ranked list
3. `curl /api/ingress/cases/1` returns full case with building, entrances, stops
4. Navigate to `/ingress` in browser — 3-panel layout loads
5. Click a case — map flies to building, detail panel populates
6. Submit a review — case status updates, canonical point created
7. Metrics strip reflects the change
8. Full end-to-end workflow completes without errors

---

## Scope Adjustments (v1)

1. **No pagination.** Fetch top ~50 cases, filter client-side.
2. **No one-time seed INSERT.** Migration creates tables/indexes/RPCs + a `refresh_ingress_cases()` helper function that can be re-run to regenerate cases while tuning thresholds.
3. **Simplified ambiguity scoring:**
   ```
   ambiguity_score = 0.4 * difficulty + 0.35 * (1 - max_confidence) + 0.25 * (1 - confidence_gap)
   ```
   Simple cluster type rules. No over-engineering.
4. **Auto-select recommended candidate** when a case is opened — highlighted in both map and candidate list.
5. **"System Recommendation" section** in detail panel explaining why the recommended candidate was chosen.
6. **Cut before core workflow:** keyboard shortcuts, URL sync, sophisticated optimistic UI are stretch goals.
7. **Single compelling payload** per case detail request. Cleanest possible 3-minute demo.
8. **Demo opens directly on `/ingress`** — no time spent on old `/` route.
