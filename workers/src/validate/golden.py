"""Golden buildings: curated set for manual validation."""

from src.common.db import get_connection, get_cursor


def add_golden_buildings(building_ids: list[int], reason: str | None = None) -> int:
    """Insert building IDs into golden set. Returns count added."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            count = 0
            for bid in building_ids:
                cur.execute("""
                    INSERT INTO logistics.golden_buildings (building_id, reason)
                    VALUES (%s, %s)
                    ON CONFLICT (building_id) DO NOTHING
                """, (bid, reason))
                if cur.rowcount > 0:
                    count += 1
            conn.commit()
    return count


def remove_golden_buildings(building_ids: list[int]) -> int:
    """Remove building IDs from golden set. Returns count removed."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            count = 0
            for bid in building_ids:
                cur.execute("""
                    DELETE FROM logistics.golden_buildings
                    WHERE building_id = %s
                """, (bid,))
                count += cur.rowcount
            conn.commit()
    return count


def list_golden_buildings() -> list[dict]:
    """Return golden buildings with metadata (name, address, stop count)."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute("""
                SELECT
                    gb.building_id,
                    b.name,
                    b.address,
                    COALESCE(b.building_type, '--') as building_type,
                    gb.reason,
                    gb.added_at,
                    COUNT(bse.id) as stop_count
                FROM logistics.golden_buildings gb
                JOIN logistics.buildings b ON b.id = gb.building_id
                LEFT JOIN logistics.building_stop_events bse ON bse.building_id = gb.building_id
                GROUP BY gb.building_id, b.name, b.address, b.building_type, gb.reason, gb.added_at
                ORDER BY gb.building_id
            """)
            rows = cur.fetchall()
            return [
                {
                    "building_id": row[0],
                    "name": row[1],
                    "address": row[2],
                    "building_type": row[3],
                    "reason": row[4],
                    "added_at": row[5],
                    "stop_count": row[6],
                }
                for row in rows
            ]


def print_golden_list() -> None:
    """Print golden buildings in a formatted table."""
    buildings = list_golden_buildings()

    if not buildings:
        print("\nNo golden buildings yet. Use: golden-add --building-ids <id> --reason <reason>")
        return

    print(f"\nGolden Buildings ({len(buildings)} total)")
    print("=" * 100)
    print(f"{'ID':<10} {'Name':<30} {'Type':<15} {'Stops':<8} {'Reason':<20}")
    print("-" * 100)

    for b in buildings:
        name = (b["name"] or "")[:28] if b["name"] else "--"
        btype = (b["building_type"] or "")[:13] if b["building_type"] else "--"
        reason = (b["reason"] or "")[:18] if b["reason"] else "--"
        print(f"{b['building_id']:<10} {name:<30} {btype:<15} {b['stop_count']:<8} {reason:<20}")

    print("=" * 100)
