"""
Upasana waitlist.

When every bookable date of a member's zone for the booking year is gone, the member can join a
waitlist instead of booking (preferred months or "any month", optional note). Admins and the
committee decide; an admin then gives the member a date with Add Upasana (Saturdays and Sundays
that are still free), which creates a normal admin booking and marks the entry allocated.

Rules
  * Join only while booking is open AND the admin has the waitlist open (setting `waitlist_open`).
  * Only when the member's zone has no bookable date left in the year, and the member has no
    Upasana that year. One active entry (waiting or allocated) per member per year.
  * Members may edit or withdraw while waiting; admins see "Edited" / "Withdrawn" / "Rejoined".
  * Entries made during a trial run are marked trial (deleted by hand with trial bookings).
  * Only admins see the list. A member sees only their own entry, clearly marked as not a booking.

Endpoints
  GET  /waitlist/me?user_id=                  member: status + own entry for the booking year
  POST /waitlist/join      {user_id, months[], note}
  POST /waitlist/update    {user_id, months[], note}
  POST /waitlist/withdraw  {user_id}
  GET  /admin/waitlist?year=                  admin: every entry of the year, oldest first
  (allocation: POST /admin/book with waitlist_id; see admin_bookings.py)
Table: migrations/add_waitlist.sql (also created at start-up).
"""

import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from admin_auth import admin_required
from model import db, User
import schema_check

router = Blueprint("waitlist", __name__)

IST = timedelta(hours=5, minutes=30)
OPEN_KEY = "waitlist_open"          # reference_data; "false" = closed by admin, anything else open
NOTE_MAX = 500

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS upasana_waitlist (
           id SERIAL PRIMARY KEY,
           user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
           year INTEGER NOT NULL,
           preferred_months VARCHAR(40) NOT NULL DEFAULT '',
           note VARCHAR(500),
           status VARCHAR(20) NOT NULL DEFAULT 'waiting',
           is_trial BOOLEAN NOT NULL DEFAULT FALSE,
           zone_code VARCHAR(20),
           host_area VARCHAR(100),
           edited BOOLEAN NOT NULL DEFAULT FALSE,
           created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Kolkata'),
           updated_at TIMESTAMP,
           withdrawn_at TIMESTAMP,
           allocated_booking_id INTEGER REFERENCES bookings(id) ON DELETE SET NULL,
           allocated_at TIMESTAMP,
           allocated_by VARCHAR(120),
           mahaprasad BOOLEAN
       )""",
    "ALTER TABLE upasana_waitlist ADD COLUMN IF NOT EXISTS mahaprasad BOOLEAN",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_waitlist_active_member_year
       ON upasana_waitlist (user_id, year) WHERE status IN ('waiting', 'allocated')""",
    "CREATE INDEX IF NOT EXISTS ix_waitlist_year ON upasana_waitlist (year, status, created_at)",
]

COLUMNS = ("id, user_id, year, preferred_months, note, status, is_trial, zone_code, host_area, edited, "
           "created_at, updated_at, withdrawn_at, allocated_booking_id, allocated_at, allocated_by, mahaprasad")


def ready():
    return schema_check.has("upasana_waitlist.id")


def now_ist():
    return datetime.utcnow() + IST


def _iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:%S+05:30") if ts else None


def _name(u):
    return " ".join(p.strip() for p in [u.first_name, u.middle_name, u.last_name] if p and p.strip())


def _clean_months(raw):
    """Sorted unique months 1–12 from a list; empty list = any month."""
    out = set()
    for m in raw or []:
        try:
            m = int(m)
        except (TypeError, ValueError):
            continue
        if 1 <= m <= 12:
            out.add(m)
    return sorted(out)


def _row_dict(r):
    keys = [c.strip() for c in COLUMNS.split(",")]
    d = dict(zip(keys, r))
    months = [int(x) for x in (d["preferred_months"] or "").split(",") if x.strip()]
    return {
        "id": d["id"], "user_id": d["user_id"], "year": d["year"],
        "months": months, "any_month": not months,
        "note": d["note"] or "", "status": d["status"], "is_trial": bool(d["is_trial"]),
        "zone_code": d["zone_code"] or "", "host_area": d["host_area"] or "",
        "edited": bool(d["edited"]),
        "created_at": _iso(d["created_at"]), "updated_at": _iso(d["updated_at"]),
        "withdrawn_at": _iso(d["withdrawn_at"]),
        "allocated_booking_id": d["allocated_booking_id"], "allocated_at": _iso(d["allocated_at"]),
        "allocated_by": d["allocated_by"],
        "mahaprasad": d["mahaprasad"],         # True / False as chosen when joining; None = not asked
    }


