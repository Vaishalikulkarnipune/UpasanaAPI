"""
Which of the newer optional columns exist in this database.

users.created_at (joining date), bookings.is_trial (trial-run flag), users.updated_at /
updated_by (last profile change) and the profile_change_requests table are added by the API at
startup and by migrations/*.sql. If either is still missing (for example the startup schema change
could not run), the code paths that use them fall back instead of failing, so registration, login
and booking keep working.

refresh() runs once at startup, after the schema changes; has() is a cheap lookup afterwards.
"""

import logging
from sqlalchemy import text

OPTIONAL_COLUMNS = (
    "users.created_at",
    "bookings.is_trial",
    "users.updated_at",
    "users.updated_by",
    "profile_change_requests.id",
    "bookings.zone_code",
    "bookings.host_area",
    "admin_accounts.id",
    "admin_sessions.id",
    "bookings.map_link",
    "upasana_events.map_link",
    "upasana_waitlist.id",
    "bookings.attendance_count",
    "upasana_events.attendance_count",
    "bookings.attendance_expected",
    "upasana_events.attendance_expected",
    "upasana_waitlist.mahaprasad",
)

_present = set()


def refresh(engine):
    global _present
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT table_name || '.' || column_name FROM information_schema.columns "
                "WHERE table_name IN ('users', 'bookings', 'profile_change_requests', 'admin_accounts', 'admin_sessions', 'upasana_events', 'upasana_waitlist')"
            )).all()
        _present = {r[0] for r in rows}
    except Exception as e:
        logging.error(f"Could not read the database columns: {e}")
        _present = set()
    missing = [c for c in OPTIONAL_COLUMNS if c not in _present]
    if missing:
        logging.error(
            f"Columns missing: {', '.join(missing)}. The app keeps working without them, but run "
            "the SQL in migrations/ to enable joining dates and trial-run flags."
        )


def has(column):
    """has("users.created_at") -> True when the column exists."""
    return column in _present
