"""
Member profile changes that need an admin's approval, plus "last updated" tracking.

A member edits their details in the app; that creates a change request instead of changing the
profile. An admin sees the request (old -> new values, and what it affects: zone change, upcoming
Upasana) and approves or rejects it. Only approved changes reach users.

Endpoints
─────────
  GET  /users/<id>/change-request                member: their latest request (pending or decided)
  POST /users/<id>/change-request                member: { changes: {field: value} } (replaces a pending one)
  GET  /admin/change-requests                    admin: pending requests with impact
  POST /admin/change-requests/<id>/decide        admin: { approve: true|false, note? }

users.updated_at / users.updated_by are set on every profile change (admin edit, completed
profile, approved request). Times are IST. Table and columns are created at startup and by
migrations/add_profile_changes.sql.
"""

import json
import logging
import re
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from model import db, Booking, User
from admin_auth import require_admin, SUPER_ADMIN_MOBILE
import schema_check

router = Blueprint("profile_changes", __name__)

IST = timedelta(hours=5, minutes=30)

# What a member may change themselves (mobile number is their login, so only an admin changes it)
MEMBER_FIELDS = {
    "first_name": "First name",
    "middle_name": "Middle name",
    "last_name": "Last name",
    "email": "Email",
    "alternate_mobile_number": "Alternate mobile",
    "flat_no": "Flat / House",
    "full_address": "Full address",
    "area": "Area",
    "landmark": "Landmark",
    "pincode": "PIN code",
    "gender": "Gender",
    "anugrahit": "Anugrahit",
}
ADDRESS_FIELDS = {"flat_no", "full_address", "area", "landmark", "pincode"}
REQUIRED = {"first_name", "last_name", "full_address", "area", "landmark", "pincode"}

SCHEMA = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_by VARCHAR(120)",
    """CREATE TABLE IF NOT EXISTS profile_change_requests (
           id SERIAL PRIMARY KEY,
           user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
           changes TEXT NOT NULL,
           status VARCHAR(20) NOT NULL DEFAULT 'pending',
           created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Kolkata'),
           decided_at TIMESTAMP,
           decided_by VARCHAR(120),
           admin_note VARCHAR(500)
       )""",
    "CREATE INDEX IF NOT EXISTS ix_profile_change_requests_user ON profile_change_requests (user_id, status)",
]


def now_ist():
    return datetime.utcnow() + IST


def _iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:%S+05:30") if ts else None


def _name(u):
    return " ".join(p for p in [u.first_name, u.middle_name, u.last_name] if p).strip()


def actor_label(user_id_or_mobile):
    """'Super admin', 'Admin: Name' or 'Member: Name' for whoever made a change."""
    value = str(user_id_or_mobile or "").strip()
    if not value:
        return "Unknown"
    if value == SUPER_ADMIN_MOBILE:
        return "Super admin"
    try:
        u = User.query.get(int(value))
    except (TypeError, ValueError):
        return "Unknown"
    if not u:
        return "Unknown"
    return f"{'Admin' if u.isadmin else 'Member'}: {_name(u)}"


def mark_updated(cursor_or_none, user_id, by_label):
    """Record when/who last changed a member's profile. Works with a raw cursor or the ORM session."""
    if not schema_check.has("users.updated_at"):
        return
    params = {"at": now_ist(), "by": (by_label or "Unknown")[:120], "id": user_id}
    if cursor_or_none is not None:
        cursor_or_none.execute(
            "UPDATE users SET updated_at = %s, updated_by = %s WHERE id = %s",
            (params["at"], params["by"], params["id"]),
        )
    else:
        db.session.execute(text("UPDATE users SET updated_at = :at, updated_by = :by WHERE id = :id"), params)


def last_updated(user_id):
    """{"updated_at": ..., "updated_by": ...} for display; empty values when not recorded."""
    if not schema_check.has("users.updated_at"):
        return {"updated_at": None, "updated_by": None}
    row = db.session.execute(
        text("SELECT updated_at, updated_by FROM users WHERE id = :id"), {"id": user_id}
    ).first()
    return {"updated_at": _iso(row[0]) if row else None, "updated_by": row[1] if row else None}


