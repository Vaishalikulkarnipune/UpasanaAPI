from datetime import datetime, timedelta, date
from flask import jsonify
from model import db, Booking, User, BlockedDate, SundayBooking, UpasanaEvent
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, OperationalError
import schema_check
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

SLOT_TAKEN_MSG = "This date is no longer available. Please select another date."

def booking_zone():
    """The zone a booking counts for: the one saved on it, else (older rows) the member's profile."""
    if schema_check.has("bookings.zone_code"):
        return func.coalesce(Booking.zone_code, User.zone_code)
    return User.zone_code


def host_snapshot(user):
    """Zone and area to save on a booking for this host (nothing when the columns don't exist)."""
    if not schema_check.has("bookings.zone_code"):
        return {}
    return {"zone_code": user.zone_code, "host_area": ((user.area or "").strip() or None)}


def set_host_snapshot(booking, user):
    for field, value in host_snapshot(user).items():
        setattr(booking, field, value)


FREEZE_SNAPSHOT_SQL = """
    UPDATE bookings b
       SET zone_code = COALESCE(b.zone_code, u.zone_code),
           host_area = COALESCE(b.host_area, NULLIF(TRIM(u.area), ''))
      FROM users u
     WHERE u.id = b.user_id AND b.user_id = {param}
       AND (b.zone_code IS NULL OR b.host_area IS NULL)
"""


def freeze_host_snapshot(cursor_or_none, user_id):
    """
    Call BEFORE a member's PIN/zone or address changes: bookings that have no saved zone or area
    (made before the columns existed, or imported) get the member's current ones written in, so
    the change does not move past Upasana to the new zone or area. Works with a raw cursor or the
    ORM session; the caller commits.
    """
    if not (schema_check.has("bookings.zone_code") and schema_check.has("bookings.host_area")):
        return
    if cursor_or_none is not None:
        cursor_or_none.execute(FREEZE_SNAPSHOT_SQL.format(param="%s"), (user_id,))
    else:
        db.session.execute(text(FREEZE_SNAPSHOT_SQL.format(param=":uid")), {"uid": user_id})


def _trial_value(is_trial):
    """{"is_trial": ...} for a new Booking, or nothing when the column does not exist."""
    return {"is_trial": bool(is_trial)} if schema_check.has("bookings.is_trial") else {}


def note_zone_change():
    """After any change to bookings, events or blocked dates: update the per-zone 'completed at' stamps."""
    from zone_completion import record_zone_completion   # imported late: zone_completion imports this module
    record_zone_completion()


def today_ist():
    return (datetime.utcnow() + IST_OFFSET).date()


