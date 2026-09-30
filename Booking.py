from datetime import datetime, timedelta, date
from flask import jsonify
from model import db, Booking, User, BlockedDate, SundayBooking
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, OperationalError
import calendar
import logging


IST_OFFSET = timedelta(hours=5, minutes=30)

ZONE_LIMITS = {"A": 1, "B": 2, "C": 2}
ZONE_NAMES = {
    "A": "Zone A (East Pune)",
    "B": "Zone B (Rest of Pune)",
    "C": "Zone C (PCMC)",
}

# Namespaces for pg_advisory_xact_lock(int, int)
USER_LOCK_NS = 1001
MONTH_LOCK_NS = 1002

SLOT_TAKEN_MSG = "This Saturday is no longer available. Please select another date."


def today_ist():
    return (datetime.utcnow() + IST_OFFSET).date()


def month_bounds(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def saturdays_in_month(year, month):
    return [
        date(year, month, week[calendar.SATURDAY])
        for week in calendar.monthcalendar(year, month)
        if week[calendar.SATURDAY] != 0
    ]


# =======================================================
# 🔒 Locks (released automatically on commit / rollback)
# =======================================================
def lock_month(year, month):
    db.session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :key)"),
        {"ns": MONTH_LOCK_NS, "key": year * 100 + month},
    )


def lock_user_and_month(user_id, booking_date):
    """Always user first, then month, so concurrent requests can't deadlock."""
    db.session.execute(text("SET LOCAL lock_timeout = '15s'"))
    db.session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :key)"),
        {"ns": USER_LOCK_NS, "key": int(user_id)},
    )
    lock_month(booking_date.year, booking_date.month)


# =======================================================
# 🧩 Monthly counters
# =======================================================
def monthly_zone_counts(year, month):
    start, end = month_bounds(year, month)
    rows = (
        db.session.query(User.zone_code, func.count(Booking.id))
        .join(User, User.id == Booking.user_id)
        .filter(Booking.booking_date >= start, Booking.booking_date <= end, Booking.is_active == True)
        .group_by(User.zone_code)
        .all()
    )
    return {zone: count for zone, count in rows}


def open_saturdays_in_month(year, month):
    """Saturdays still bookable: not in the past, not blocked, not already booked."""
    today = today_ist()
    candidates = [d for d in saturdays_in_month(year, month) if d >= today]
    if not candidates:
        return 0
    blocked = {
        b.blocked_date
        for b in BlockedDate.query.filter(BlockedDate.blocked_date.in_(candidates)).all()
    }
    booked = {
        b.booking_date
        for b in Booking.query.filter(Booking.booking_date.in_(candidates), Booking.is_active == True).all()
    }
    return sum(1 for d in candidates if d not in blocked and d not in booked)


def zone_rule_error(zone_code, year, month):
    """Monthly zone allocation check. Returns an error message or None."""
    if zone_code not in ZONE_LIMITS:
        return "Your zone is not set up for Upasana booking. Please contact the admin to update your pincode/zone."

    counts = monthly_zone_counts(year, month)
    zone_name = ZONE_NAMES[zone_code]
    full_msg = f"{zone_name} is full for this month. Please try another month."

    if counts.get(zone_code, 0) >= ZONE_LIMITS[zone_code]:
        return full_msg

    # The last open Saturday of a month is held for Zone A until Zone A has its booking
    if zone_code != "A" and counts.get("A", 0) == 0 and open_saturdays_in_month(year, month) <= 1:
        return full_msg

    return None


def active_booking_in_year(user_id, year):
    start, end = date(year, 1, 1), date(year, 12, 31)
    saturday = Booking.query.filter(
        Booking.user_id == user_id,
        Booking.booking_date >= start,
        Booking.booking_date <= end,
        Booking.is_active == True,
    ).first()
    if saturday:
        return saturday.booking_date
    sunday = SundayBooking.query.filter(
        SundayBooking.user_id == user_id,
        SundayBooking.booking_date >= start,
        SundayBooking.booking_date <= end,
        SundayBooking.is_active == True,
    ).first()
    return sunday.booking_date if sunday else None


def check_booking_rules(user, booking_date, enable_zone_restriction):
    """
    Every rule a booking must pass. Call while holding lock_user_and_month().
    Returns (message, status_code) when not allowed, else None.
    """
    blocked = BlockedDate.query.filter_by(blocked_date=booking_date).first()
    if blocked:
        message = "This Saturday is not available for Upasana booking."
        if blocked.reason:
            message = f"{message} ({blocked.reason})"
        return message, 400

    taken = Booking.query.filter(
        Booking.booking_date == booking_date, Booking.is_active == True
    ).first()
    if taken:
        return SLOT_TAKEN_MSG, 409

    if active_booking_in_year(user.id, booking_date.year):
        return "You have already made one booking for this year.", 400

    if enable_zone_restriction:
        error = zone_rule_error(user.zone_code, booking_date.year, booking_date.month)
        if error:
            return error, 400

    return None


