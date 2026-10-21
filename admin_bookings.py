"""
Admin Upasana bookings: on behalf of a member, or a common event not tied to a member.
Admin bookings can be on any date and skip the member rules; a date still holds only
one Upasana (member booking or event).

Endpoints (all need the admin login token: Authorization: Bearer <token>)
─────────
  GET  /admin/members/lookup?mobile=XXXXXXXXXX   member details + their active bookings
  POST /admin/book                               { user_id, booking_date, mahaprasad }
  POST /admin/upasana-events                     { event_date, title, host_name?, contact_number?,
                                                   address?, note?, mahaprasad? }
  PUT  /admin/upasana-events/<id>                any of the above fields, or { is_active: false } to cancel
  POST /admin/bookings/check                     member rules an admin action would bypass (warnings only)
"""

import logging
import re
from datetime import datetime
from flask import Blueprint, request, jsonify
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from model import db, Booking, User, UpasanaEvent
from admin_auth import require_admin
from upasana_settings import trial_is_active
from Booking import (
    admin_create_booking,
    set_host_snapshot,
    note_zone_change,
    admin_override_warnings,
    active_booking_in_year,
    lock_month,
    lock_user_and_month,
    USER_LOCK_NS,
    is_date_taken,
    today_ist,
    SLOT_TAKEN_MSG,
)

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
    return admin_create_booking(
        user_id, data["booking_date"], data.get("mahaprasad", False), admin_label, is_trial=trial_is_active()
    )


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
        note_zone_change()
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
            note_zone_change()
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
        note_zone_change()
        logging.info(f"Admin {admin_label} updated event {event_id}")
        return jsonify({"message": "Event updated.", "event": event_to_dict(event)}), 200
    except OperationalError:
        db.session.rollback()
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error updating event {event_id}: {e}")
        return jsonify({"error": "Failed to update event."}), 500


@router.route("/admin/bookings/check", methods=["POST"])
def check_admin_action():
    """
    Member rules an admin action would bypass, shown before the admin confirms.
    Never blocks: the admin may always go ahead.
      { action: "book", user_id, booking_date }
      { action: "reassign", booking_id, user_id }
      { action: "swap", booking_id, other_booking_id }
    """
    err, status, _ = require_admin()
    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    action = data.get("action")
    warnings = []
    try:
        if action == "book":
            user = User.query.get(int(data.get("user_id")))
            booking_date = _parse_date(data.get("booking_date"))
            if user and booking_date:
                warnings = admin_override_warnings(user, booking_date)

        elif action == "reassign":
            booking = Booking.query.get(int(data.get("booking_id")))
            user = User.query.get(int(data.get("user_id")))
            if booking and user:
                existing = active_booking_in_year(user.id, booking.booking_date.year)
                if existing:
                    warnings.append(
                        f"{_host_name(user)} already has an Upasana on {existing.strftime('%d %B %Y')} this year."
                    )
                warnings += admin_override_warnings(
                    user, booking.booking_date, exclude_ids=[booking.id], check_reserved=False
                )

        elif action == "swap":
            first = Booking.query.get(int(data.get("booking_id")))
            second = Booking.query.get(int(data.get("other_booking_id")))
            if first and second:
                moved = [first.id, second.id]
                for booking, new_date in ((first, second.booking_date), (second, first.booking_date)):
                    user = User.query.get(booking.user_id)
                    same_month = (new_date.year, new_date.month) == (booking.booking_date.year, booking.booking_date.month)
                    if not user or same_month:
                        continue
                    for text_ in admin_override_warnings(user, new_date, exclude_ids=moved, check_reserved=False):
                        warnings.append(f"{_host_name(user)}: {text_}")
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid request."}), 400
    except Exception as e:
        logging.exception(f"Error checking admin action: {e}")
        return jsonify({"error": "Could not check the booking rules."}), 500

    return jsonify({"warnings": warnings}), 200


def _upcoming_booking(booking_id):
    """Active booking on today or later, or (None, error message)."""
    try:
        booking_id = int(booking_id)
    except (TypeError, ValueError):
        return None, "Booking is required."
    booking = Booking.query.get(booking_id)
    if not booking or not booking.is_active:
        return None, "Booking not found."
    if booking.booking_date < today_ist():
        return None, "Only an upcoming Upasana can be changed."
    return booking, None


def _drop_cancelled_row(user_id, booking_date):
    """A cancelled row on the same member and date would block the unique pair."""
    stale = Booking.query.filter_by(user_id=user_id, booking_date=booking_date, is_active=False).first()
    if stale:
        db.session.delete(stale)
        db.session.flush()