# ─── Settings and eligibility ─────────────────────────────────────────────────

def admin_open_setting():
    from upasana_settings import _reference
    return _reference(OPEN_KEY) != "false"


def set_admin_open(value):
    """Caller commits."""
    from upasana_settings import _set_reference
    _set_reference(OPEN_KEY, "true" if value else "false")


def waitlist_state(user=None):
    """
    {"open", "admin_open", "booking_open", "year", "zone_complete", "eligible", "reason"} —
    `open`: members can join now (booking open and admin switch on); `eligible`: this member can.
    """
    from upasana_settings import get_booking_settings
    from Booking import year_zone_overview, active_booking_in_year, ZONE_LIMITS
    settings = get_booking_settings()
    year = settings["booking_year"]
    admin_open = admin_open_setting()
    booking_open = bool(settings["enable_booking"]) and bool(year)
    state = {"year": year, "admin_open": admin_open, "booking_open": booking_open,
             "open": ready() and admin_open and booking_open,
             "zone_complete": False, "eligible": False, "reason": None}
    if user is None or not year:
        return state
    if not ready():
        state["reason"] = "not_available"
        return state
    zone = user.zone_code
    if zone not in ZONE_LIMITS:
        state["reason"] = "zone_unknown"
        return state
    open_months = year_zone_overview(year, settings["enable_zone_restriction"])["open_months"]
    state["zone_complete"] = not open_months.get(zone)
    if not state["open"]:
        state["reason"] = "closed"
    elif active_booking_in_year(user.id, year):
        state["reason"] = "already_booked"
    elif not state["zone_complete"]:
        state["reason"] = "zone_has_dates"
    else:
        state["eligible"] = True
    return state


def _member_entry(user_id, year):
    """Latest entry of this member for the year (any status), or None."""
    row = db.session.execute(
        text(f"SELECT {COLUMNS} FROM upasana_waitlist WHERE user_id = :u AND year = :y ORDER BY id DESC LIMIT 1"),
        {"u": user_id, "y": year},
    ).first()
    return _row_dict(row) if row else None


def _allocated_date(entry):
    if not entry or not entry.get("allocated_booking_id"):
        return None
    row = db.session.execute(
        text("SELECT booking_date FROM bookings WHERE id = :i AND is_active"), {"i": entry["allocated_booking_id"]}
    ).first()
    return row[0].strftime("%Y-%m-%d") if row else None


def member_summary(user):
    """State + own entry, for the booking page, Home and My Bookings."""
    state = waitlist_state(user)
    entry = _member_entry(user.id, state["year"]) if (state["year"] and ready()) else None
    if entry:
        entry["allocated_date"] = _allocated_date(entry)
        if entry["status"] == "withdrawn":
            entry_out = None            # a withdrawn entry is not shown to the member
        else:
            entry_out = entry
    else:
        entry_out = None
    # A member already on the waitlist is not "eligible to join" again, but may edit/withdraw
    if entry_out and entry_out["status"] == "waiting":
        state["eligible"] = False
        state["reason"] = "on_waitlist"
        entry_out.update(_queue_info(entry_out, user, state["year"]))
    return {**state, "entry": entry_out}


def _queue_info(entry, user, year):
    """For the member's waiting entry: their number in the zone's queue (same order as the admin
    list: oldest first), how many are waiting in the zone, and how many times they have hosted
    before this year (real Upasana, not trial)."""
    zone = entry.get("zone_code") or user.zone_code or ""
    queue = db.session.execute(
        text("SELECT w.id FROM upasana_waitlist w JOIN users u ON u.id = w.user_id "
             "WHERE w.year = :y AND w.status = 'waiting' AND COALESCE(NULLIF(w.zone_code, ''), u.zone_code, '') = :z "
             "ORDER BY w.created_at, w.id"),
        {"y": year, "z": zone},
    ).scalars().all()
    trial = "AND NOT is_trial" if schema_check.has("bookings.is_trial") else ""
    hosted = db.session.execute(
        text(f"SELECT COUNT(*) FROM bookings WHERE user_id = :u AND is_active {trial} "
             f"AND booking_date < make_date(:y, 1, 1)"),
        {"u": user.id, "y": year},
    ).scalar() or 0
    return {
        "position": (queue.index(entry["id"]) + 1) if entry["id"] in queue else None,
        "zone_waiting": len(queue),
        "hosted_count": int(hosted),
    }


