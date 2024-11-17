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

# Fetch the user's zone code
    user = User.query.filter_by(id=user_id).first()
    if user:
        # Retrieve the zone_code from the User table
        zone_code = user.zone_code
        print(f"User with ID {user_id} belongs to Zone {zone_code}.")
    else:
       # return jsonify({"error": "User not found."}), 404
        print("User not found")

    # Ensure the user can only book once per year
    year_start = datetime(booking_date.year, 1, 1)
    year_end = datetime(booking_date.year, 12, 31)
    existing_booking = Booking.query.filter(
        Booking.user_id == user_id,
        Booking.booking_date >= year_start,
        Booking.booking_date <= year_end
    ).first()

    if existing_booking:
        return jsonify({"error": "You have already made a booking for this year."}), 400

    # Check the booking restrictions based on the user's zone code
    month_start = booking_date.replace(day=1)  # First day of the current month
    next_month = booking_date.replace(day=28) + timedelta(days=4)  # Go to next month
    month_end = next_month.replace(day=1) - timedelta(days=1)  # Last day of the current month

    # Count existing bookings in the current month
    monthly_booking_count = Booking.query.filter(
        Booking.user_id == user_id,
        Booking.booking_date >= month_start,
        Booking.booking_date <= month_end
    ).count()

# Count all Zone A bookings in the current month
    zone_a_booking_count = Booking.query.join(User).filter(
        User.zone_code == "A",
        Booking.booking_date >= month_start,
        Booking.booking_date <= month_end
    ).count()

# Count Zone B bookings in the current month
    zone_b_booking_count = Booking.query.join(User).filter(
    User.zone_code == "B",
    Booking.booking_date >= month_start,
    Booking.booking_date <= month_end
).count()

# Count Zone C bookings in the current month
    zone_c_booking_count = Booking.query.join(User).filter(
    User.zone_code == "C",
    Booking.booking_date >= month_start,
    Booking.booking_date <= month_end
).count()

   # Restrict Zone A users to one booking per month
    if zone_code == "A":
        if monthly_booking_count >= 1:
            return jsonify({"error": "Zone A members can only book once per month."}), 400
        if zone_a_booking_count >= 1:
            return jsonify({"error": "A booking already exists for Zone A in this month."}), 400
    
    elif zone_code == "B":
        if monthly_booking_count >= 2:  # Individual restriction
            return jsonify({"error": "Zone B members can only book twice per month."}), 400
    if zone_b_booking_count >= 2:  # Collective restriction
        return jsonify({"error": "Zone B already has two bookings this month."}), 400

    elif zone_code == "C":
        if monthly_booking_count >= 2:  # Individual restriction
            return jsonify({"error": "Zone C members can only book twice per month."}), 400
    if zone_c_booking_count >= 2:  # Collective restriction
        return jsonify({"error": "Zone C already has two bookings this month."}), 400
    #    # Check if the user has already booked for the selected Saturday
    existing_booking_on_saturday = Booking.query.filter_by(user_id=user_id, booking_date=booking_date).first()
    if existing_booking_on_saturday:
        return jsonify({"error": "You have already booked a slot on this Saturday."}), 400

# Check if the selected Saturday is already fully booked
    total_bookings_on_saturday = Booking.query.filter_by(booking_date=booking_date).count()
    if total_bookings_on_saturday > 0:
        print("this saturday is already booked")
        return jsonify({"error": "This Saturday is already fully booked."}), 400
        
    # Create the new booking entry
    new_booking = Booking(
        user_id=user_id,
        booking_date=booking_date,
        mahaprasad=mahaprasad,
        created_at=datetime.utcnow(),
        updated_date=datetime.utcnow(),
        updated_by=user_id
    )

    # Add the booking to the session and commit
    db.session.add(new_booking)
    db.session.commit()

    # Return a success message
    return jsonify({"message": "Booking successful."}), 201

   