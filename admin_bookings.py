"""
Admin Upasana bookings: on behalf of a member, or a common event not tied to a member.
Admin bookings can be on any date and skip the member rules; a date still holds only
one Upasana (member booking or event).

Endpoints (all take admin_mobile | admin_user_id)
─────────
  GET  /admin/members/lookup?mobile=XXXXXXXXXX   member details + their active bookings
  POST /admin/book                               { user_id, booking_date, mahaprasad }
  POST /admin/upasana-events                     { event_date, title, host_name?, contact_number?,
                                                   address?, note?, mahaprasad? }
  PUT  /admin/upasana-events/<id>                any of the above fields, or { is_active: false } to cancel
"""

import logging
import re
from datetime import datetime
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import OperationalError

from model import db, Booking, User, UpasanaEvent
from admin_auth import require_admin
from Booking import admin_create_booking, lock_month, is_date_taken, SLOT_TAKEN_MSG

router = Blueprint("admin_bookings", __name__)

EVENT_TEXT_FIELDS = {"title": 200, "host_name": 150, "contact_number": 20, "address": 1000, "note": 1000}


def _parse_date(value):
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def event_to_dict(e):
    return {
        "event_id": e.id,
        "event_date": e.event_date.strftime("%Y-%m-%d"),
        "title": e.title,
        "host_name": e.host_name or "",
        "contact_number": e.contact_number or "",
        "address": e.address or "",
        "note": e.note or "",
        "mahaprasad": bool(e.mahaprasad),
        "is_active": bool(e.is_active),
    }


@router.route("/admin/members/lookup", methods=["GET"])
def lookup_member():
    err, status, _ = require_admin()
    if err:
        return err, status

    digits = re.sub(r"\D", "", request.args.get("mobile", ""))[-10:]
    if len(digits) != 10:
        return jsonify({"error": "Enter a 10-digit mobile number."}), 400

    user = User.query.filter(
        (User.mobile_number == digits) | (User.alternate_mobile_number == digits)
    ).first()
    if not user:
        return jsonify({"error": "No member is registered with this mobile number."}), 404

    bookings = (
        Booking.query.filter(Booking.user_id == user.id, Booking.is_active == True)
        .order_by(Booking.booking_date)
        .all()
    )
    return jsonify({
        "user": {
            "id": user.id,
            "name": " ".join(p for p in [user.first_name, user.middle_name, user.last_name] if p),
            "mobile_number": user.mobile_number,
            "alternate_mobile_number": user.alternate_mobile_number or "",
            "flat_no": user.flat_no or "",
            "full_address": user.full_address or "",
            "area": user.area or "",
            "landmark": user.landmark or "",
            "city": user.city or "",
            "pincode": user.pincode or "",
            "zone_code": user.zone_code or "",
        },
        "bookings": [
            {"booking_id": b.id, "booking_date": b.booking_date.strftime("%Y-%m-%d"), "booked_by_admin": bool(b.booked_by_admin)}
            for b in bookings
        ],
    }), 200


@router.route("/admin/book", methods=["POST"])
def admin_book():
    err, status, admin_label = require_admin()
    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Member is required."}), 400
    if not data.get("booking_date"):
        return jsonify({"error": "Booking date is required."}), 400
    return admin_create_booking(user_id, data["booking_date"], data.get("mahaprasad", False), admin_label)


def _event_fields(data, partial):
    """Validated column values from the request body, or (None, error message)."""
    values = {}
    for field, limit in EVENT_TEXT_FIELDS.items():
        if field in data:
            values[field] = (str(data.get(field) or "").strip())[:limit] or None
    if "mahaprasad" in data:
        values["mahaprasad"] = bool(data.get("mahaprasad"))
    if "event_date" in data or not partial:
        event_date = _parse_date(data.get("event_date"))
        if not event_date:
            return None, "Event date is required (YYYY-MM-DD)."
        values["event_date"] = event_date
    if ("title" in values or not partial) and not values.get("title"):
        return None, "Event title is required."
    return values, None


@router.route("/admin/upasana-events", methods=["POST"])
def create_event():
    err, status, admin_label = require_admin()
    if err:
        return err, status

    values, error = _event_fields(request.get_json(silent=True) or {}, partial=False)
    if error:
        return jsonify({"error": error}), 400

    try:
        lock_month(values["event_date"].year, values["event_date"].month)
        if is_date_taken(values["event_date"]):
            db.session.rollback()
            return jsonify({"error": SLOT_TAKEN_MSG}), 409
        event = UpasanaEvent(**values, is_active=True, created_by=admin_label)
        db.session.add(event)
        db.session.commit()
        logging.info(f"Admin {admin_label} created event {event.id} on {event.event_date}")
        return jsonify({"message": "Event added.", "event": event_to_dict(event)}), 201
    except OperationalError:
        db.session.rollback()
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error creating event: {e}")
        return jsonify({"error": "Failed to add event."}), 500


@router.route("/admin/upasana-events/<int:event_id>", methods=["PUT"])
def update_event(event_id):
    err, status, admin_label = require_admin()
    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    values, error = _event_fields(data, partial=True)
    if error:
        return jsonify({"error": error}), 400

    event = UpasanaEvent.query.get(event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404

    try:
        if data.get("is_active") is False:
            event.is_active = False
            db.session.commit()
            logging.info(f"Admin {admin_label} cancelled event {event_id}")
            return jsonify({"message": "Event cancelled."}), 200

        new_date = values.get("event_date", event.event_date)
        if new_date != event.event_date or not event.is_active:
            # Lock both months so a booking can't take either date mid-move.
            for year, month in sorted({(new_date.year, new_date.month), (event.event_date.year, event.event_date.month)}):
                lock_month(year, month)
            event.is_active = False
            db.session.flush()
            if is_date_taken(new_date):
                db.session.rollback()
                return jsonify({"error": SLOT_TAKEN_MSG}), 409

        for field, value in values.items():
            setattr(event, field, value)
        event.is_active = True
        db.session.commit()
        logging.info(f"Admin {admin_label} updated event {event_id}")
        return jsonify({"message": "Event updated.", "event": event_to_dict(event)}), 200
    except OperationalError:
        db.session.rollback()
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error updating event {event_id}: {e}")
        return jsonify({"error": "Failed to update event."}), 500