def _parse_date(booking_date):
    if isinstance(booking_date, date) and not isinstance(booking_date, datetime):
        return booking_date
    if isinstance(booking_date, datetime):
        return booking_date.date()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(booking_date, fmt).date()
        except (TypeError, ValueError):
            continue
    return None


# =======================================================
# 🧱 Main Booking Function
# =======================================================
def create_booking(user_id, booking_date, mahaprasad=False, enable_zone_restriction=True):
    """Creates a booking after validating every rule while holding the user and month locks."""
    booking_date = _parse_date(booking_date)
    if not booking_date:
        return jsonify({"error": "Invalid date format. Use 'YYYY-MM-DD'."}), 400

    if booking_date.weekday() != 5:
        return jsonify({"error": "You can only book on Saturdays."}), 400

    if booking_date < today_ist():
        return jsonify({"error": "Past dates cannot be booked."}), 400

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"error": "User not found."}), 404

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    if user.is_quick_registered:
        return jsonify({"error": "Please complete your profile before booking Upasana."}), 400

    # A cancelled date can't be rebooked by the same user (unique user_id + booking_date)
    cancelled = Booking.query.filter_by(user_id=user_id, booking_date=booking_date, is_active=False).first()
    if cancelled:
        return jsonify({"error": "Cancelled dates cannot be rebooked."}), 400

    try:
        lock_user_and_month(user_id, booking_date)

        rule_error = check_booking_rules(user, booking_date, enable_zone_restriction)
        if rule_error:
            db.session.rollback()
            message, status = rule_error
            logging.info(f"Booking rejected user={user_id} date={booking_date}: {message}")
            return jsonify({"error": message}), status

        now = datetime.utcnow()
        db.session.add(Booking(
            user_id=user_id,
            booking_date=booking_date,
            mahaprasad=bool(mahaprasad),
            created_at=now,
            updated_date=now,
            updated_by=user_id,
            is_active=True,
        ))
        db.session.commit()
        logging.info(f"Booking successful user={user_id} date={booking_date}")
        return jsonify({"message": "Booking successful.", "booking_date": str(booking_date)}), 201

    except IntegrityError as e:
        db.session.rollback()
        logging.warning(f"Booking integrity conflict user={user_id} date={booking_date}: {e}")
        return jsonify({"error": SLOT_TAKEN_MSG}), 409
    except OperationalError as e:
        db.session.rollback()
        logging.warning(f"Booking operational error user={user_id} date={booking_date}: {e}")
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Unexpected booking error user={user_id} date={booking_date}: {e}")
        return jsonify({"error": "Unexpected error during booking."}), 500


# =======================================================
# ♻️ Reactivate a cancelled booking
# =======================================================
def reactivate_booking(booking_id, user_id, enable_zone_restriction=True):
    """Re-validates every rule before turning a cancelled booking back on."""
    booking = Booking.query.filter_by(id=booking_id, user_id=user_id).first()
    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    if booking.is_active:
        return jsonify({"message": "Booking is already active."}), 200

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    try:
        lock_user_and_month(user_id, booking.booking_date)

        rule_error = check_booking_rules(user, booking.booking_date, enable_zone_restriction)
        if rule_error:
            db.session.rollback()
            message, status = rule_error
            return jsonify({"error": f"Cannot reactivate: {message}"}), status

        booking.is_active = True
        booking.updated_date = datetime.utcnow()
        db.session.commit()
        return jsonify({"message": "Booking activated successfully"}), 200

    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": f"Cannot reactivate: {SLOT_TAKEN_MSG}"}), 409
    except OperationalError:
        db.session.rollback()
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Unexpected reactivation error booking={booking_id}: {e}")
        return jsonify({"error": "Unexpected error while reactivating booking."}), 500


# =======================================================
# 📅 Per-month availability for the booking calendar
# =======================================================
def booking_availability(user, year, enable_zone_restriction=True):
    """Read-only preview of which months the user can book in (final check happens at booking)."""
    existing = active_booking_in_year(user.id, year)
    today = today_ist()
    months = {}
    for month in range(1, 13):
        _, month_end = month_bounds(year, month)
        if month_end < today:
            months[month] = {"available": False, "reason": "This month has passed."}
            continue
        reason = zone_rule_error(user.zone_code, year, month) if enable_zone_restriction else None
        if not reason and open_saturdays_in_month(year, month) == 0:
            reason = "No Saturdays are available in this month."
        months[month] = {"available": reason is None, "reason": reason}
    return {
        "year": year,
        "zone_code": user.zone_code,
        "zone_name": ZONE_NAMES.get(user.zone_code, user.zone_code),
        "already_booked_date": existing.strftime("%Y-%m-%d") if existing else None,
        "months": months,
    }
