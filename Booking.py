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

    # --- Parse booking_date safely ---
    if isinstance(booking_date, str):
        try:
            booking_date = datetime.strptime(booking_date, "%Y-%m-%dT%H:%M:%S").date()
        except ValueError:
            try:
                booking_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"error": "Invalid date format. Use 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS'."}), 400

    # --- Only allow bookings on Saturdays ---
    if booking_date.weekday() != 5:
        return jsonify({"error": "You can only book on Saturdays."}), 400

    # --- Fetch user and zone ---
    user = User.query.filter_by(id=user_id).first()
    if not user:
        print(f"❌ User not found for ID {user_id}")
        return jsonify({"error": "User not found."}), 404

    zone_code = user.zone_code or "Unknown"
    print(f"✅ User {user_id} (Zone {zone_code}) booking for {booking_date}")

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
        return jsonify({"error": "You have already made one booking for this year."}), 400

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
        print(f"⚠️ Lock failed — {booking_date} already locked by another booking.")
        return jsonify({"error": "Upasana is fully booked for this Saturday."}), 400

    # =======================================================
    # 🔍 Monthly Zone Restrictions
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

    # --- Apply Zone Restriction Rules ---
    if enable_zone_restriction:
        if zone_code == "A":
            if monthly_booking_count >= 1:
                return jsonify({"error": "Try another month, Zone A (East Pune) can only book once per month."}), 400
            if zone_a_booking_count >= 1:
                return jsonify({"error": "Try another month, Zone A (East Pune) full for this month."}), 400

        elif zone_code == "B":
            if monthly_booking_count >= 2:
                return jsonify({"error": "Zone B (Rest of Pune) limit reached for this month."}), 400
            if zone_b_booking_count >= 2:
                return jsonify({"error": "Zone B (Rest of Pune) full for this month."}), 400

            saturdays_count = count_saturdays_in_month(booking_date)
            open_booking_in_month = saturdays_count - all_monthly_booking_count
            if open_booking_in_month == 1 and zone_a_booking_count == 0:
                return jsonify({"error": "Zone B (Rest of Pune) full for this month."}), 400

        elif zone_code == "C":
            if monthly_booking_count >= 2:
                return jsonify({"error": "Zone C (PCMC) limit reached for this month."}), 400
            if zone_c_booking_count >= 2:
                return jsonify({"error": "Zone C (PCMC) full for this month."}), 400

            saturdays_count = count_saturdays_in_month(booking_date)
            open_booking_in_month = saturdays_count - all_monthly_booking_count
            if open_booking_in_month == 1 and zone_a_booking_count == 0:
                return jsonify({"error": "Zone C (PCMC) full for this month."}), 400

    # =======================================================
    # 🧩 Prevent Double Booking by Same User or Same Date
    # =======================================================
    existing_booking_on_saturday = Booking.query.filter_by(
        user_id=user_id, booking_date=booking_date, is_active=True
    ).first()
    if existing_booking_on_saturday:
        return jsonify({"error": "Upasana already booked for this Saturday."}), 400

    total_bookings_on_saturday = Booking.query.filter(
        Booking.booking_date == booking_date, Booking.is_active == True
    ).count()

    if total_bookings_on_saturday > 0:
        print("⚠️ Upasana is already booked for this Saturday.")
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
        print("⚠️ IntegrityError (possible duplicate insert):", e)
        traceback.print_exc()
        return jsonify({"error": "Upasana is fully booked for this Saturday."}), 400

    except OperationalError as e:
        db.session.rollback()
        print("⚠️ OperationalError:", e)
        traceback.print_exc()
        return jsonify({"error": "Database temporarily busy. Please retry."}), 500

    except Exception as e:
        db.session.rollback()
        print("⚠️ Unexpected Error:", e)
        traceback.print_exc()
        return jsonify({"error": "Unexpected error during booking.", "details": str(e)}), 500

    finally:
        # =======================================================
        # 🧹 Conditional Lock Cleanup
        # =======================================================
        try:
            # If no booking exists for this date, cleanup the lock
            existing = Booking.query.filter_by(
                booking_date=booking_date, is_active=True
            ).first()

            if not existing:
                print(f"🧹 Removing lock for {booking_date} (no active booking found)")
                db.session.delete(lock)
                db.session.commit()
            else:
                print(f"🔒 Keeping lock for {booking_date} (booking confirmed)")
        except Exception as cleanup_err:
            db.session.rollback()
            print(f"⚠️ Lock cleanup failed for {booking_date}: {cleanup_err}")
