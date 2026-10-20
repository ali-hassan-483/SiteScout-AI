"""SiteScout AI - save discovered businesses as leads, skipping duplicates."""
from app.database import db
from app.leads import add_event

FIELDS = [
    "name", "category", "country", "city", "phone", "email", "address",
    "website", "source", "source_url", "osm_ref",
]


def import_leads(found: list, only_with_phone: bool = False, only_no_website: bool = False) -> dict:
    """Insert discovered leads. Returns counts: added, duplicates, filtered."""
    added = duplicates = filtered = 0
    with db() as conn:
        for item in found:
            if only_with_phone and not item.get("phone"):
                filtered += 1
                continue
            if only_no_website and item.get("website"):
                filtered += 1
                continue
            ref = item.get("osm_ref")
            if ref and conn.execute(
                "SELECT 1 FROM leads WHERE osm_ref = ?", (ref,)
            ).fetchone():
                duplicates += 1
                continue
            values = [item.get(f) for f in FIELDS]
            cur = conn.execute(
                f"INSERT INTO leads ({', '.join(FIELDS)}) "
                f"VALUES ({', '.join('?' for _ in FIELDS)})",
                values,
            )
            add_event(conn, cur.lastrowid, f"Imported from {item.get('source')}")
            added += 1
    return {"added": added, "duplicates": duplicates, "filtered": filtered}