def zone_for_pincode(pincode):
    row = db.session.execute(text("SELECT zone_code FROM zone WHERE pincode = :p"), {"p": pincode}).first()
    return row[0] if row else None


def _upcoming_bookings(user_id):
    today = now_ist().date()
    return [
        b.booking_date.isoformat()
        for b in Booking.query.filter(
            Booking.user_id == user_id, Booking.is_active == True, Booking.booking_date >= today
        ).order_by(Booking.booking_date).all()
    ]


def impact_of(user, changes):
    """What approving these changes would affect, in plain words for the admin."""
    notes = []
    new_zone = None
    if "pincode" in changes and changes["pincode"] != (user.pincode or ""):
        new_zone = zone_for_pincode(changes["pincode"])
        if new_zone and new_zone != user.zone_code:
            notes.append(
                f"Zone changes from {user.zone_code or '-'} to {new_zone}. Bookings already made stay "
                f"counted under Zone {user.zone_code or '-'}; new bookings follow Zone {new_zone}."
            )
    if ADDRESS_FIELDS & set(changes):
        upcoming = _upcoming_bookings(user.id)
        if upcoming:
            notes.append(
                f"Has upcoming Upasana on {', '.join(upcoming)}: the booking lists will show the new address."
            )
        notes.append("Map location will be found again from the new address.")
    return {"new_zone": new_zone, "notes": notes}


def apply_changes(user, changes, by_label):
    """Write approved changes to the member (zone follows the PIN code). Caller commits."""
    for field, value in changes.items():
        if field in MEMBER_FIELDS:
            setattr(user, field, value if value != "" else None)
    if "pincode" in changes:
        zone = zone_for_pincode(changes["pincode"])
        if zone:
            user.zone_code = zone
    if ADDRESS_FIELDS & set(changes):
        # The cached map location belongs to the old address
        user.latitude = None
        user.longitude = None
    db.session.flush()
    mark_updated(None, user.id, by_label)


def _clean_changes(user, raw):
    """Only allowed, actually-changed fields; returns (changes, error)."""
    if not isinstance(raw, dict):
        return None, "No changes sent."
    changes = {}
    for field, value in raw.items():
        if field not in MEMBER_FIELDS:
            continue
        value = "" if value is None else str(value).strip()
        if field in REQUIRED and not value:
            return None, f"{MEMBER_FIELDS[field]} cannot be empty."
        if value != (getattr(user, field) or ""):
            changes[field] = value
    if not changes:
        return None, "Nothing has changed."
    if "pincode" in changes:
        if not re.fullmatch(r"\d{6}", changes["pincode"]):
            return None, "PIN code must be 6 digits."
        if not zone_for_pincode(changes["pincode"]):
            return None, f"PIN code {changes['pincode']} is not in the zone list. Please contact the admin."
    if changes.get("alternate_mobile_number") and not re.fullmatch(r"\d{10}", changes["alternate_mobile_number"]):
        return None, "Alternate mobile must be 10 digits."
    if changes.get("gender") and changes["gender"] not in ("male", "female"):
        return None, "Gender must be male or female."
    if changes.get("anugrahit") and changes["anugrahit"] not in ("yes", "no"):
        return None, "Anugrahit must be yes or no."
    return changes, None


def _request_dict(row, user=None):
    rid, user_id, changes, status, created_at, decided_at, decided_by, note = row
    data = {
        "id": rid,
        "user_id": user_id,
        "changes": json.loads(changes),
        "status": status,
        "created_at": _iso(created_at),
        "decided_at": _iso(decided_at),
        "decided_by": decided_by,
        "admin_note": note,
    }
    if user is not None:
        data["user"] = {
            "name": _name(user),
            "mobile_number": user.mobile_number,
            "zone_code": user.zone_code or "",
            "current": {f: getattr(user, f) or "" for f in MEMBER_FIELDS},
        }
        data["impact"] = impact_of(user, data["changes"])
        data["labels"] = MEMBER_FIELDS
    return data


REQUEST_COLUMNS = "id, user_id, changes, status, created_at, decided_at, decided_by, admin_note"


