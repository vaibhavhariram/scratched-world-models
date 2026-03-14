import { createClient } from "@/lib/supabase/server";
import { NextRequest, NextResponse } from "next/server";

/**
 * GET /api/buildings/:id/evidence
 *
 * Returns full debug evidence for a building:
 * - building polygon + metadata
 * - all assigned stop events as GeoJSON
 * - entrance candidates
 * - score breakdown
 * - validation notes
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const buildingId = parseInt(id, 10);
  if (isNaN(buildingId)) {
    return NextResponse.json({ error: "Invalid building ID" }, { status: 400 });
  }

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("get_building_evidence", {
    p_building_id: buildingId,
  });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!data) return NextResponse.json({ error: "Not found" }, { status: 404 });
  return NextResponse.json(data);
}
