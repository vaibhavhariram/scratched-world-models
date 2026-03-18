"""Data quality checks for assigned stops before clustering."""

from dataclasses import dataclass
from src.common.db import get_connection, get_cursor


@dataclass
class SanityFlag:
    """A data quality issue detected during sanity checks."""
    building_id: int
    flag_type: str  # "too_few_stops", "zero_coords", "duplicates", "tiny_extent", "huge_extent"
    detail: str


def check_building_sanity(building_id: int) -> list[SanityFlag]:
    """Run all sanity checks on one building's assigned stops."""
    flags = []

    with get_connection() as conn:
        with get_cursor(conn) as cur:
            # Check for zero coordinates (0, 0)
            zero_flag = _check_zero_coordinates(building_id, cur)
            if zero_flag:
                flags.append(zero_flag)

            # Check for duplicate stops
            dup_flag = _check_duplicate_stops(building_id, cur)
            if dup_flag:
                flags.append(dup_flag)

            # Check for suspicious spatial extent
            extent_flag = _check_spatial_extent(building_id, cur)
            if extent_flag:
                flags.append(extent_flag)

    return flags


def _check_zero_coordinates(building_id: int, cur) -> SanityFlag | None:
    """Flag stops at (0,0) or with null coordinates."""
    cur.execute("""
        SELECT COUNT(*)
        FROM logistics.stop_events s
        JOIN logistics.building_stop_events bse ON bse.stop_event_id = s.id
        WHERE bse.building_id = %s
          AND (s.location IS NULL
               OR ST_X(s.location) = 0 AND ST_Y(s.location) = 0)
    """, (building_id,))

    count = cur.fetchone()[0]
    if count > 0:
        return SanityFlag(
            building_id=building_id,
            flag_type="zero_coords",
            detail=f"{count} stops at (0,0) or null coordinates"
        )
    return None


def _check_duplicate_stops(building_id: int, cur) -> SanityFlag | None:
    """Flag duplicate (same location + same timestamp) stops."""
    cur.execute("""
        SELECT COUNT(*) as dup_count
        FROM logistics.stop_events s
        JOIN logistics.building_stop_events bse ON bse.stop_event_id = s.id
        WHERE bse.building_id = %s
        GROUP BY ST_AsText(s.location), s.event_timestamp
        HAVING COUNT(*) > 1
    """, (building_id,))

    rows = cur.fetchall()
    if rows:
        total_dups = sum(row[0] for row in rows)
        return SanityFlag(
            building_id=building_id,
            flag_type="duplicates",
            detail=f"{len(rows)} location-timestamp pairs have {total_dups} duplicate stops"
        )
    return None


def _check_spatial_extent(building_id: int, cur) -> SanityFlag | None:
    """
    Flag if spatial extent of stops is too small (<1m) or too large (>200m).
    Too small = all stops at same point (likely not a real cluster).
    Too large = stops spread too wide (likely misassigned or building too big).
    """
    cur.execute("""
        SELECT
            GREATEST(
                ST_XMax(ST_Extent(ST_Transform(s.location, 32618))) -
                ST_XMin(ST_Extent(ST_Transform(s.location, 32618))),
                ST_YMax(ST_Extent(ST_Transform(s.location, 32618))) -
                ST_YMin(ST_Extent(ST_Transform(s.location, 32618)))
            ) as max_extent_m
        FROM logistics.stop_events s
        JOIN logistics.building_stop_events bse ON bse.stop_event_id = s.id
        WHERE bse.building_id = %s
    """, (building_id,))

    result = cur.fetchone()
    if not result or result[0] is None:
        return None

    max_extent = result[0]

    if max_extent < 1:
        return SanityFlag(
            building_id=building_id,
            flag_type="tiny_extent",
            detail=f"max spatial extent {max_extent:.2f}m (all stops at same point?)"
        )

    if max_extent > 200:
        return SanityFlag(
            building_id=building_id,
            flag_type="huge_extent",
            detail=f"max spatial extent {max_extent:.2f}m (likely misassigned or very large building)"
        )

    return None


def run_sanity_check(building_ids: list[int] | None = None) -> None:
    """Run sanity checks on buildings and print summary."""
    if building_ids is None:
        # Check all buildings with assigned stops
        with get_connection() as conn:
            with get_cursor(conn) as cur:
                cur.execute("""
                    SELECT DISTINCT bse.building_id
                    FROM logistics.building_stop_events bse
                    ORDER BY bse.building_id
                """)
                building_ids = [row[0] for row in cur.fetchall()]

    print(f"\nSanity Check: {len(building_ids)} buildings")
    print("=" * 70)

    flag_count = 0
    flag_by_type = {}

    for bid in building_ids:
        flags = check_building_sanity(bid)
        for flag in flags:
            flag_count += 1
            if flag.flag_type not in flag_by_type:
                flag_by_type[flag.flag_type] = 0
            flag_by_type[flag.flag_type] += 1
            print(f"  Building {bid}: {flag.flag_type} — {flag.detail}")

    print("=" * 70)
    if flag_count == 0:
        print(f"✓ All {len(building_ids)} buildings passed sanity checks")
    else:
        print(f"⚠ {flag_count} flags across {len(building_ids)} buildings:")
        for ftype, count in sorted(flag_by_type.items()):
            print(f"  {ftype}: {count}")