def _mahaprasad(data):
    """(value, error) for the required Mahaprasad choice when joining or editing."""
    value = data.get("mahaprasad")
    if value is True or value is False:
        return value, None
    return None, "Please choose whether MahaPrasad is available."


def _user_from_body():
    data = request.get_json(silent=True) or {}
    try:
        user = User.query.get(int(data.get("user_id")))
    except (TypeError, ValueError):
        user = None
    return data, user


# ─── Member endpoints ─────────────────────────────────────────────────────────

@router.route("/waitlist/me", methods=["GET"])
def my_waitlist():
    user = User.query.get(request.args.get("user_id", type=int) or 0)
    if not user:
        return jsonify({"error": "Member not found."}), 404
    return jsonify(member_summary(user)), 200


@router.route("/waitlist/join", methods=["POST"])
def join_waitlist():
    data, user = _user_from_body()
    if not user:
        return jsonify({"error": "Member not found."}), 404
    state = member_summary(user)          # includes "already on the waitlist"
    if not state["eligible"]:
        messages = {
            "on_waitlist": "You are already on the waitlist.",
            "not_available": "The waitlist is not available yet.",
            "closed": "The waitlist is closed now.",
            "already_booked": "You already have an Upasana this year.",
            "zone_has_dates": "Your zone still has dates available. Please book a date instead.",
            "zone_unknown": "Your zone is not set. Please contact the admin.",
        }
        return jsonify({"error": messages.get(state["reason"], "You cannot join the waitlist now."),
                        "code": state["reason"]}), 400
    from upasana_settings import trial_is_active
    months = _clean_months(data.get("months"))
    note = (str(data.get("note") or "").strip())[:NOTE_MAX] or None
    mahaprasad, error = _mahaprasad(data)
    if error:
        return jsonify({"error": error, "code": "mahaprasad_required"}), 400
    try:
        db.session.execute(
            text("INSERT INTO upasana_waitlist (user_id, year, preferred_months, note, status, is_trial, "
                 "zone_code, host_area, created_at, mahaprasad) "
                 "VALUES (:u, :y, :m, :n, 'waiting', :t, :z, :a, :c, :mp)"),
            {"u": user.id, "y": state["year"], "m": ",".join(map(str, months)), "n": note,
             "t": bool(trial_is_active()), "z": user.zone_code, "a": (user.area or "").strip() or None,
             "c": now_ist(), "mp": mahaprasad},
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        if "uq_waitlist_active_member_year" in str(e):
            return jsonify({"error": "You are already on the waitlist.", "code": "on_waitlist"}), 409
        logging.exception(f"join_waitlist failed: {e}")
        return jsonify({"error": "Could not join the waitlist. Please try again."}), 500
    logging.info(f"Member {user.id} joined the {state['year']} waitlist")
    return jsonify({"message": "Added to the waitlist.", **member_summary(user)}), 201


@router.route("/waitlist/update", methods=["POST"])
def update_waitlist():
    data, user = _user_from_body()
    if not user:
        return jsonify({"error": "Member not found."}), 404
    state = waitlist_state(user)
    months = _clean_months(data.get("months"))
    note = (str(data.get("note") or "").strip())[:NOTE_MAX] or None
    mahaprasad, error = _mahaprasad(data)
    if error:
        return jsonify({"error": error, "code": "mahaprasad_required"}), 400
    updated = db.session.execute(
        text("UPDATE upasana_waitlist SET preferred_months = :m, note = :n, mahaprasad = :mp, edited = TRUE, "
             "updated_at = :t WHERE user_id = :u AND year = :y AND status = 'waiting'"),
        {"m": ",".join(map(str, months)), "n": note, "mp": mahaprasad, "t": now_ist(),
         "u": user.id, "y": state["year"]},
    ).rowcount
    if not updated:
        db.session.rollback()
        return jsonify({"error": "You are not on the waitlist (or a date was already given)."}), 404
    db.session.commit()
    return jsonify({"message": "Waitlist details updated.", **member_summary(user)}), 200


@router.route("/waitlist/withdraw", methods=["POST"])
def withdraw_waitlist():
    data, user = _user_from_body()
    if not user:
        return jsonify({"error": "Member not found."}), 404
    state = waitlist_state(user)
    updated = db.session.execute(
        text("UPDATE upasana_waitlist SET status = 'withdrawn', withdrawn_at = :t, updated_at = :t "
             "WHERE user_id = :u AND year = :y AND status = 'waiting'"),
        {"t": now_ist(), "u": user.id, "y": state["year"]},
    ).rowcount
    if not updated:
        db.session.rollback()
        return jsonify({"error": "You are not on the waitlist (or a date was already given)."}), 404
    db.session.commit()
    logging.info(f"Member {user.id} withdrew from the {state['year']} waitlist")
    return jsonify({"message": "Removed from the waitlist.", **member_summary(user)}), 200


# ─── Admin ────────────────────────────────────────────────────────────────────

@router.route("/admin/waitlist", methods=["GET"])
@admin_required
def admin_waitlist():
    from upasana_settings import get_booking_settings
    from profile_changes import actor_label
    year = request.args.get("year", type=int) or get_booking_settings()["booking_year"]
    if not ready():
        return jsonify({"year": year, "entries": [], "admin_open": admin_open_setting(), "available": False}), 200
    rows = db.session.execute(
        text(f"SELECT {COLUMNS} FROM upasana_waitlist WHERE year = :y ORDER BY created_at, id"), {"y": year}
    ).all()
    entries = [_row_dict(r) for r in rows]
    users = {u.id: u for u in User.query.filter(User.id.in_({e["user_id"] for e in entries} or {0})).all()}

    # Earlier Upasana of each member (before this year; real bookings, not trial): "hosted 2 times: 2023, 2024"
    hosted = {}
    if entries:
        trial = "AND NOT is_trial" if schema_check.has("bookings.is_trial") else ""
        for uid, yr in db.session.execute(text(
            f"SELECT user_id, EXTRACT(YEAR FROM booking_date)::int FROM bookings "
            f"WHERE is_active {trial} AND user_id = ANY(:ids) AND booking_date < make_date(:y, 1, 1) "
            f"ORDER BY booking_date"), {"ids": list({e["user_id"] for e in entries}), "y": year}).all():
            hosted.setdefault(uid, []).append(yr)

    # Earlier withdrawn entries of the same member -> "Rejoined" on the later one
    seen_withdrawn = set()
    position = {}                                  # zone -> running number among waiting entries
    out = []
    for e in entries:
        u = users.get(e["user_id"])
        if not u:
            continue
        zone = e["zone_code"] or u.zone_code or ""
        e.update({
            "name": _name(u), "mobile_number": u.mobile_number or "",
            "zone_code": zone, "area": (u.area or "").strip() or e["host_area"],
            "rejoined": e["user_id"] in seen_withdrawn,
            "allocated_date": _allocated_date(e),
            "allocated_by": actor_label(e["allocated_by"]) if e["allocated_by"] else None,
            "hosted_years": hosted.get(e["user_id"], []),
            "position": None,
        })
        if e["status"] == "withdrawn":
            seen_withdrawn.add(e["user_id"])
        if e["status"] == "waiting":
            position[zone] = position.get(zone, 0) + 1
            e["position"] = position[zone]
        out.append(e)
    counts = {s: sum(1 for e in out if e["status"] == s) for s in ("waiting", "allocated", "withdrawn")}
    return jsonify({"year": year, "entries": out, "counts": counts,
                    "admin_open": admin_open_setting(), "available": True}), 200


def waitlist_entry_for_allocation(waitlist_id, user_id):
    """The waiting entry this admin booking allocates, or (None, error)."""
    if not ready():
        return None, "The waitlist is not available."
    row = db.session.execute(
        text(f"SELECT {COLUMNS} FROM upasana_waitlist WHERE id = :i FOR UPDATE"), {"i": waitlist_id}
    ).first()
    if not row:
        return None, "Waitlist entry not found."
    entry = _row_dict(row)
    if entry["user_id"] != user_id:
        return None, "This waitlist entry belongs to another member."
    if entry["status"] != "waiting":
        return None, f"This waitlist entry is already {entry['status']}."
    return entry, None


def mark_allocated(waitlist_id, booking_id, admin_label):
    """Caller commits (same transaction as the booking)."""
    db.session.execute(
        text("UPDATE upasana_waitlist SET status = 'allocated', allocated_booking_id = :b, allocated_at = :t, "
             "allocated_by = :by, updated_at = :t WHERE id = :i"),
        {"b": booking_id, "t": now_ist(), "by": (admin_label or "")[:120], "i": waitlist_id},
    )