def month_bounds(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def saturdays_in_month(year, month):
    start, end = month_bounds(year, month)
    first = start + timedelta(days=(calendar.SATURDAY - start.weekday()) % 7)
    return [first + timedelta(days=7 * i) for i in range(((end - first).days // 7) + 1)]


def taken_dates(dates):
    """Dates that already hold an active member booking or common event."""
    booked = {
        b.booking_date
        for b in Booking.query.filter(Booking.booking_date.in_(dates), Booking.is_active == True).all()
    }
    events = {
        e.event_date
        for e in UpasanaEvent.query.filter(UpasanaEvent.event_date.in_(dates), UpasanaEvent.is_active == True).all()
    }
    return booked | events


def is_date_taken(booking_date):
    return booking_date in taken_dates([booking_date])


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
    """Member self-bookings per zone; admin bookings don't use up a zone's monthly quota."""
    start, end = month_bounds(year, month)
    zone = booking_zone()
    rows = (
        db.session.query(zone, func.count(Booking.id))
        .join(User, User.id == Booking.user_id)
        .filter(
            Booking.booking_date >= start,
            Booking.booking_date <= end,
            Booking.is_active == True,
            Booking.booked_by_admin == False,
        )
        .group_by(zone)
        .all()
    )
    return {zone: count for zone, count in rows}


def open_saturdays_in_month(year, month):
    """Saturdays still bookable: not in the past, not blocked, not already taken."""
    today = today_ist()
    candidates = [d for d in saturdays_in_month(year, month) if d >= today]
    if not candidates:
        return 0
    blocked = {
        b.blocked_date
        for b in BlockedDate.query.filter(BlockedDate.blocked_date.in_(candidates)).all()
    }
    taken = taken_dates(candidates)
    return sum(1 for d in candidates if d not in blocked and d not in taken)


def year_zone_overview(year, enable_zone_restriction=True):
    """
    For every zone, the months of the year in which one of its members could still book, plus
    each zone's active bookings. Same rules as zone_slot_status(), from three bulk queries.
    """
    today = today_ist()
    start, end = date(year, 1, 1), date(year, 12, 31)
    rows = (
        db.session.query(Booking.booking_date, Booking.booked_by_admin, booking_zone())
        .join(User, User.id == Booking.user_id)
        .filter(Booking.booking_date >= start, Booking.booking_date <= end, Booking.is_active == True)
        .all()
    )
    events = {
        e.event_date
        for e in UpasanaEvent.query.filter(
            UpasanaEvent.event_date >= start, UpasanaEvent.event_date <= end, UpasanaEvent.is_active == True
        ).all()
    }
    blocked = {
        b.blocked_date
        for b in BlockedDate.query.filter(BlockedDate.blocked_date >= start, BlockedDate.blocked_date <= end).all()
    }
    taken = {row[0] for row in rows} | events

    member_counts = {}      # (month, zone) -> member self-bookings, which use up the zone's quota
    booking_counts = {zone: 0 for zone in ZONE_LIMITS}
    for booking_date, by_admin, zone in rows:
        if zone in booking_counts:
            booking_counts[zone] += 1
        if not by_admin:
            member_counts[(booking_date.month, zone)] = member_counts.get((booking_date.month, zone), 0) + 1

    open_months = {zone: [] for zone in ZONE_LIMITS}
    for month in range(1, 13):
        open_saturdays = [
            d for d in saturdays_in_month(year, month) if d >= today and d not in blocked and d not in taken
        ]
        if not open_saturdays:
            continue
        for zone, limit in ZONE_LIMITS.items():
            if enable_zone_restriction:
                if member_counts.get((month, zone), 0) >= limit:
                    continue
                # The last open date of a month is held for Zone A until Zone A has its booking.
                if zone != "A" and member_counts.get((month, "A"), 0) == 0 and len(open_saturdays) <= 1:
                    continue
            open_months[zone].append(month)
    return {"open_months": open_months, "booking_counts": booking_counts}


def zone_slot_status(zone_code, year, month):
    """None when the zone may still book. Otherwise zone_unknown, zone_full, or reserved."""
    if zone_code not in ZONE_LIMITS:
        return "zone_unknown"

    counts = monthly_zone_counts(year, month)
    if counts.get(zone_code, 0) >= ZONE_LIMITS[zone_code]:
        return "zone_full"

    # The last open date of a month is held for Zone A until Zone A has its booking.
    if zone_code != "A" and counts.get("A", 0) == 0 and open_saturdays_in_month(year, month) <= 1:
        return "reserved"

    return None


def zone_rule_error(zone_code, year, month):
    """Monthly zone allocation check. Returns an error message or None."""
    status = zone_slot_status(zone_code, year, month)
    if status == "zone_unknown":
        return "Your zone is not set up for Upasana booking. Please contact the admin to update your pincode/zone."
    if status == "reserved":
        return "The remaining date this month is reserved for Zone A. Please choose another month."
    if status == "zone_full":
        return f"{ZONE_NAMES[zone_code]} is full for this month. Please try another month."
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
    Returns (message, status_code, code) when not allowed, else None.
    """
    blocked = BlockedDate.query.filter_by(blocked_date=booking_date).first()
    if blocked:
        message = "This date is not available for Upasana booking."
        if blocked.reason:
            message = f"{message} ({blocked.reason})"
        return message, 400, "blocked"

    if is_date_taken(booking_date):
        return SLOT_TAKEN_MSG, 409, "date_taken"

    if active_booking_in_year(user.id, booking_date.year):
        return "You have already made one booking for this year.", 400, "already_booked"

    if enable_zone_restriction:
        status = zone_slot_status(user.zone_code, booking_date.year, booking_date.month)
        if status:
            return zone_rule_error(user.zone_code, booking_date.year, booking_date.month), 400, status

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
def create_booking(user_id, booking_date, mahaprasad=False, enable_zone_restriction=True, is_trial=False):
    """Creates a booking after validating every rule while holding the user and month locks."""
    booking_date = _parse_date(booking_date)
    if not booking_date:
        return jsonify({"error": "Invalid date format. Use 'YYYY-MM-DD'."}), 400

    if booking_date.weekday() != calendar.SATURDAY:
        return jsonify({"error": "Upasana can only be booked on Saturdays."}), 400

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
            message, status, code = rule_error
            logging.info(f"Booking rejected user={user_id} date={booking_date}: {message}")
            return jsonify({"error": message, "code": code}), status

        now = datetime.utcnow()
        db.session.add(Booking(
            user_id=user_id,
            booking_date=booking_date,
            mahaprasad=bool(mahaprasad),
            created_at=now,
            updated_date=now,
            updated_by=user_id,
            is_active=True,
            **_trial_value(is_trial),
            **host_snapshot(user),
        ))
        db.session.commit()
        note_zone_change()
        logging.info(f"Booking successful user={user_id} date={booking_date} trial={bool(is_trial)}")
        return jsonify({
            "message": "Booking successful.", "booking_date": str(booking_date), "is_trial": bool(is_trial),
        }), 201

    except IntegrityError as e:
        db.session.rollback()
        logging.warning(f"Booking integrity conflict user={user_id} date={booking_date}: {e}")
        return jsonify({"error": SLOT_TAKEN_MSG, "code": "date_taken"}), 409
    except OperationalError as e:
        db.session.rollback()
        logging.warning(f"Booking operational error user={user_id} date={booking_date}: {e}")
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Unexpected booking error user={user_id} date={booking_date}: {e}")
        return jsonify({"error": "Unexpected error during booking."}), 500


# =======================================================
# 🛡️ Admin booking on behalf of a member
# =======================================================
def admin_create_booking(user_id, booking_date, mahaprasad, admin_label, is_trial=False, on_booked=None):
    """
    Any date, no zone / weekday / one-per-year / blocked-date rules; the date must still be free.
    `on_booked(booking)` runs in the same transaction, after the booking row exists (e.g. waitlist).
    """
    booking_date = _parse_date(booking_date)
    if not booking_date:
        return jsonify({"error": "Invalid date format. Use 'YYYY-MM-DD'."}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Member not found."}), 404

    try:
        lock_user_and_month(user.id, booking_date)

        if is_date_taken(booking_date):
            db.session.rollback()
            return jsonify({"error": SLOT_TAKEN_MSG}), 409

        now = datetime.utcnow()
        # (user_id, booking_date) is unique, so a cancelled booking on this date is turned back on
        booking = Booking.query.filter_by(user_id=user.id, booking_date=booking_date).first()
        if booking:
            booking.is_active = True
            booking.mahaprasad = bool(mahaprasad)
            booking.booked_by_admin = True
            set_host_snapshot(booking, user)
            if schema_check.has("bookings.is_trial"):
                booking.is_trial = bool(is_trial)
            booking.updated_date = now
        else:
            booking = Booking(
                user_id=user.id,
                booking_date=booking_date,
                mahaprasad=bool(mahaprasad),
                created_at=now,
                updated_date=now,
                is_active=True,
                booked_by_admin=True,
                **_trial_value(is_trial),
                **host_snapshot(user),
            )
            db.session.add(booking)
        if on_booked:
            db.session.flush()
            on_booked(booking)
        db.session.commit()
        note_zone_change()
        logging.info(f"Admin {admin_label} booked user={user.id} date={booking_date}")
        return jsonify({"message": "Upasana booked.", "booking_id": booking.id, "booking_date": str(booking_date)}), 201

    except IntegrityError as e:
        db.session.rollback()
        logging.warning(f"Admin booking integrity conflict user={user.id} date={booking_date}: {e}")
        return jsonify({"error": SLOT_TAKEN_MSG}), 409
    except OperationalError:
        db.session.rollback()
        return jsonify({"error": "Server is busy. Please retry in a moment."}), 503
    except Exception as e:
        db.session.rollback()
        logging.exception(f"Unexpected admin booking error user={user_id} date={booking_date}: {e}")
        return jsonify({"error": "Unexpected error during booking."}), 500


def zone_bookings_in_month(zone_code, year, month, exclude_ids=()):
    """Every active booking (member or admin) held by a zone's members in a month."""
    start, end = month_bounds(year, month)
    query = (
        db.session.query(func.count(Booking.id))
        .join(User, User.id == Booking.user_id)
        .filter(
            booking_zone() == zone_code,
            Booking.booking_date >= start,
            Booking.booking_date <= end,
            Booking.is_active == True,
        )
    )
    if exclude_ids:
        query = query.filter(Booking.id.notin_(list(exclude_ids)))
    return query.scalar() or 0


def admin_override_warnings(user, booking_date, exclude_ids=(), check_reserved=True):
    """
    Member rules that putting this member on this date would bypass. Informational only:
    an admin may always go ahead. exclude_ids are bookings being moved away by the same action.
    """
    warnings = []
    month_label = booking_date.strftime("%B %Y")
    is_saturday = booking_date.weekday() == calendar.SATURDAY
    if not is_saturday:
        warnings.append(f"{booking_date.strftime('%A')} is not a Saturday. Members can book Saturdays only.")

    zone = user.zone_code
    limit = ZONE_LIMITS.get(zone)
    if not limit:
        warnings.append(f"Zone '{zone or '-'}' is not set up for Upasana booking.")
        return warnings

    count = zone_bookings_in_month(zone, booking_date.year, booking_date.month, exclude_ids)
    if count >= limit:
        warnings.append(
            f"Zone {zone} already has {count} Upasana in {month_label} (limit {limit}). "
            "This goes over the zone limit."
        )
    elif (
        check_reserved
        and is_saturday
        and zone != "A"
        and zone_bookings_in_month("A", booking_date.year, booking_date.month, exclude_ids) == 0
        and open_saturdays_in_month(booking_date.year, booking_date.month) <= 1
    ):
        warnings.append(f"This is the last free Saturday of {month_label}, normally kept for Zone A.")
    return warnings


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

        if booking.booked_by_admin:
            rule_error = (SLOT_TAKEN_MSG, 409, "date_taken") if is_date_taken(booking.booking_date) else None
        else:
            rule_error = check_booking_rules(user, booking.booking_date, enable_zone_restriction)
        if rule_error:
            db.session.rollback()
            message, status, _code = rule_error
            return jsonify({"error": f"Cannot reactivate: {message}"}), status

        booking.is_active = True
        booking.updated_date = datetime.utcnow()
        db.session.commit()
        note_zone_change()
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
            months[month] = {"available": False, "reason": "This month has passed.", "code": "passed"}
            continue
        code = zone_slot_status(user.zone_code, year, month) if enable_zone_restriction else None
        reason = zone_rule_error(user.zone_code, year, month) if code else None
        if not code and open_saturdays_in_month(year, month) == 0:
            reason = "No Saturdays are available in this month."
            code = "no_saturdays"
        limit = ZONE_LIMITS.get(user.zone_code)
        used = monthly_zone_counts(year, month).get(user.zone_code, 0) if limit else 0
        months[month] = {
            "available": code is None,
            "reason": reason,
            "code": code,
            "limit": limit,
            "places_left": max(0, limit - used) if limit else None,
            "open_saturdays": 0 if month_end < today else open_saturdays_in_month(year, month),
            "saturday_count": len(saturdays_in_month(year, month)),
            "other_zone": "A" if code == "reserved" else None,
        }
    return {
        "year": year,
        "zone_code": user.zone_code,
        "zone_name": ZONE_NAMES.get(user.zone_code, user.zone_code),
        "already_booked_date": existing.strftime("%Y-%m-%d") if existing else None,
        "months": months,
        # Zones that still have at least one bookable month, so a member with no date left can be
        # told who the remaining dates are for.
        "zones_with_dates": [
            zone for zone, open_ in year_zone_overview(year, enable_zone_restriction)["open_months"].items() if open_
        ],
    }