@router.route("/users/<int:user_id>/change-request", methods=["GET"])
def my_change_request(user_id):
    if not schema_check.has("profile_change_requests.id"):
        return jsonify({"request": None, "enabled": False}), 200
    row = db.session.execute(
        text(f"SELECT {REQUEST_COLUMNS} FROM profile_change_requests WHERE user_id = :u ORDER BY id DESC LIMIT 1"),
        {"u": user_id},
    ).first()
    return jsonify({"request": _request_dict(row) if row else None, "enabled": True, "labels": MEMBER_FIELDS}), 200


@router.route("/users/<int:user_id>/change-request", methods=["POST"])
def submit_change_request(user_id):
    if not schema_check.has("profile_change_requests.id"):
        return jsonify({"error": "Profile changes are not available yet. Please contact your zone admin."}), 503
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Member not found."}), 404
    changes, error = _clean_changes(user, (request.get_json(silent=True) or {}).get("changes"))
    if error:
        return jsonify({"error": error}), 400
    try:
        # One pending request per member: a new one replaces the old
        db.session.execute(
            text("DELETE FROM profile_change_requests WHERE user_id = :u AND status = 'pending'"), {"u": user_id}
        )
        db.session.execute(
            text("INSERT INTO profile_change_requests (user_id, changes, status, created_at) "
                 "VALUES (:u, :c, 'pending', :t)"),
            {"u": user_id, "c": json.dumps(changes, ensure_ascii=False), "t": now_ist()},
        )
        db.session.commit()
        return jsonify({"message": "Sent to the admin for approval.", "changes": changes}), 201
    except Exception as e:
        db.session.rollback()
        logging.exception(f"submit_change_request failed: {e}")
        return jsonify({"error": "Could not send the change. Please try again."}), 500


@router.route("/admin/change-requests", methods=["GET"])
def pending_change_requests():
    err, status, _ = require_admin()
    if err:
        return err, status
    if not schema_check.has("profile_change_requests.id"):
        return jsonify({"requests": []}), 200
    rows = db.session.execute(
        text(f"SELECT {REQUEST_COLUMNS} FROM profile_change_requests WHERE status = 'pending' ORDER BY created_at")
    ).all()
    out = []
    for row in rows:
        user = User.query.get(row[1])
        if user:
            out.append(_request_dict(row, user))
    return jsonify({"requests": out}), 200


@router.route("/admin/change-requests/<int:request_id>/decide", methods=["POST"])
def decide_change_request(request_id):
    err, status, admin_label = require_admin()
    if err:
        return err, status
    data = request.get_json(silent=True) or {}
    approve = data.get("approve") is True
    note = (str(data.get("note") or "").strip())[:500] or None
    row = db.session.execute(
        text(f"SELECT {REQUEST_COLUMNS} FROM profile_change_requests WHERE id = :i FOR UPDATE"), {"i": request_id}
    ).first()
    if not row:
        return jsonify({"error": "Request not found."}), 404
    if row[3] != "pending":
        return jsonify({"error": f"This request was already {row[3]}."}), 409
    user = User.query.get(row[1])
    if not user:
        return jsonify({"error": "Member not found."}), 404

    by = actor_label(admin_label)
    try:
        if approve:
            changes, error = _clean_changes(user, json.loads(row[2]))
            if error and error != "Nothing has changed.":
                db.session.rollback()
                return jsonify({"error": f"Cannot approve: {error}"}), 400
            if changes:
                apply_changes(user, changes, f"{by} (approved member's request)")
        db.session.execute(
            text("UPDATE profile_change_requests SET status = :s, decided_at = :t, decided_by = :b, admin_note = :n "
                 "WHERE id = :i"),
            {"s": "approved" if approve else "rejected", "t": now_ist(), "b": by, "n": note, "i": request_id},
        )
        db.session.commit()
        if approve:
            from Booking import note_zone_change
            note_zone_change()          # a zone change can complete or reopen a zone
        return jsonify({"message": "Approved and applied." if approve else "Rejected."}), 200
    except Exception as e:
        db.session.rollback()
        logging.exception(f"decide_change_request failed: {e}")
        return jsonify({"error": "Could not save the decision. Please try again."}), 500
