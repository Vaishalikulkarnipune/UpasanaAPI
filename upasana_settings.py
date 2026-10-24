"""
Upasana booking settings and calendar availability.

Endpoints
─────────
  GET  /upasana-settings                 booking year, toggles, selectable years
  POST /upasana-settings                 admin: { booking_year?, enable_booking?, enable_zone_restriction?,
                                                  booking_opens_at?, trial_run?, trial_run_start?, trial_run_end?,
                                                  show_booking_stats?,
                                                  admin login token }
  GET  /booking-availability?user_id=X   per-month availability for the user's zone in the booking year
"""

import logging
import calendar
from datetime import date, datetime, timedelta
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


# Trial run: booking opened for practice before the real opening. Shown to members as
# "trial run, not real booking"; it does not change the booking rules.
# Active = switch on AND today (IST) inside the admin's date range (an empty range means any day).
# Bookings made while active are flagged bookings.is_trial so the admin can delete them by hand;
# the app itself never deletes them.
# Kept in reference_data (not feature_toggle): that table's id has no sequence here, so the
# app cannot create new toggle rows.
TRIAL_KEY = "trial_run"
TRIAL_DATE_KEYS = ("trial_run_start", "trial_run_end")


def _toggle(name):
    row = FeatureToggle.query.filter_by(toggle_name=name).first()
    return row.toggle_enabled if row else _TOGGLE_DEFAULTS[name]


def _reference(key):
    row = ReferenceData.query.filter_by(reference_key=key).first()
    return (row.reference_value or None) if row else None


def _set_reference(key, value):
    row = ReferenceData.query.filter_by(reference_key=key).first()
    if row:
        row.reference_value = value
    else:
        db.session.add(ReferenceData(reference_key=key, reference_value=value))


def get_trial_settings():
    switch_on = _reference(TRIAL_KEY) == "true"
    dates = {key: _reference(key) for key in TRIAL_DATE_KEYS}
    today = today_ist().strftime("%Y-%m-%d")
    in_range = (not dates["trial_run_start"] or today >= dates["trial_run_start"]) and (
        not dates["trial_run_end"] or today <= dates["trial_run_end"]
    )
    return {"trial_run": switch_on, "trial_active": switch_on and in_range, **dates}


def trial_is_active():
    return get_trial_settings()["trial_active"]


# When real booking opens (admin still flips "Booking Open" by hand; this is what members are told).
# Stored as IST "YYYY-MM-DDTHH:MM"; unset means the usual rule below.
OPENS_AT_KEY = "booking_opens_at"
OPENS_AT_FORMAT = "%Y-%m-%dT%H:%M"


def default_opens_at(booking_year):
    """First Sunday of the previous December, 12:00 noon IST."""
    first = date(booking_year - 1, 12, 1)
    sunday = first + timedelta(days=(calendar.SUNDAY - first.weekday()) % 7)
    return f"{sunday.strftime('%Y-%m-%d')}T12:00"


def get_opening_settings(booking_year):
    custom = _reference(OPENS_AT_KEY)
    default = default_opens_at(booking_year) if booking_year else None
    return {
        "booking_opens_at": custom or default,
        "booking_opens_at_default": default,
        "booking_opens_at_is_default": not custom,
    }


# Admin dashboard: show the "Zone booking status" card. Booking happens once a year, so the
# admin can hide it for the rest of the year. Shown unless switched off.
BOOKING_STATS_KEY = "show_booking_stats"


def _all_settings():
    booking = get_booking_settings()
    return {
        **booking,
        "show_booking_stats": _reference(BOOKING_STATS_KEY) != "false",
        # Admin switch; members can join only while booking is also open (see waitlist.py)
        "waitlist_open": _reference("waitlist_open") != "false",
        **get_opening_settings(booking["booking_year"]),
        **get_trial_settings(),
        "year_options": year_options(),
    }


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
        return jsonify(_all_settings()), 200
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
            if not row or row.reference_value != str(year):
                # A custom opening time belongs to the old year; the new year starts from the usual rule.
                _set_reference(OPENS_AT_KEY, "")
            if row:
                row.reference_value = str(year)
            else:
                db.session.add(ReferenceData(reference_key="booking_year", reference_value=str(year)))

        # "YYYY-MM-DDTHH:MM" in IST; an empty value goes back to the usual rule.
        if OPENS_AT_KEY in data:
            value = str(data[OPENS_AT_KEY] or "").strip()[:16]
            if value:
                try:
                    datetime.strptime(value, OPENS_AT_FORMAT)
                except ValueError:
                    db.session.rollback()
                    return jsonify({"error": "Booking opening must be a date and time (YYYY-MM-DDTHH:MM)."}), 400
            _set_reference(OPENS_AT_KEY, value)

        for name in _TOGGLE_DEFAULTS:
            if name in data:
                value = bool(data[name])
                row = FeatureToggle.query.filter_by(toggle_name=name).first()
                if row:
                    row.toggle_enabled = value
                else:
                    db.session.add(FeatureToggle(toggle_name=name, toggle_enabled=value))

        if "show_booking_stats" in data:
            _set_reference(BOOKING_STATS_KEY, "true" if bool(data["show_booking_stats"]) else "false")

        if "trial_run" in data:
            _set_reference(TRIAL_KEY, "true" if bool(data["trial_run"]) else "false")

        if "waitlist_open" in data:
            _set_reference("waitlist_open", "true" if bool(data["waitlist_open"]) else "false")

        # Dates are YYYY-MM-DD; an empty value clears the date.
        dates = {key: _reference(key) for key in TRIAL_DATE_KEYS}
        for key in TRIAL_DATE_KEYS:
            if key in data:
                value = str(data[key] or "").strip()
                if value:
                    try:
                        datetime.strptime(value, "%Y-%m-%d")
                    except ValueError:
                        db.session.rollback()
                        return jsonify({"error": "Trial run dates must be YYYY-MM-DD."}), 400
                dates[key] = value or None
                _set_reference(key, value)
        if dates["trial_run_start"] and dates["trial_run_end"] and dates["trial_run_start"] > dates["trial_run_end"]:
            db.session.rollback()
            return jsonify({"error": "Trial run end date must be on or after the start date."}), 400

        db.session.commit()
        return jsonify(_all_settings()), 200
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
        from waitlist import member_summary
        return jsonify({**result, "booking_open": settings["enable_booking"], "waitlist": member_summary(user)}), 200
    except Exception as e:
        logging.error(f"Error in availability: {e}")
        return jsonify({"error": "Failed to fetch availability"}), 500
