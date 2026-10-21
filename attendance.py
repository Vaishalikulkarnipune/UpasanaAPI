"""
Attendance after an Upasana (admins only).

Admins record how many people confirmed they would attend (expected) and roughly how many
actually attended, with a short note, for a member booking or a common Upasana (event). It can be entered once the date has come and until 31 December of that
year (IST); after that it is read-only. Only admins see it (Stats → Attendance, which can be shared
on WhatsApp, and the year-end report).

Endpoints (admin login)
  GET  /admin/attendance?year=YYYY     every Upasana of the year up to today, with attendance
  POST /admin/attendance               { booking_id | event_id, expected, count, note }  (null clears)
Columns: migrations/add_attendance.sql (also added at start-up).
"""

import logging
from datetime import datetime, timedelta, date

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from admin_auth import admin_required, require_admin
from model import db, Booking, User, UpasanaEvent
import schema_check

router = Blueprint("attendance", __name__)

IST = timedelta(hours=5, minutes=30)
NOTE_MAX = 300
COUNT_MAX = 5000

SCHEMA = [
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS attendance_count INTEGER",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS attendance_note VARCHAR(300)",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS attendance_at TIMESTAMP",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS attendance_by VARCHAR(120)",
    "ALTER TABLE upasana_events ADD COLUMN IF NOT EXISTS attendance_count INTEGER",
    "ALTER TABLE upasana_events ADD COLUMN IF NOT EXISTS attendance_note VARCHAR(300)",
    "ALTER TABLE upasana_events ADD COLUMN IF NOT EXISTS attendance_at TIMESTAMP",
    "ALTER TABLE upasana_events ADD COLUMN IF NOT EXISTS attendance_by VARCHAR(120)",
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS attendance_expected INTEGER",
    "ALTER TABLE upasana_events ADD COLUMN IF NOT EXISTS attendance_expected INTEGER",
]


def ready():
    return all(schema_check.has(c) for c in (
        "bookings.attendance_count", "upasana_events.attendance_count",
        "bookings.attendance_expected", "upasana_events.attendance_expected"))


def today_ist():
    return (datetime.utcnow() + IST).date()


def _iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:%S+05:30") if ts else None


def editable(day):
    """Attendance can be entered from the Upasana day until 31 December of its year."""
    today = today_ist()
    return day <= today <= date(day.year, 12, 31)


def _name(u):
    return " ".join(p.strip() for p in [u.first_name, u.middle_name, u.last_name] if p and p.strip())


@router.route("/admin/attendance", methods=["GET"])
@admin_required
def list_attendance():
    from upasana_settings import get_booking_settings
    year = request.args.get("year", type=int) or today_ist().year
    if not ready():
        return jsonify({"year": year, "items": [], "available": False}), 200
    today = today_ist()
    start, end = date(year, 1, 1), min(date(year, 12, 31), today)
    items = []
    if start <= end:
        trial_filter = "AND NOT b.is_trial" if schema_check.has("bookings.is_trial") else ""
        zone = "COALESCE(b.zone_code, u.zone_code)" if schema_check.has("bookings.zone_code") else "u.zone_code"
        area = "COALESCE(b.host_area, u.area)" if schema_check.has("bookings.host_area") else "u.area"
        rows = db.session.execute(text(f"""
            SELECT b.id, b.booking_date, b.mahaprasad, b.attendance_count, b.attendance_note, b.attendance_at,
                   b.attendance_by, u.first_name, u.middle_name, u.last_name, {zone}, {area}, b.attendance_expected
              FROM bookings b JOIN users u ON u.id = b.user_id
             WHERE b.is_active {trial_filter} AND b.booking_date BETWEEN :s AND :e
        """), {"s": start, "e": end}).all()
        for r in rows:
            items.append({
                "kind": "booking", "id": r[0], "date": r[1].strftime("%Y-%m-%d"), "mahaprasad": bool(r[2]),
                "count": r[3], "note": r[4] or "", "updated_at": _iso(r[5]), "updated_by": r[6],
                "name": " ".join(p.strip() for p in r[7:10] if p and p.strip()),
                "zone_code": r[10] or "", "area": (r[11] or "").strip(), "expected": r[12],
                "editable": editable(r[1]),
            })
        rows = db.session.execute(text("""
            SELECT id, event_date, mahaprasad, attendance_count, attendance_note, attendance_at, attendance_by,
                   title, address, attendance_expected
              FROM upasana_events WHERE is_active AND event_date BETWEEN :s AND :e
        """), {"s": start, "e": end}).all()
        for r in rows:
            items.append({
                "kind": "event", "id": r[0], "date": r[1].strftime("%Y-%m-%d"), "mahaprasad": bool(r[2]),
                "count": r[3], "note": r[4] or "", "updated_at": _iso(r[5]), "updated_by": r[6],
                "name": r[7], "zone_code": "", "area": (r[8] or "").strip(), "expected": r[9],
                "editable": editable(r[1]),
            })
    items.sort(key=lambda x: (x["date"], x["kind"]))
    booking_year = get_booking_settings()["booking_year"]
    years = list(range(2023, max(today.year, booking_year or today.year) + 1))
    return jsonify({"year": year, "items": items, "available": True, "years": years}), 200


@router.route("/admin/attendance", methods=["POST"])
def save_attendance():
    err, status, admin_label = require_admin()
    if err:
        return err, status
    if not ready():
        return jsonify({"error": "Attendance is not available yet (run migrations/add_attendance.sql)."}), 503
    data = request.get_json(silent=True) or {}

    def number(key, label):
        raw = data.get(key)
        if raw in (None, ""):
            return None, None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None, f"{label} must be a number."
        if value < 0 or value > COUNT_MAX:
            return None, f"{label} must be between 0 and {COUNT_MAX}."
        return value, None

    count, error = number("count", "Attendance")
    if error:
        return jsonify({"error": error}), 400
    expected, error = number("expected", "Attendance confirmed")
    if error:
        return jsonify({"error": error}), 400
    note = (str(data.get("note") or "").strip())[:NOTE_MAX] or None

    if data.get("booking_id") not in (None, ""):
        table, row = "bookings", Booking.query.get(int(data["booking_id"]))
        day = row.booking_date if row and row.is_active else None
    elif data.get("event_id") not in (None, ""):
        table, row = "upasana_events", UpasanaEvent.query.get(int(data["event_id"]))
        day = row.event_date if row and row.is_active else None
    else:
        return jsonify({"error": "booking_id or event_id is required."}), 400
    if not day:
        return jsonify({"error": "Upasana not found."}), 404
    if day > today_ist():
        return jsonify({"error": "Attendance can be entered on or after the Upasana date."}), 400
    if not editable(day):
        return jsonify({"error": f"Attendance for {day.year} can no longer be changed (only until 31 December {day.year})."}), 400

    from profile_changes import actor_label
    by = actor_label(admin_label)
    try:
        db.session.execute(
            text(f"UPDATE {table} SET attendance_count = :c, attendance_expected = :x, attendance_note = :n, "
                 f"attendance_at = :t, attendance_by = :b WHERE id = :i"),
            {"c": count, "x": expected, "n": note, "t": datetime.utcnow() + IST, "b": by[:120], "i": row.id},
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.exception(f"save_attendance failed: {e}")
        return jsonify({"error": "Could not save the attendance."}), 500
    saved = count is not None or expected is not None
    return jsonify({"message": "Attendance saved." if saved else "Attendance cleared.",
                    "count": count, "expected": expected, "note": note or "", "updated_by": by}), 200
