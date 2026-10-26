"""
Google Maps link for an Upasana: on a booking (the host's place) or a common Upasana event.

There is ONE link per member home: users.map_link. The member saves it in Profile (no approval
needed); an admin changes the same link from the member's details or from Manage booking (it is
the host's link). Every booking of that member shows it: in the booking details, the share
message and Navigate / View address. Changing a booking's host shows the new host's link;
swapping dates keeps each host's link. bookings.map_link (links set per booking before) is only a
fallback until migrations/add_member_map_link.sql has copied them to the members.

Endpoints
─────────
  POST /users/<id>/map-link       { map_link, user_id }      the member themself, or an admin
  POST /admin/bookings/map-link   { booking_id, map_link }   admin: saves the HOST's link (same field)
Empty map_link removes it.
Events take `map_link` in POST/PUT /admin/upasana-events (admin_bookings.py).

Columns are added at start-up and by migrations/add_map_links.sql; without them the feature is
simply off (nothing is shown and saving says it is not available yet).
"""

import logging
import re
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from admin_auth import admin_required, current_admin
from model import db
import schema_check

router = Blueprint("booking_maps", __name__)

MAX_LEN = 500

SCHEMA = [
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS map_link VARCHAR(500)",
    "ALTER TABLE upasana_events ADD COLUMN IF NOT EXISTS map_link VARCHAR(500)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS map_link VARCHAR(500)",
]

# Google Maps addresses a shared link can have
_ALLOWED = re.compile(
    r"^(maps\.app\.goo\.gl|goo\.gl|maps\.google\.[a-z.]+|(www\.)?google\.[a-z.]+)$", re.I
)


def bookings_ready():
    return schema_check.has("bookings.map_link")


def events_ready():
    return schema_check.has("upasana_events.map_link")


def members_ready():
    return schema_check.has("users.map_link")


def member_link(user_id):
    """The member's own home link, or None."""
    if not members_ready():
        return None
    row = db.session.execute(text("SELECT map_link FROM users WHERE id = :i"), {"i": user_id}).first()
    return row[0] if row else None


def clean_map_link(value):
    """(link_or_None, error). Empty means 'remove'. Only Google Maps links are accepted."""
    link = str(value or "").strip()
    if not link:
        return None, None
    if len(link) > MAX_LEN:
        return None, "The map link is too long."
    if not re.match(r"^https?://", link, re.I):
        link = "https://" + link
    parsed = urlparse(link)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    is_maps = (
        host == "maps.app.goo.gl"
        or (host == "goo.gl" and path.startswith("/maps"))
        or host.startswith("maps.google.")
        or (_ALLOWED.match(host) and path.startswith("/maps"))
    )
    if not is_maps:
        return None, "Please paste a Google Maps link (maps.app.goo.gl/… or google.com/maps/…)."
    return link, None


def booking_links(booking_ids):
    """{booking_id: map_link} for these bookings (only those with a link): the host's home link;
    an older per-booking link only when the host has none yet."""
    ids = [int(i) for i in booking_ids if i is not None]
    if not ids or not (bookings_ready() or members_ready()):
        return {}
    own = "b.map_link" if bookings_ready() else "NULL"
    host = "u.map_link" if members_ready() else "NULL"
    rows = db.session.execute(
        text(f"SELECT b.id, COALESCE({host}, {own}) FROM bookings b JOIN users u ON u.id = b.user_id "
             f"WHERE b.id = ANY(:ids) AND COALESCE({host}, {own}) IS NOT NULL"),
        {"ids": ids},
    ).all()
    return {r[0]: r[1] for r in rows}


def event_link(event_id):
    if not events_ready():
        return None
    row = db.session.execute(text("SELECT map_link FROM upasana_events WHERE id = :i"), {"i": event_id}).first()
    return row[0] if row else None


def set_event_link(event_id, link):
    """Caller commits."""
    db.session.execute(text("UPDATE upasana_events SET map_link = :l WHERE id = :i"), {"l": link, "i": event_id})


def clear_booking_link(booking_id):
    """When a booking's host changes: drop an older per-booking link (the new host's link shows). Caller commits."""
    if bookings_ready():
        db.session.execute(text("UPDATE bookings SET map_link = NULL WHERE id = :i"), {"i": booking_id})


@router.route("/admin/bookings/map-link", methods=["POST"])
@admin_required
def set_booking_map_link():
    """Admin, from Manage booking: saves the HOST's home link (users.map_link, the same link the
    member sees in Profile) and drops any older link stored on this booking."""
    if not members_ready():
        return jsonify({"error": "Map links are not available yet (run migrations/add_member_map_link.sql)."}), 503
    data = request.get_json(silent=True) or {}
    try:
        booking_id = int(data.get("booking_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "booking_id is required."}), 400
    link, error = clean_map_link(data.get("map_link"))
    if error:
        return jsonify({"error": error}), 400
    try:
        row = db.session.execute(
            text("SELECT user_id FROM bookings WHERE id = :i AND is_active"), {"i": booking_id}
        ).first()
        if not row:
            return jsonify({"error": "Booking not found."}), 404
        db.session.execute(text("UPDATE users SET map_link = :l WHERE id = :u"), {"l": link, "u": row[0]})
        if bookings_ready():
            db.session.execute(text("UPDATE bookings SET map_link = NULL WHERE id = :i"), {"i": booking_id})
        db.session.commit()
        logging.info(f"Host map link {'set' if link else 'removed'} for user {row[0]} (booking {booking_id})")
        return jsonify({"message": "Map link saved." if link else "Map link removed.", "map_link": link,
                        "user_id": row[0]}), 200
    except Exception as e:
        db.session.rollback()
        logging.exception(f"set_booking_map_link failed: {e}")
        return jsonify({"error": "Could not save the map link."}), 500


@router.route("/users/<int:user_id>/map-link", methods=["POST"])
def set_member_map_link(user_id):
    """
    Google Maps link of a member's home. The member saves it from Profile without admin approval
    (body: { map_link, user_id } — user_id must be the member themself); an admin (session token)
    can save it for any member. Empty map_link removes it.
    """
    if not members_ready():
        return jsonify({"error": "Map links are not available yet (run migrations/add_member_map_link.sql)."}), 503
    data = request.get_json(silent=True) or {}
    admin = current_admin()
    if admin is None:
        try:
            acting = int(data.get("user_id"))
        except (TypeError, ValueError):
            acting = None
        if acting != user_id:
            return jsonify({"error": "You can only change the map link of your own home."}), 403
    link, error = clean_map_link(data.get("map_link"))
    if error:
        return jsonify({"error": error}), 400
    try:
        updated = db.session.execute(
            text("UPDATE users SET map_link = :l WHERE id = :i"), {"l": link, "i": user_id}
        ).rowcount
        if not updated:
            db.session.rollback()
            return jsonify({"error": "Member not found."}), 404
        db.session.commit()
        who = f"admin {admin.mobile_number}" if admin is not None else "member"
        logging.info(f"Member map link {'set' if link else 'removed'} for user {user_id} by {who}")
        return jsonify({"message": "Map link saved." if link else "Map link removed.", "map_link": link}), 200
    except Exception as e:
        db.session.rollback()
        logging.exception(f"set_member_map_link failed: {e}")
        return jsonify({"error": "Could not save the map link."}), 500

