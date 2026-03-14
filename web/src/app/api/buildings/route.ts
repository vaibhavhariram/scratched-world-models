import { createClient } from "@/lib/supabase/server";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const supabase = await createClient();
  const { searchParams } = request.nextUrl;

  const bboxParam = searchParams.get("bbox");
  if (!bboxParam) {
    return NextResponse.json({ error: "bbox required: west,south,east,north" }, { status: 400 });
  }
  const bbox = bboxParam.split(",").map(Number);
  if (bbox.length !== 4 || bbox.some(isNaN)) {
    return NextResponse.json({ error: "bbox must be 4 numbers" }, { status: 400 });
  }

  const { data, error } = await supabase.rpc("get_buildings_in_bbox", {
    p_west: bbox[0], p_south: bbox[1], p_east: bbox[2], p_north: bbox[3],
    p_min_score: Number(searchParams.get("min_score") ?? 0),
    p_max_score: Number(searchParams.get("max_score") ?? 1),
    p_limit: Math.min(Number(searchParams.get("limit") ?? 500), 1000),
  });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}
