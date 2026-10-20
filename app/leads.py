"""SiteScout AI - lead database operations."""
import csv
import io

from app.database import db

STATUSES = [
    "discovered", "qualified", "demo_ready", "outreach_pending", "contacted",
    "replied", "interested", "not_interested", "follow_up", "won", "lost", "inactive",
]
PRIORITIES = ["low", "normal", "high"]
WEBSITE_STATUSES = ["unchecked", "no_website_found", "reachable", "possibly_broken"]

EDITABLE_FIELDS = [
    "name", "category", "country", "city", "phone", "email", "address",
    "website", "source", "source_url", "website_status", "demo_url",
    "followup_date", "status", "priority",
]
CSV_FIELDS = [
    "id", "name", "category", "country", "city", "phone", "email", "address",
    "website", "website_status", "status", "priority", "demo_url",
    "followup_date", "do_not_contact", "source", "created_at",
]


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def validate(data: dict) -> list:
    """Return a list of error messages (empty list means valid)."""
    errors = []
    if not _clean(data.get("name")):
        errors.append("Name is required.")
    if data.get("status") and data["status"] not in STATUSES:
        errors.append("Invalid status.")
    if data.get("priority") and data["priority"] not in PRIORITIES:
        errors.append("Invalid priority.")
    if data.get("website_status") and data["website_status"] not in WEBSITE_STATUSES:
        errors.append("Invalid website status.")
    return errors


def add_event(conn, lead_id: int, event: str) -> None:
    conn.execute("INSERT INTO lead_events (lead_id, event) VALUES (?, ?)", (lead_id, event))


def create_lead(data: dict) -> int:
    values = {k: _clean(data.get(k)) for k in EDITABLE_FIELDS}
    values["status"] = values["status"] or "discovered"
    values["priority"] = values["priority"] or "normal"
    values["website_status"] = values["website_status"] or "unchecked"
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    with db() as conn:
        cur = conn.execute(f"INSERT INTO leads ({columns}) VALUES ({marks})", list(values.values()))
        lead_id = cur.lastrowid
        add_event(conn, lead_id, "Lead created")
    return lead_id


def get_lead(lead_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return dict(row) if row else None


def list_leads(search="", status="", priority="", website_status="", limit=200, offset=0):
    sql = "SELECT * FROM leads WHERE 1=1"
    params = []
    if search:
        like = f"%{search}%"
        sql += " AND (name LIKE ? OR city LIKE ? OR category LIKE ? OR phone LIKE ?)"
        params += [like, like, like, like]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if priority:
        sql += " AND priority = ?"
        params.append(priority)
    if website_status:
        sql += " AND website_status = ?"
        params.append(website_status)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def update_lead(lead_id: int, data: dict) -> bool:
    values = {k: _clean(data.get(k)) for k in EDITABLE_FIELDS if k in data}
    if not values:
        return False
    sets = ", ".join(f"{k} = ?" for k in values) + ", updated_at = datetime('now')"
    with db() as conn:
        old = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if old is None:
            return False
        conn.execute(f"UPDATE leads SET {sets} WHERE id = ?", list(values.values()) + [lead_id])
        for key, new in values.items():
            if (old[key] or None) != new:
                add_event(conn, lead_id, f"{key} changed: {old[key] or '-'} -> {new or '-'}")
    return True


def set_do_not_contact(lead_id: int, flag: bool) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE leads SET do_not_contact = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if flag else 0, lead_id),
        )
        add_event(conn, lead_id, "Marked DO NOT CONTACT" if flag else "Do-not-contact removed")


def add_note(lead_id: int, note: str) -> bool:
    note = _clean(note)
    if not note:
        return False
    with db() as conn:
        conn.execute("INSERT INTO lead_notes (lead_id, note) VALUES (?, ?)", (lead_id, note))
        add_event(conn, lead_id, "Note added")
    return True


def get_notes(lead_id: int):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM lead_notes WHERE lead_id = ? ORDER BY id DESC", (lead_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_events(lead_id: int):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM lead_events WHERE lead_id = ? ORDER BY id DESC", (lead_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_lead(lead_id: int) -> bool:
    with db() as conn:
        cur = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    return cur.rowcount > 0


def export_csv() -> str:
    with db() as conn:
        rows = conn.execute("SELECT * FROM leads ORDER BY id").fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_FIELDS)
    for row in rows:
        cells = []
        for field in CSV_FIELDS:
            value = row[field]
            value = "" if value is None else str(value)
            # Stop spreadsheet formula injection from imported business data.
            if value[:1] in ("=", "+", "-", "@"):
                value = "'" + value
            cells.append(value)
        writer.writerow(cells)
    return out.getvalue()


def dashboard_counts() -> dict:
    with db() as conn:
        def one(sql, params=()):
            return conn.execute(sql, params).fetchone()[0]
        return {
            "total": one("SELECT COUNT(*) FROM leads"),
            "no_website": one("SELECT COUNT(*) FROM leads WHERE website_status = 'no_website_found'"),
            "has_website": one(
                "SELECT COUNT(*) FROM leads WHERE website_status IN ('reachable', 'possibly_broken')"
            ),
            "qualified": one("SELECT COUNT(*) FROM leads WHERE status = 'qualified'"),
            "demos": one("SELECT COUNT(*) FROM leads WHERE demo_url IS NOT NULL AND demo_url != ''"),
            "pending_outreach": one("SELECT COUNT(*) FROM leads WHERE status = 'outreach_pending'"),
            "replies": one("SELECT COUNT(*) FROM leads WHERE status IN ('replied', 'interested')"),
            "interested": one("SELECT COUNT(*) FROM leads WHERE status = 'interested'"),
            "followups_due": one(
                "SELECT COUNT(*) FROM leads WHERE followup_date IS NOT NULL "
                "AND followup_date != '' AND followup_date <= date('now') "
                "AND status NOT IN ('won', 'lost', 'inactive') AND do_not_contact = 0"
            ),
            "converted": one("SELECT COUNT(*) FROM leads WHERE status = 'won'"),
        }
