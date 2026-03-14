import { createClient } from "@/lib/supabase/server";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const supabase = await createClient();
  const { searchParams } = request.nextUrl;

  const bboxParam = searchParams.get("bbox");
  if (!bboxParam) {
    return NextResponse.json(
      { error: "bbox required: west,south,east,north" },
      { status: 400 }
    );
  }

  const bbox = bboxParam.split(",").map(Number);
  if (bbox.length !== 4 || bbox.some(isNaN)) {
    return NextResponse.json(
      { error: "bbox must be 4 comma-separated numbers" },
      { status: 400 }
    );
  }

  const [west, south, east, north] = bbox;
  const limit = Math.min(Number(searchParams.get("limit") ?? 1000), 2000);

  const { data, error } = await supabase.rpc("get_entrances_in_bbox", {
    p_west: west,
    p_south: south,
    p_east: east,
    p_north: north,
    p_limit: limit,
  });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json(data);
}
