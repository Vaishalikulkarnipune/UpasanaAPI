"""
Google Maps link for an Upasana: on a booking (the host's place) or a common Upasana event.

Only an admin adds or changes it. Everyone sees it in the booking details and the share message,
and can open it to start navigation. Changing a booking's host clears its link (it points to the
old host's place); swapping dates keeps each host's link.

Endpoint
────────
  POST /admin/bookings/map-link   { booking_id, map_link }   admin; empty map_link removes it
Events take `map_link` in POST/PUT /admin/upasana-events (admin_bookings.py).

Columns are added at start-up and by migrations/add_map_links.sql; without them the feature is
simply off (nothing is shown and saving says it is not available yet).
"""

import logging
import re
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request
from sqlalchemy import text

from admin_auth import admin_required
from model import db
import schema_check

router = Blueprint("booking_maps", __name__)

MAX_LEN = 500

SCHEMA = [
    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS map_link VARCHAR(500)",
    "ALTER TABLE upasana_events ADD COLUMN IF NOT EXISTS map_link VARCHAR(500)",
]

# Google Maps addresses a shared link can have
_ALLOWED = re.compile(
    r"^(maps\.app\.goo\.gl|goo\.gl|maps\.google\.[a-z.]+|(www\.)?google\.[a-z.]+)$", re.I
)


def bookings_ready():
    return schema_check.has("bookings.map_link")


def events_ready():
    return schema_check.has("upasana_events.map_link")


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
    """{booking_id: map_link} for these bookings (only those with a link)."""
    ids = [int(i) for i in booking_ids if i is not None]
    if not ids or not bookings_ready():
        return {}
    rows = db.session.execute(
        text("SELECT id, map_link FROM bookings WHERE id = ANY(:ids) AND map_link IS NOT NULL"),
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
    """When a booking's host changes. Caller commits."""
    if bookings_ready():
        db.session.execute(text("UPDATE bookings SET map_link = NULL WHERE id = :i"), {"i": booking_id})


@router.route("/admin/bookings/map-link", methods=["POST"])
@admin_required
def set_booking_map_link():
    if not bookings_ready():
        return jsonify({"error": "Map links are not available yet (run migrations/add_map_links.sql)."}), 503
    data = request.get_json(silent=True) or {}
    try:
        booking_id = int(data.get("booking_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "booking_id is required."}), 400
    link, error = clean_map_link(data.get("map_link"))
    if error:
        return jsonify({"error": error}), 400
    try:
        updated = db.session.execute(
            text("UPDATE bookings SET map_link = :l WHERE id = :i AND is_active"), {"l": link, "i": booking_id}
        ).rowcount
        if not updated:
            db.session.rollback()
            return jsonify({"error": "Booking not found."}), 404
        db.session.commit()
        logging.info(f"Map link {'set' if link else 'removed'} for booking {booking_id}")
        return jsonify({"message": "Map link saved." if link else "Map link removed.", "map_link": link}), 200
    except Exception as e:
        db.session.rollback()
        logging.exception(f"set_booking_map_link failed: {e}")
        return jsonify({"error": "Could not save the map link."}), 500
