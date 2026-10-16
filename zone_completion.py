"""
When each zone's Upasana bookings for the booking year were completed.

A zone is complete when it has no month left in which a member of that zone could still
book. The moment that first becomes true is stamped in reference_data
(zone_complete_at_<year>_<zone>, UTC) so the admin can share it with the community; if a
cancellation frees a date for the zone again, the stamp is cleared and set afresh later.
Trial-run bookings are never stamped.

Endpoint
────────
  GET /admin/zone-completion    per-zone status for the booking year (admin_mobile | admin_user_id)
"""

import logging
from datetime import datetime
from flask import Blueprint, jsonify

from model import db
from admin_auth import require_admin
from Booking import ZONE_LIMITS, ZONE_NAMES, year_zone_overview

router = Blueprint("zone_completion", __name__)


def _key(year, zone):
    return f"zone_complete_at_{year}_{zone}"


def record_zone_completion():
    """Call after any change to bookings, events or blocked dates. Never raises."""
    try:
        from upasana_settings import get_booking_settings, trial_is_active, _reference, _set_reference

        if trial_is_active():
            return
        settings = get_booking_settings()
        year = settings["booking_year"]
        if not year:
            return
        open_months = year_zone_overview(year, settings["enable_zone_restriction"])["open_months"]
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        changed = False
        for zone in ZONE_LIMITS:
            stamped = _reference(_key(year, zone))
            complete = not open_months[zone]
            if complete and not stamped:
                _set_reference(_key(year, zone), now)
                changed = True
            elif not complete and stamped:
                _set_reference(_key(year, zone), "")
                changed = True
        if changed:
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Could not record zone completion: {e}")


@router.route("/admin/zone-completion", methods=["GET"])
def zone_completion():
    err, status, _ = require_admin()
    if err:
        return err, status
    try:
        from upasana_settings import get_booking_settings, trial_is_active, _reference

        settings = get_booking_settings()
        year = settings["booking_year"]
        if not year:
            return jsonify({"error": "Booking year configuration is missing."}), 500

        overview = year_zone_overview(year, settings["enable_zone_restriction"])
        zones = []
        for zone in ZONE_LIMITS:
            open_months = overview["open_months"][zone]
            zones.append({
                "zone": zone,
                "name": ZONE_NAMES[zone],
                "bookings": overview["booking_counts"][zone],
                "complete": not open_months,
                "open_months": open_months,
                "completed_at": _reference(_key(year, zone)) if not open_months else None,
            })
        all_complete = all(z["complete"] for z in zones)
        stamps = [z["completed_at"] for z in zones if z["completed_at"]]
        return jsonify({
            "year": year,
            "zones": zones,
            "total_bookings": sum(z["bookings"] for z in zones),
            "all_complete": all_complete,
            "all_completed_at": max(stamps) if all_complete and len(stamps) == len(zones) else None,
            "trial_active": trial_is_active(),
        }), 200
    except Exception as e:
        logging.error(f"Error in zone_completion: {e}")
        return jsonify({"error": "Failed to fetch zone status"}), 500
