from datetime import datetime, timedelta
from flask import jsonify
from model import db, Booking, User, SundayBooking  # assuming SundayBooking model exists
import calendar
from sqlalchemy import func

# ✅ Helper: Get all Saturdays from Dec 1 of current year
def get_saturdays_for_year():
    start_date = datetime(datetime.now().year, 12, 1)
    saturdays = []
    for i in range(365):
        date = start_date + timedelta(days=i)
        if date.weekday() == 5:  # Saturday = 5
            saturdays.append(date.date())
    return saturdays

def has_user_already_booked(user_id, year=None):
    if not year:
        year = datetime.utcnow().year

    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31)

    existing_booking = Booking.query.filter(
        Booking.user_id == user_id,
        Booking.booking_date >= year_start,
        Booking.booking_date <= year_end,
        Booking.is_active == True
    ).first()

    existing_sunday_booking = SundayBooking.query.filter(
        SundayBooking.user_id == user_id,
        SundayBooking.booking_date >= year_start,
        SundayBooking.booking_date <= year_end,
        SundayBooking.is_active == True
    ).first()

    return existing_booking or existing_sunday_booking

# ✅ Sunday booking function
def create_sunday_booking(user_id, booking_date, mahaprasad=False):
    # Ensure booking_date is a datetime
    if isinstance(booking_date, str):
        try:
            booking_date = datetime.strptime(booking_date, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return jsonify({"error": "Invalid date format. Use 'YYYY-MM-DDTHH:MM:SS'."}), 400

    # Ensure booking date is a Sunday (weekday 6 = Sunday)
    if booking_date.weekday() != 6:
        return jsonify({"error": "You can only book on Sundays."}), 400
    
     # Check user exists
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return jsonify({"error": "User not found."}), 404

    # Check if user already booked for this year
    if has_user_already_booked(user_id, booking_date.year):
        return jsonify({"error": "You have already booked Upasana this year."}), 400

    # 1️⃣ Check if all Saturdays are full before allowing Sunday booking
    saturdays = get_saturdays_for_year()
    total_saturdays = len(saturdays)
    total_saturday_bookings = (
        Booking.query.filter(
            func.date(Booking.booking_date).in_(saturdays),
            Booking.is_active == True
        ).count()
    )

    if total_saturday_bookings < total_saturdays:
        return jsonify({"error": "Sunday booking not allowed until all Saturday slots are full."}), 400

    # 2️⃣ Check user existence
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return jsonify({"error": "User not found."}), 404

    # 3️⃣ Ensure one booking per year (Saturday or Sunday)
    year_start = datetime(booking_date.year, 1, 1)
    year_end = datetime(booking_date.year, 12, 31)

    existing_booking = Booking.query.filter(
        Booking.user_id == user_id,
        Booking.booking_date >= year_start,
        Booking.booking_date <= year_end,
        Booking.is_active == True
    ).first()

    existing_sunday_booking = SundayBooking.query.filter(
        SundayBooking.user_id == user_id,
        SundayBooking.booking_date >= year_start,
        SundayBooking.booking_date <= year_end,
        SundayBooking.is_active == True
    ).first()

    if existing_booking or existing_sunday_booking:
        return jsonify({"error": "You have already booked either Saturday or Sunday Upasana this year."}), 400

    # 4️⃣ Prevent duplicate Sunday booking for same date
    existing_booking_on_sunday = SundayBooking.query.filter_by(
        user_id=user_id, booking_date=booking_date, is_active=True
    ).first()

    if existing_booking_on_sunday:
        return jsonify({"error": "You have already booked for this Sunday."}), 400

    # 5️⃣ Check if the selected Sunday is fully booked (optional capacity check)
    total_bookings_on_sunday = SundayBooking.query.filter(
        func.date(SundayBooking.booking_date) == booking_date,
        SundayBooking.is_active == True
    ).count()

    # For example, if you want to limit to 300 members per Sunday:
    SUNDAY_LIMIT = 1
    if total_bookings_on_sunday >= SUNDAY_LIMIT:
        return jsonify({"error": "Upasana is fully booked for this Sunday."}), 400

    # 6️⃣ Create new Sunday booking
    new_booking = SundayBooking(
        user_id=user_id,
        booking_date=booking_date,
        mahaprasad=mahaprasad,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        updated_by=user_id,
        is_active=True
    )

    db.session.add(new_booking)
    db.session.commit()

    return jsonify({"message": "Sunday booking successful."}), 201
