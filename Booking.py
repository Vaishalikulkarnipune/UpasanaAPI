from datetime import datetime, timedelta
from flask import jsonify
from model import db, Booking, User, BookingLock
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError
import calendar
import traceback


# =======================================================
# 🧩 Helper Function to Count Saturdays in a Month
# =======================================================
def count_saturdays_in_month(date):
    year = date.year
    month = date.month
    month_days = calendar.monthcalendar(year, month)
    saturdays = sum(1 for week in month_days if week[calendar.SATURDAY] != 0)
    return saturdays


# =======================================================
# 🧩 Helper Function to Get All Saturdays from Dec 1
# =======================================================
def get_saturdays_for_year():
    start_date = datetime(datetime.now().year, 12, 1)
    saturdays = []
    for i in range(365):
        date = start_date + timedelta(days=i)
        if date.weekday() == 5:
            saturdays.append(date.date())
    return saturdays


# =======================================================
# 🧱 Main Booking Function
# =======================================================
def create_booking(user_id, booking_date, mahaprasad=False, enable_zone_restriction=True):
    """Creates a booking safely with all business rules and race condition protection."""

    # Helper to remove lock when needed
    def remove_lock(date):
        try:
            BookingLock.query.filter_by(booking_date=date).delete()
            db.session.commit()
            print(f"🧹 Lock removed for {date}")
        except Exception as ex:
            db.session.rollback()
            print(f"⚠️ Failed to remove lock for {date}: {ex}")

    # --- Parse booking_date safely ---
    if isinstance(booking_date, str):
        try:
            booking_date = datetime.strptime(booking_date, "%Y-%m-%dT%H:%M:%S").date()
        except ValueError:
            try:
                booking_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
            except ValueError:
                print("DEBUG: RETURN_REASON=INVALID_DATE_FORMAT", booking_date)
                return jsonify({"error": "Invalid date format. Use 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'."}), 400

    # --- Only allow bookings on Saturdays ---
    if booking_date.weekday() != 5:
        print("DEBUG: RETURN_REASON=NOT_SATURDAY", booking_date.weekday())
        return jsonify({"error": "You can only book on Saturdays."}), 400

    # --- Fetch user and zone ---
    user = User.query.filter_by(id=user_id).first()
    if not user:
        print(f"DEBUG: RETURN_REASON=USER_NOT_FOUND user_id={user_id}")
        return jsonify({"error": "User not found."}), 404

    zone_code = user.zone_code or "Unknown"
    print(f"✅ User {user_id} (Zone {zone_code}) booking for {booking_date}")

    # =========================================================
    # 🔥 OPTION A: Prevent rebooking of a cancelled date (immediate)
    # =========================================================
    cancelled_booking = Booking.query.filter_by(
        user_id=user_id,
        booking_date=booking_date,
        is_active=False
    ).first()

    if cancelled_booking:
        print(f"DEBUG: RETURN_REASON=CANCELLED_DATE_REBOOK_ATTEMPT booking_id={cancelled_booking.id} user_id={user_id} date={booking_date}")
        return jsonify({"error": "Cancelled dates cannot be rebooked."}), 400
    # =========================================================

    # --- Restrict one booking per user per year ---
    year_start = datetime(booking_date.year, 1, 1).date()
    year_end = datetime(booking_date.year, 12, 31).date()
    existing_booking = Booking.query.filter(
        Booking.user_id == user_id,
        Booking.booking_date >= year_start,
        Booking.booking_date <= year_end,
        Booking.is_active == True
    ).first()

    if existing_booking:
        print(f"DEBUG: RETURN_REASON=ONE_BOOKING_PER_YEAR user_id={user_id} existing_booking_id={existing_booking.id}")
        return jsonify({"error": "You have already made one booking for this year."}), 400

    # =======================================================
    # DIAGNOSTIC: state before trying to create lock
    # =======================================================
    try:
        existing_lock_pre = BookingLock.query.filter_by(booking_date=booking_date).first()
        total_active_bookings_pre = Booking.query.filter(Booking.booking_date == booking_date, Booking.is_active == True).count()
        print(f"DEBUG: PRE_LOCK existing_lock={bool(existing_lock_pre)} total_active_bookings={total_active_bookings_pre}")
    except Exception as ex:
        print(f"DEBUG: PRE_LOCK query failed: {ex}")

    # =======================================================
    # 🔒 Race Condition Prevention: Soft Lock (BookingLock)
    # =======================================================
    try:
        lock = BookingLock(booking_date=booking_date)
        db.session.add(lock)
        db.session.commit()
        print(f"🔒 Lock acquired for {booking_date}")
    except IntegrityError:
        db.session.rollback()
        print(f"DEBUG: RETURN_REASON=LOCK_EXISTS booking_date={booking_date}")
        return jsonify({"error": "Upasana is fully booked for this Saturday."}), 400

    # =======================================================
    # 🔍 Monthly Zone Restrictions (compute diagnostic values)
    # =======================================================
    month_start = booking_date.replace(day=1)
    next_month = booking_date.replace(day=28) + timedelta(days=4)
    month_end = next_month.replace(day=1) - timedelta(days=1)

    monthly_booking_count = Booking.query.filter(
        Booking.user_id == user_id,
        Booking.booking_date >= month_start,
        Booking.booking_date <= month_end,
        Booking.is_active == True
    ).count()

    all_monthly_booking_count = Booking.query.filter(
        Booking.booking_date >= month_start,
        Booking.booking_date <= month_end,
        Booking.is_active == True
    ).count()

    zone_a_booking_count = Booking.query.join(User).filter(
        User.zone_code == "A",
        Booking.booking_date >= month_start,
        Booking.booking_date <= month_end,
        Booking.is_active == True
    ).count()

    zone_b_booking_count = Booking.query.join(User).filter(
        User.zone_code == "B",
        Booking.booking_date >= month_start,
        Booking.booking_date <= month_end,
        Booking.is_active == True
    ).count()

    zone_c_booking_count = Booking.query.join(User).filter(
        User.zone_code == "C",
        Booking.booking_date >= month_start,
        Booking.booking_date <= month_end,
        Booking.is_active == True
    ).count()

    # Diagnostic print of relevant counters
    print(f"DEBUG: COUNTERS month_start={month_start} month_end={month_end} monthly_booking_count={monthly_booking_count} all_monthly_booking_count={all_monthly_booking_count} zoneA={zone_a_booking_count} zoneB={zone_b_booking_count} zoneC={zone_c_booking_count}")

    # --- Apply Zone Restriction Rules ---
    if enable_zone_restriction:
        if zone_code == "A":
            if monthly_booking_count >= 1:
                print(f"DEBUG: RETURN_REASON=ZONE_A_MONTHLY_LIMIT user_id={user_id} monthly_booking_count={monthly_booking_count}")
                remove_lock(booking_date)
                return jsonify({"error": "Try another month, Zone A (East Pune) can only book once per month."}), 400
            if zone_a_booking_count >= 1:
                print(f"DEBUG: RETURN_REASON=ZONE_A_FULL month={month_start.month} zone_a_booking_count={zone_a_booking_count}")
                remove_lock(booking_date)
                return jsonify({"error": "Try another month, Zone A (East Pune) full for this month."}), 400

        elif zone_code == "B":
            if monthly_booking_count >= 2:
                print(f"DEBUG: RETURN_REASON=ZONE_B_MONTHLY_LIMIT user_id={user_id} monthly_booking_count={monthly_booking_count}")
                remove_lock(booking_date)
                return jsonify({"error": "Zone B (Rest of Pune) limit reached for this month."}), 400
            if zone_b_booking_count >= 2:
                print(f"DEBUG: RETURN_REASON=ZONE_B_FULL zone_b_booking_count={zone_b_booking_count}")
                remove_lock(booking_date)
                return jsonify({"error": "Zone B (Rest of Pune) full for this month."}), 400

            saturdays_count = count_saturdays_in_month(booking_date)
            open_booking_in_month = saturdays_count - all_monthly_booking_count
            print(f"DEBUG: ZONE_B saturdays_count={saturdays_count} open_booking_in_month={open_booking_in_month}")
            if open_booking_in_month == 1 and zone_a_booking_count == 0:
                print("DEBUG: RETURN_REASON=ZONE_B_OPEN_SLOTS_RESTRICTED")
                remove_lock(booking_date)
                return jsonify({"error": "Zone B (Rest of Pune) full for this month."}), 400

        elif zone_code == "C":
            if monthly_booking_count >= 2:
                print(f"DEBUG: RETURN_REASON=ZONE_C_MONTHLY_LIMIT monthly_booking_count={monthly_booking_count}")
                remove_lock(booking_date)
                return jsonify({"error": "Zone C (PCMC) limit reached for this month."}), 400
            if zone_c_booking_count >= 2:
                print(f"DEBUG: RETURN_REASON=ZONE_C_FULL zone_c_booking_count={zone_c_booking_count}")
                remove_lock(booking_date)
                return jsonify({"error": "Zone C (PCMC) full for this month."}), 400

            saturdays_count = count_saturdays_in_month(booking_date)
            open_booking_in_month = saturdays_count - all_monthly_booking_count
            print(f"DEBUG: ZONE_C saturdays_count={saturdays_count} open_booking_in_month={open_booking_in_month}")
            if open_booking_in_month == 1 and zone_a_booking_count == 0:
                print("DEBUG: RETURN_REASON=ZONE_C_OPEN_SLOTS_RESTRICTED")
                remove_lock(booking_date)
                return jsonify({"error": "Zone C (PCMC) full for this month."}), 400

    # =======================================================
    # 🧩 Prevent Double Booking by Same User or Same Date
    # =======================================================
    existing_booking_on_saturday = Booking.query.filter_by(
        user_id=user_id, booking_date=booking_date, is_active=True
    ).first()
    if existing_booking_on_saturday:
        print(f"DEBUG: RETURN_REASON=EXISTING_ACTIVE_BOOKING user_id={user_id} booking_id={existing_booking_on_saturday.id}")
        remove_lock(booking_date)
        return jsonify({"error": "Upasana already booked for this Saturday."}), 400

    total_bookings_on_saturday = Booking.query.filter(
        Booking.booking_date == booking_date, Booking.is_active == True
    ).count()

    print(f"DEBUG: total_bookings_on_saturday={total_bookings_on_saturday}")

    if total_bookings_on_saturday > 0:
        print(f"DEBUG: RETURN_REASON=TOTAL_BOOKINGS_GT_0 count={total_bookings_on_saturday}")
        remove_lock(booking_date)
        return jsonify({"error": "Upasana is fully booked for this Saturday."}), 400

    # =======================================================
    # 🧾 Create and Commit New Booking
    # =======================================================
    new_booking = Booking(
        user_id=user_id,
        booking_date=booking_date,
        mahaprasad=mahaprasad,
        created_at=datetime.utcnow(),
        updated_date=datetime.utcnow(),
        updated_by=user_id,
        is_active=True
    )

    try:
        db.session.add(new_booking)
        db.session.commit()
        print(f"✅ Booking successful: User {user_id} → {booking_date}")

        return jsonify({
            "message": "Booking successful.",
            "booking_date": str(booking_date)
        }), 201

    except IntegrityError as e:
        db.session.rollback()
        print(f"DEBUG: EXCEPT_INTEGRITYERROR during commit: {e}")
        remove_lock(booking_date)
        return jsonify({"error": "Upasana is fully booked for this Saturday."}), 400

    except OperationalError as e:
        db.session.rollback()
        print(f"DEBUG: EXCEPT_OPERATIONALERROR during commit: {e}")
        remove_lock(booking_date)
        return jsonify({"error": "Database temporarily busy. Please retry."}), 500

    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: EXCEPT_GENERAL during commit: {e}")
        remove_lock(booking_date)
        return jsonify({"error": "Unexpected error during booking.", "details": str(e)}), 500

    finally:
        try:
            existing = Booking.query.filter_by(
                booking_date=booking_date, is_active=True
            ).first()

            if not existing:
                print(f"DEBUG: FINALLY - no active booking found for {booking_date}, removing lock")
                remove_lock(booking_date)
            else:
                print(f"DEBUG: FINALLY - active booking exists for {booking_date}, keeping lock")
        except Exception as ex:
            print(f"DEBUG: FINALLY cleanup failed: {ex}")
            pass


