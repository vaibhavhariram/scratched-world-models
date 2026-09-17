# NAVRA Ingress — Implementation Notes (SPEC-1)

## Overview

NAVRA Ingress is a map-first operator workflow at `/ingress` for resolving ambiguous building access points from noisy urban stop traces. It adds a case-driven decision layer on top of the existing NAVRA geospatial pipeline (buildings, stops, entrance clustering, difficulty scoring).

---

## Database Layer

**Migration:** `supabase/migrations/009_ingress_tables.sql`

### New Tables

| Table | Purpose |
|-------|---------|
| `logistics.ingress_cases` | Ambiguity cases derived from existing scores + entrance data. One per building (UNIQUE). |
| `logistics.operator_reviews` | Operator decisions — resolution type, selected candidate, notes. |
| `logistics.canonical_drop_points` | Confirmed access points with PostGIS POINT geometry. Supports deactivation for re-canonicalization. |

### Key Function: `refresh_ingress_cases()`

Re-runnable case generator. Can be called repeatedly while tuning thresholds — no one-time seed insert.

- Clears pending cases, preserves resolved/skipped
- Uses `ON CONFLICT (building_id) DO UPDATE` for idempotency
- Selects buildings where `difficulty > 0.4`, `entrance_count >= 2`, and no dominant entrance (`max_confidence < 0.7` OR `confidence_gap < 0.2`)

**Ambiguity score formula:**

```
ambiguity_score = 0.4 * difficulty + 0.35 * (1 - max_confidence) + 0.25 * (1 - confidence_gap)
```

**Cluster type classification:**

| Type | Rule |
|------|------|
| `multi_entrance` | ≥3 candidates, confidence gap < 0.15 |
| `low_confidence` | Max confidence < 0.5 |
| `facade_spread` | Stop variance > 0.7 |
| `high_distance` | Road distance > 0.7 |
| `mixed` | Everything else |

### RPC Functions

| Function | Returns | Notes |
|----------|---------|-------|
| `get_ingress_cases(p_limit)` | `{cases: [...], total: N}` | Pending first, ranked by ambiguity DESC |
| `get_ingress_case_detail(p_case_id)` | Single payload | Building + footprint + entrances + stops (GeoJSON) + score + reviews + canonical point |
| `submit_ingress_review(...)` | `{review_id, status}` | Transactional PL/pgSQL — inserts review, updates case, optionally creates canonical drop point |
| `get_ingress_stats()` | Summary counts | Total, pending, resolved, skipped, canonicalized, avg ambiguity |

---

## API Routes

All follow the existing pattern: `createClient()` → `supabase.rpc()` → `NextResponse.json()`.

| Method | Path | RPC | Notes |
|--------|------|-----|-------|
| GET | `/api/ingress/cases` | `get_ingress_cases` | Query: `limit` (default 50, max 100) |
| GET | `/api/ingress/cases/[id]` | `get_ingress_case_detail` | Path param: case ID |
| POST | `/api/ingress/cases/[id]/review` | `submit_ingress_review` | Body: `resolution_type`, `selected_candidate_id?`, `note?` |
| GET | `/api/ingress/stats` | `get_ingress_stats` | No params |

**Validation on POST:** `resolution_type` must be one of `canonicalized`, `wrong_building`, `diffuse_cluster`, `ambiguous_entrance`, `skip`. If `canonicalized`, `selected_candidate_id` is required.

---

## Data Hooks

| Hook | Type | Purpose |
|------|------|---------|
| `useIngressCases` | SWR | Fetches top 50 cases. Client-side filtering (no server pagination in v1). |
| `useIngressCase` | SWR | Fetches full case detail, keyed on case ID. |
| `useIngressStats` | SWR | Summary metrics with 30s auto-refresh. |
| `useIngressReview` | Mutation | POST review + invalidates cases/stats/detail caches. |

**Types exported:** `IngressCase`, `CaseDetail`, `EntranceCandidate`, `IngressStats`.

---

## UI Components

### IngressLayout (orchestrator)

- CSS Grid: `grid-cols-[320px_1fr_400px]`, full viewport
- MetricsStrip spanning top (h-12)
- Manages `selectedCaseId` and `selectedCandidateId`
- **Auto-selects `recommended_candidate_id`** when a case loads
- After review: auto-advances to next pending case

### MetricsStrip

Top bar showing: Total Cases, Pending, Resolved, Skipped, Canonicalized, Avg Ambiguity.

### CaseQueue + CaseQueueItem (left panel)

- Client-side filter tabs: All | Pending | Resolved
- Each item shows: building name, ambiguity score badge (color-coded), candidate count, cluster type tag, status dot
- Selected case highlighted with blue ring
- Loading skeleton state (8 placeholder cards)

### IngressMap (center panel)

