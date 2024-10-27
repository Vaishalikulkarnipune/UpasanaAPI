from datetime import datetime, timedelta
from flask import jsonify
from model import db, Booking
from config import get_db_connection, release_db_connection

# Helper function to get all Saturdays from December 1 of the booking year
def get_saturdays_for_year():
    start_date = datetime(datetime.now().year, 12, 1)
    saturdays = []
    for i in range(365):
        date = start_date + timedelta(days=i)
        if date.weekday() == 5:  # Saturday is the 5th weekday
            saturdays.append(date.date())
    return saturdays

# Check if booking is allowed based on rules for zone and date
def is_booking_allowed(user_id, zone, booking_date):
    # Get the current year to restrict to once per year
    current_year = datetime.now().year
    start_of_year = datetime(current_year, 1, 1)
    end_of_year = datetime(current_year, 12, 31)

    # Fetch existing bookings for the user within the year
    existing_bookings = Booking.query.filter_by(user_id=user_id).filter(
        Booking.booking_date.between(start_of_year, end_of_year)
    ).all()

    # Apply zone-specific booking rules
    if zone == 'A' and len(existing_bookings) >= 1:
        return False, "Zone A members can only book once per year."
    elif zone in ['B', 'C'] and len(existing_bookings) >= 2:
        return False, "Zone B and C members can book a maximum of twice per year."

    # Ensure the booking date is a Saturday
    if booking_date not in get_saturdays_for_year():
        return False, "You can only book on Saturdays."

    # Prevent duplicate bookings for the same date
    duplicate_booking = Booking.query.filter_by(user_id=user_id, booking_date=booking_date).first()
    if duplicate_booking:
        return False, "A booking already exists for this date."

    return True, "Booking is allowed."

# Function to create a booking if allowed
def create_booking(user_id, zone, booking_date, mahaprasad=False):
    # Validate if booking is allowed
    is_allowed, message = is_booking_allowed(user_id, zone, booking_date)
    if not is_allowed:
        return jsonify({"error": message}), 400

    # Create and commit the new booking
    new_booking = Booking(
        user_id=user_id,
        booking_date=booking_date,
        zone=zone,
        mahaprasad=mahaprasad
    )
    db.session.add(new_booking)
    db.session.commit()

    return jsonify({"message": "Booking successful"}), 201