def _lock_users_then_months(user_ids, dates):
    """Users in id order, then months, so two admin edits cannot deadlock."""
    db.session.execute(text("SET LOCAL lock_timeout = '15s'"))
    for user_id in sorted({int(uid) for uid in user_ids}):
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:ns, :key)"),
            {"ns": USER_LOCK_NS, "key": user_id},
        )
    for year, month in sorted({(d.year, d.month) for d in dates}):
        lock_month(year, month)


def _host_name(user):
    return " ".join(p for p in [user.first_name, user.middle_name, user.last_name] if p)


@router.route("/admin/bookings/swap", methods=["POST"])
def swap_bookings():
    """Exchange the dates of two upcoming member bookings."""
    err, status, admin_label = require_admin()
    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    first, error = _upcoming_booking(data.get("booking_id"))
    if error:
        return jsonify({"error": error}), 400
    second, error = _upcoming_booking(data.get("other_booking_id"))
    if error:
        return jsonify({"error": error}), 400
    if first.id == second.id:
        return jsonify({"error": "Choose two different bookings."}), 400

    date_a, date_b = first.booking_date, second.booking_date
    try:
        _lock_users_then_months([first.user_id, second.user_id], [date_a, date_b])

        first.is_active = False
        second.is_active = False
        db.session.flush()
        _drop_cancelled_row(first.user_id, date_b)
        _drop_cancelled_row(second.user_id, date_a)

        now = datetime.utcnow()
        first.booking_date = date_b
        second.booking_date = date_a
        first.is_active = True
        second.is_active = True
        first.updated_date = now
        second.updated_date = now
        first.updated_by = None
        db.session.commit()
        note_zone_change()
        logging.info(f"Admin {admin_label} swapped bookings {first.id} and {second.id}")
        return jsonify({
            "message": "Dates swapped.",
            "bookings": [
                {"booking_id": first.id, "booking_date": date_b.strftime("%Y-%m-%d"), "user_id": first.user_id},
                {"booking_id": second.id, "booking_date": date_a.strftime("%Y-%m-%d"), "user_id": second.user_id},
            ],
        }), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "These dates could not be swapped. Refresh and try again."}), 409
    except OperationalError:
        db.session.rollback()
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error swapping bookings: {e}")
        return jsonify({"error": "Failed to swap bookings."}), 500


@router.route("/admin/bookings/reassign", methods=["POST"])
def reassign_booking():
    """Give an upcoming booking to another member. The date stays; host details follow the new member."""
    err, status, admin_label = require_admin()
    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    booking, error = _upcoming_booking(data.get("booking_id"))
    if error:
        return jsonify({"error": error}), 400
    try:
        new_user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Choose the new host."}), 400

    new_user = User.query.get(new_user_id)
    if not new_user:
        return jsonify({"error": "Member not found."}), 404
    if new_user.id == booking.user_id:
        return jsonify({"error": "This member is already the host."}), 400

    try:
        _lock_users_then_months([booking.user_id, new_user.id], [booking.booking_date])
        _drop_cancelled_row(new_user.id, booking.booking_date)
        booking.user_id = new_user.id
        set_host_snapshot(booking, new_user)       # the new host's zone and area
        booking.booked_by_admin = True
        booking.updated_date = datetime.utcnow()
        db.session.commit()
        note_zone_change()
        logging.info(f"Admin {admin_label} reassigned booking {booking.id} to user {new_user.id}")
        return jsonify({
            "message": "Host updated.",
            "booking_id": booking.id,
            "user_id": new_user.id,
            "host_name": _host_name(new_user),
            "booking_date": booking.booking_date.strftime("%Y-%m-%d"),
        }), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "This member cannot take this date. Refresh and try again."}), 409
    except OperationalError:
        db.session.rollback()
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error reassigning booking: {e}")
        return jsonify({"error": "Failed to change the host."}), 500


@router.route("/admin/bookings/cancel", methods=["POST"])
def cancel_booking():
    """Free an upcoming date. Another host can be added later."""
    err, status, admin_label = require_admin()
    if err:
        return err, status

    booking, error = _upcoming_booking((request.get_json(silent=True) or {}).get("booking_id"))
    if error:
        return jsonify({"error": error}), 400

    try:
        lock_user_and_month(booking.user_id, booking.booking_date)
        booking.is_active = False
        booking.updated_date = datetime.utcnow()
        db.session.commit()
        note_zone_change()
        logging.info(f"Admin {admin_label} cancelled booking {booking.id}")
        return jsonify({
            "message": "Booking cancelled. The date is free for another host.",
            "booking_date": booking.booking_date.strftime("%Y-%m-%d"),
        }), 200
    except OperationalError:
        db.session.rollback()
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Error cancelling booking: {e}")
        return jsonify({"error": "Failed to cancel the booking."}), 500