- Reuses deck.gl + react-map-gl + Mapbox dark-v11 from existing `MapContainer`
- **Case-driven** — all data comes from selected case detail, no bbox fetching
- Layers:
  - Building footprint (GeoJsonLayer, blue fill)
  - Stop events (ScatterplotLayer, green=pickup / orange=dropoff)
  - Entrance candidates (ScatterplotLayer, confidence colors)
  - Selected candidate (ScatterplotLayer, blue with white ring)
- FlyTo animation on case selection (`FlyToInterpolator`, zoom 18, 1200ms)
- Click entrance candidate on map to select it
- Legend overlay, loading/empty states

### CaseDetailPanel (right panel)

Composed from sub-components, vertically scrollable:

1. **Building header** — name, address, area, OSM ID, cluster type badge, stop/candidate counts
2. **ScoreBreakdown** — prominent ambiguity score with gradient bar, max confidence and confidence gap, difficulty sub-component bars (stop variance, road distance, entrance count, dwell time)
3. **System Recommendation** — explains why the recommended candidate was chosen: confidence dominance, margin over next candidate, cluster size, spatial spread, facade side
4. **EntranceCandidateList** — selectable cards with RECOMMENDED badge, confidence %, side, cluster size, spread, avg dwell. Selected card gets blue ring.
5. **Canonical Drop Point** — shown if one exists (green badge)
6. **Review History** — past reviews with resolution type and notes
7. **ReviewActions** — Canonicalize (green, requires candidate), Wrong Building (red), Diffuse Cluster (orange), Ambiguous (yellow), Skip (gray). Optional note textarea. Error display.

---

## File Manifest

### New Files (19)

```
supabase/migrations/009_ingress_tables.sql

web/src/app/ingress/page.tsx
web/src/app/api/ingress/cases/route.ts
web/src/app/api/ingress/cases/[id]/route.ts
web/src/app/api/ingress/cases/[id]/review/route.ts
web/src/app/api/ingress/stats/route.ts

web/src/components/ingress/IngressLayout.tsx
web/src/components/ingress/MetricsStrip.tsx
web/src/components/ingress/CaseQueue.tsx
web/src/components/ingress/CaseQueueItem.tsx
web/src/components/ingress/IngressMap.tsx
web/src/components/ingress/CaseDetailPanel.tsx
web/src/components/ingress/ScoreBreakdown.tsx
web/src/components/ingress/EntranceCandidateList.tsx
web/src/components/ingress/ReviewActions.tsx

web/src/lib/hooks/useIngressCases.ts
web/src/lib/hooks/useIngressCase.ts
web/src/lib/hooks/useIngressStats.ts
web/src/lib/hooks/useIngressReview.ts
```

### Modified Files (1)

```
web/src/lib/utils/colors.ts              # Added ambiguityToRGBA
```

---

## Reuse Map

| Existing Code | Reused In |
|---|---|
| `MapContainer.tsx` — deck.gl + react-map-gl setup | IngressMap (same pattern, case-driven instead of viewport-driven) |
| `EvidencePanel.tsx` — section layout, score display | CaseDetailPanel (same dark panel styling) |
| `colors.ts` — `difficultyToRGBA`, `confidenceToRGBA`, `eventTypeColor` | Direct imports in IngressMap, ScoreBreakdown |
| `useEvidence.ts` — SWR hook pattern | useIngressCase, useIngressCases |
| `buildings/route.ts` — API route pattern | All 4 ingress API routes |
| `server.ts` — `createClient` | All API routes |
| `get_building()` RPC | Called inside `get_ingress_case_detail` |

---

## Scope Decisions (v1)

| Decision | Rationale |
|----------|-----------|
| No pagination | Top 50 cases, client-side filtering. Simpler. |
| `refresh_ingress_cases()` instead of seed INSERT | Re-runnable while tuning thresholds. |
| Simple ambiguity formula | `0.4*difficulty + 0.35*(1-max_conf) + 0.25*(1-conf_gap)`. Interpretable. |
| Auto-select recommended candidate | Reduces clicks, shows system opinion immediately. |
| System Recommendation section | Explains why — builds operator trust. |
| Cut keyboard shortcuts, URL sync | Stretch goals. Core workflow ships first. |
| Single payload per case detail | One RPC call returns everything needed. No waterfall. |
| Demo opens on `/ingress` | No time spent on old `/` route. |

---

## Activation Steps

1. Apply the migration:
   ```bash
   supabase db push
   ```
   Or run `009_ingress_tables.sql` manually against the database.

2. Populate cases:
   ```sql
   SELECT logistics.refresh_ingress_cases();
   ```

3. Start the dev server:
   ```bash
   cd web && npm run dev
   ```

4. Navigate to `http://localhost:3000/ingress`

---

## Build Status

- TypeScript: clean (`npx tsc --noEmit` passes)
- Next.js production build: passes
- `/ingress` renders as static page
- All API routes registered as dynamic server endpoints
