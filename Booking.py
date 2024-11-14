from datetime import datetime, timedelta
from flask import jsonify
from model import db, Booking, User
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
def is_booking_allowed(user_id, zone_code, booking_date):
    # Get the current year to restrict to once per year
    current_year = datetime.now().year
    start_of_year = datetime(current_year, 1, 1)
    end_of_year = datetime(current_year, 12, 31)

    # Fetch existing bookings for the user within the year
    existing_bookings = Booking.query.filter_by(user_id=user_id).filter(
        Booking.booking_date.between(start_of_year, end_of_year)
    ).all()

    # Apply zone-specific booking rules
    if zone_code == 'A' and len(existing_bookings) >= 1:
        return False, "Zone A members can only book once per year."
    elif zone_code in ['B', 'C'] and len(existing_bookings) >= 2:
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
def create_booking(user_id, booking_date, mahaprasad=False):
    # Ensure booking_date is a datetime object (if it's a string, parse it, otherwise assume it's already a datetime.date)
    if isinstance(booking_date, str):
        try:
            # Convert booking_date from string to datetime object if it's a string
            booking_date = datetime.strptime(booking_date, "%Y-%m-%dT%H:%M:%S")  # Adjust format as needed
        except ValueError:
            return jsonify({"error": "Invalid date format. Use 'YYYY-MM-DDTHH:MM:SS'."}), 400

    # Ensure booking date is a Saturday (weekday 5 corresponds to Saturday)
    if booking_date.weekday() != 5:  
        return jsonify({"error": "You can only book on Saturdays."}), 400

    # Check if the user has already made a booking in the current year
    year_start = datetime(booking_date.year, 1, 1)
    year_end = datetime(booking_date.year, 12, 31)
    
    # Convert the datetime to date (to match the format of booking_date in DB)
    year_start_date = year_start.date()
    year_end_date = year_end.date()

    existing_booking = Booking.query.filter(
        Booking.user_id == user_id,
        Booking.booking_date >= year_start_date,
        Booking.booking_date <= year_end_date
    ).first()

    if existing_booking:
        return jsonify({"error": "You have already made a booking for this year."}), 400

    # Check if the user has already booked for the selected Saturday
    existing_booking_on_saturday = Booking.query.filter_by(user_id=user_id, 
                                                           booking_date=booking_date).first()

    if existing_booking_on_saturday:
        return jsonify({"error": "You have already booked a slot on this Saturday."}), 400

    # Fetch the user's zone code
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return jsonify({"error": "User not found."}), 404
    
    # Retrieve the zone_code from the User table
    zone_code = user.zone_code

    # Create the new booking entry
    new_booking = Booking(
        user_id=user_id,
        booking_date=booking_date,
        mahaprasad=mahaprasad,
        created_at=datetime.utcnow(),
        updated_date=datetime.utcnow(),
        updated_by=user_id  # Assuming the user making the booking is updating
    )

    # Add the booking to the session and commit
    db.session.add(new_booking)
    db.session.commit()

    # Return a success message
    return jsonify({"message": "Booking successful."}), 201