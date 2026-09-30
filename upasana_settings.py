"""
Upasana booking settings and calendar availability.

Endpoints
─────────
  GET  /upasana-settings                 booking year, toggles, selectable years
  POST /upasana-settings                 admin: { booking_year?, enable_booking?, enable_zone_restriction?,
                                                  admin_mobile | admin_user_id }
  GET  /booking-availability?user_id=X   per-month availability for the user's zone in the booking year
"""

import logging
from flask import Blueprint, request, jsonify

from model import db, FeatureToggle, ReferenceData, User
from admin_auth import require_admin
from Booking import booking_availability, today_ist

router = Blueprint("upasana_settings", __name__)

YEARS_AHEAD = 10

# toggle name -> default when the row is missing
_TOGGLE_DEFAULTS = {
    "enable_booking": False,
    "enable_zone_restriction": True,
}


def _toggle(name):
    row = FeatureToggle.query.filter_by(toggle_name=name).first()
    return row.toggle_enabled if row else _TOGGLE_DEFAULTS[name]


def year_options():
    this_year = today_ist().year
    return list(range(this_year, this_year + YEARS_AHEAD + 1))


def get_booking_settings():
    row = ReferenceData.query.filter_by(reference_key="booking_year").first()
    try:
        booking_year = int(row.reference_value) if row else None
    except (TypeError, ValueError):
        booking_year = None
    return {
        "booking_year": booking_year,
        "enable_booking": _toggle("enable_booking"),
        "enable_zone_restriction": _toggle("enable_zone_restriction"),
    }


@router.route("/upasana-settings", methods=["GET"])
def read_settings():
    try:
        return jsonify({**get_booking_settings(), "year_options": year_options()}), 200
    except Exception as e:
        logging.error(f"Error in read_settings: {e}")
        return jsonify({"error": "Failed to fetch Upasana settings"}), 500


@router.route("/upasana-settings", methods=["POST"])
def update_settings():
    err, status, _ = require_admin()
    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    try:
        if "booking_year" in data:
            try:
                year = int(data["booking_year"])
            except (TypeError, ValueError):
                return jsonify({"error": "booking_year must be a number."}), 400
            options = year_options()
            if year not in options:
                return jsonify({"error": f"booking_year must be between {options[0]} and {options[-1]}."}), 400
            row = ReferenceData.query.filter_by(reference_key="booking_year").first()
            if row:
                row.reference_value = str(year)
            else:
                db.session.add(ReferenceData(reference_key="booking_year", reference_value=str(year)))

        for name in _TOGGLE_DEFAULTS:
            if name in data:
                value = bool(data[name])
                row = FeatureToggle.query.filter_by(toggle_name=name).first()
                if row:
                    row.toggle_enabled = value
                else:
                    db.session.add(FeatureToggle(toggle_name=name, toggle_enabled=value))

        db.session.commit()
        return jsonify({**get_booking_settings(), "year_options": year_options()}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in update_settings: {e}")
        return jsonify({"error": "Failed to update Upasana settings"}), 500


@router.route("/booking-availability", methods=["GET"])
def availability():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    try:
        settings = get_booking_settings()
        year = settings["booking_year"]
        if not year:
            return jsonify({"error": "Booking year configuration is missing."}), 500
        result = booking_availability(user, year, settings["enable_zone_restriction"])
        return jsonify({**result, "booking_open": settings["enable_booking"]}), 200
    except Exception as e:
        logging.error(f"Error in availability: {e}")
        return jsonify({"error": "Failed to fetch availability"}), 500
