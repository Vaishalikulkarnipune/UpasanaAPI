from flask import Flask, request, jsonify
import psycopg2
from model import db,Booking,User
from Booking import create_booking
from datetime import datetime
from config import get_db_connection, release_db_connection,Config
from werkzeug.security import generate_password_hash, check_password_hash
import re
from flask_cors import CORS
import logging

# Set up basic logging configuration
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.config["DEBUG"] = True  # This enables debug mode
app.config.from_object(Config)

# Initialize SQLAlchemy with app
db.init_app(app)
# Configure logging to ensure all logs are captured
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CORS(app)

def validate_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email)

def validate_mobile_number(mobile_number):
    pattern = r'^\d{10}$'  # Assuming a 10-digit mobile number
    return re.match(pattern, mobile_number)

@app.route('/book', methods=['POST'])
def book():
    data = request.get_json()
    user_id = data.get('user_id')
    mahaprasad = data.get('mahaprasad', False)
    booking_date_str = data.get('booking_date')

    # Ensure booking_date_str is present
    if not booking_date_str:
        return jsonify({"error": "Booking date is required."}), 400

    # Convert booking_date from string to date object
    try:
        booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()  # Correct the order here
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Call the create_booking function
    return create_booking(user_id, booking_date, mahaprasad)
# Get All Bookings for Admin 
@app.route('/bookings', methods=['GET'])
def get_all_bookings():
    try:
        # Fetch all bookings
        bookings = Booking.query.all()
        
        # Convert booking data into a JSON-serializable format
        booking_list = []
        for booking in bookings:
            booking_data = {
                'id': booking.id,
                'user_id': booking.user_id,
                'booking_date': booking.booking_date.strftime('%Y-%m-%d'),
                'zone_code': booking.zone,
                'mahaprasad': booking.mahaprasad,
                'created_at': booking.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            booking_list.append(booking_data)

        return jsonify(booking_list), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/bookings/user/<int:user_id>', methods=['GET'])
def get_user_and_booking_details(user_id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                users.id, users.first_name, users.middle_name, users.last_name, 
                users.email, users.mobile_number, users.alternate_mobile_number, 
                users.flat_no, users.full_address, users.area, users.landmark, 
                users.city, users.state, users.pincode, users.anugrahit, 
                users.gender, users.unique_family_code,
                
                bookings.id AS booking_id, bookings.booking_date, bookings.mahaprasad, 
                bookings.created_at, bookings.updated_date, bookings.updated_by

            FROM users
            INNER JOIN bookings ON users.id = bookings.user_id
            WHERE bookings.user_id = %s
        """, (user_id,))
        
        result = cursor.fetchall()

        if not result:
            return jsonify({"message": "User or booking not found, but here's some info."}), 200

        user_data = {
            'id': result[0][0],
            'first_name': result[0][1],
            'middle_name': result[0][2],
            'last_name': result[0][3],
            'email': result[0][4],
            'mobile_number': result[0][5],
            'alternate_mobile_number': result[0][6],
            'flat_no': result[0][7],
            'full_address': result[0][8],
            'area': result[0][9],
            'landmark': result[0][10],
            'city': result[0][11],
            'state': result[0][12],
            'pincode': result[0][13],
            'anugrahit': result[0][14],
            'gender': result[0][15],
            'unique_family_code': result[0][16],
        }

        bookings = [
            {
                'booking_id': row[17],
                'booking_date': row[18],
                'mahaprasad': row[19],
                'created_at': row[20],
                'updated_date': row[21],
                'updated_by': row[22]
            }
            for row in result
        ]

        response = {
            'user': user_data,
            'bookings': bookings
        }

        return jsonify(response), 200

    except psycopg2.DatabaseError as db_err:
        logging.error(f"Database error: {str(db_err)}")
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
         # Close cursor and connection if they are defined
        if cursor is not None:
            cursor.close()
        if conn is not None:
            release_db_connection(conn)

#Fetch All Booking Members List
@app.route('/bookings/users', methods=['GET'])
def get_all_booking_users():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Query to get all users with their booking information
        cursor.execute("""
            SELECT 
                users.id, users.first_name, users.middle_name, users.last_name, 
                users.email, users.mobile_number, users.alternate_mobile_number, 
                users.flat_no, users.full_address, users.area, users.landmark, 
                users.city, users.state, users.pincode, users.anugrahit, 
                users.gender, users.unique_family_code,
                
                bookings.id AS booking_id, bookings.booking_date, bookings.mahaprasad, 
                bookings.created_at, bookings.updated_date, bookings.updated_by

            FROM users
            INNER JOIN bookings ON users.id = bookings.user_id
        """)

        result = cursor.fetchall()

        if not result:
            return jsonify({"message": "No users with bookings found"}), 404

        # Structure data for JSON response
        users_with_bookings = {}
        for row in result:
            user_id = row[0]
            if user_id not in users_with_bookings:
                # Add user data if not already in the dictionary
                users_with_bookings[user_id] = {
                    'id': user_id,
                    'first_name': row[1],
                    'middle_name': row[2],
                    'last_name': row[3],
                    'email': row[4],
                    'mobile_number': row[5],
                    'alternate_mobile_number': row[6],
                    'flat_no': row[7],
                    'full_address': row[8],
                    'area': row[9],
                    'landmark': row[10],
                    'city': row[11],
                    'state': row[12],
                    'pincode': row[13],
                    'anugrahit': row[14],
                    'gender': row[15],
                    'unique_family_code': row[16],
                    'bookings': []
                }
            
            # Append booking data to the user's bookings list
            users_with_bookings[user_id]['bookings'].append({
                'booking_id': row[17],
                'booking_date': row[18],
                'mahaprasad': row[19],
                'created_at': row[20],
                'updated_date': row[21],
                'updated_by': row[22]
            })

        # Convert the dictionary to a list of users with bookings
        response = {'users': list(users_with_bookings.values())}
        
        return jsonify(response), 200

    except psycopg2.DatabaseError as db_err:
        logging.error(f"Database error: {str(db_err)}")
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
         # Close cursor and connection if they are defined
        if cursor is not None:
            cursor.close()
        if conn is not None:
            release_db_connection(conn)


# Step 2: API route for inserting data into users table
@app.route('/register', methods=['POST'])
def register_user():
    conn = None
    cursor = None
    try:
        data = request.get_json()

        # Extracting the required fields
        first_name = data.get('first_name')
        middle_name = data.get('middle_name', None)
        last_name = data.get('last_name')
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirm_password')
        mobile_number = data.get('mobile_number')
        alt_mobile_number = data.get('alternate_mobile_number', None)
        flat_no = data.get('flat_no', None)
        full_address = data.get('full_address')
        area = data.get('area', None)
        landmark = data.get('landmark', None)
        pincode = data.get('pincode')
        anugrahit = data.get('anugrahit', 'no')
        gender = data.get('gender', 'male')
        # Fixed city and state values
        city = "PUNE"
        state = "Maharashtra"
        logging.info("Validating Passwords:")
        # Step 3: Validation checks (optional)
        if password != confirm_password:
            return jsonify({"error": "Passwords do not match"}), 400
        logging.info("Validating Mobile Number:")
        if not validate_mobile_number(mobile_number):
            return jsonify({"error": "Invalid mobile number format"}), 400

        # Insert the user data into PostgreSQL
        conn = get_db_connection()
        cursor = conn.cursor()

        # Query to get the zone code
        zone_query = "SELECT zone_code FROM Zone WHERE pincode = %s"
        cursor.execute(zone_query, (pincode,))
        zone_result = cursor.fetchone()
        logging.info("Validating Pincode:")
        # Check if zone code exists for the provided pincode
        if zone_result is None:
            return jsonify({"Invalid pin code": "Pin code not found. Please contact administrator"}), 400

        # Retrieve the zone code from the query result
        zone_code = zone_result[0]

        # Check if the mobile number is already registered
        cursor.execute("SELECT * FROM users WHERE mobile_number = %s", (mobile_number,))
        existing_user = cursor.fetchone()
        logging.info("Validating Mobile Number already exist:")
        if existing_user:
            return jsonify({"error": "Already registered mobile number"}), 400


        # Step 4: Insert query
        insert_query = """
        INSERT INTO users (
            first_name, middle_name, last_name, email, password, confirm_password,
            mobile_number, alternate_mobile_number, flat_no, full_address, area,
            landmark, city, state, pincode, anugrahit, gender, zone_code
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s)
        """

        # Execute the query
        cursor.execute(insert_query, (
            first_name, middle_name, last_name, email, password, confirm_password, 
            mobile_number, alt_mobile_number, flat_no, full_address, area,
            landmark, city, state, pincode, anugrahit, gender, zone_code
        ))

        conn.commit()  # Commit the transaction
        return jsonify({"message": "User registered successfully"}), 201

    except psycopg2.DatabaseError as db_err:
        logging.error(f"Database error: {str(db_err)}")
        return jsonify({"error": "Database error occurred"}), 500
    except KeyError as key_err:
        logging.error(f"Missing key: {str(key_err)}")
        return jsonify({"error": f"Missing field: {str(key_err)}"}), 400
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        # Close cursor and connection if they are defined
        if cursor is not None:
            cursor.close()
        if conn is not None:
            release_db_connection(conn)

# Step 2: API route for fetching all users
@app.route('/users', methods=['GET'])
def get_all_users():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Step 3: Fetch all users from the users table
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()

        # Step 4: Convert the data into a list of dictionaries for better JSON readability
        user_list = []
        for user in users:
            user_data = {
                'id': user[0],
                'first_name': user[1],
                'middle_name': user[2],
                'last_name': user[3],
                'email': user[4],
                'mobile_number': user[7],
                'alternate_mobile_number': user[8],
                'flat_no': user[9],
                'full_address': user[10],
                'area': user[11],
                'landmark': user[12],
                'city': user[13],
                'state': user[14],
                'pincode': user[15],
                'anugrahit': user[16],
                'gender': user[17],
                'unique_family_code': user[18],
            }
            user_list.append(user_data)

        return jsonify(user_list), 200

    except psycopg2.DatabaseError as db_err:
        logging.error(f"Database error: {str(db_err)}")
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        # Close cursor and connection if they are defined
        if cursor is not None:
            cursor.close()
        if conn is not None:
            release_db_connection(conn)

# PUT Route to update a user's data
@app.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    conn = None
    cursor = None
    try:
        data = request.json  # Get JSON data from request body

        # List of fields that can be updated
        update_fields = ['first_name', 'middle_name', 'last_name', 'email', 'password', 'mobile_number', 'alternate_mobile_number', 
                         'flat_no', 'full_address', 'area', 'landmark', 'city', 'state', 'pincode', 'anugrahit', 'gender']

        # Only keep fields that are in update_fields and provided in the request
        updated_data = {key: data[key] for key in data if key in update_fields}

        if not updated_data:
            return jsonify({"error": "No valid fields to update"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Build the dynamic SQL update query
        set_clause = ', '.join([f"{key} = %s" for key in updated_data])
        values = list(updated_data.values())
        values.append(user_id)  # Add user_id to the values list

        update_query = f"UPDATE users SET {set_clause} WHERE id = %s"
        
        cursor.execute(update_query, values)
        conn.commit()

        return jsonify({"message": "User updated successfully"}), 200

    except psycopg2.DatabaseError as db_err:
        logging.error(f"Database error: {str(db_err)}")
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        # Close cursor and connection if they are defined
        if cursor is not None:
            cursor.close()
        if conn is not None:
            release_db_connection(conn)

# DELETE Route to delete a user by ID
@app.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Execute the DELETE query
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "User not found"}), 404

        return jsonify({"message": "User deleted successfully"}), 200

    except psycopg2.DatabaseError as db_err:
        logging.error(f"Database error: {str(db_err)}")
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        # Close cursor and connection if they are defined
        if cursor is not None:
            cursor.close()
        if conn is not None:
            release_db_connection(conn)

# Route to get user profile by ID
@app.route('/users/<int:user_id>', methods=['GET'])
def get_user_by_id(user_id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch user by ID from the users table
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        # Check if the user exists
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Map the fetched data to a dictionary
        user_data = {
            'id': user[0],
            'first_name': user[1],
            'middle_name': user[2],
            'last_name': user[3],
            'email': user[4],
            'mobile_number': user[7],
            'alternate_mobile_number': user[8],
            'flat_no': user[9],
            'full_address': user[10],
            'area': user[11],
            'landmark': user[12],
            'city': user[13],
            'state': user[14],
            'pincode': user[15],
            'anugrahit': user[16],
            'gender': user[17],
            'unique_family_code': user[18],
        }

        return jsonify(user_data), 200

    except psycopg2.DatabaseError as db_err:
        logging.error(f"Database error: {str(db_err)}")
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        # Close cursor and connection if they are defined
        if cursor is not None:
            cursor.close()
        if conn is not None:
            release_db_connection(conn)

# Example route to get bookings with user details
@app.route('/bookings-with-users', methods=['GET'])
def get_bookings_with_users():
    # Perform the join query between Booking and User tables
    results = (
        db.session.query(Booking, User)
        .join(User, User.id == Booking.user_id)
        .all()
    )
    
    # Format the data for JSON response
    bookings_with_users = [
        {
            "booking_date": booking.booking_date,
            "zone": booking.zone,
           
            "user_first_name": user.first_name,
            "user_last_name": user.last_name,
            "user_member_id": user.id
        }
        for booking, user in results
    ]
    
    return jsonify(bookings_with_users)

# User login route
@app.route('/login', methods=['POST'])
def login():
    conn = None
    cursor = None
    try:
        data = request.json
        mobile_number = data.get('mobile_number')
        password = data.get('password')

        if not mobile_number:
            return jsonify({"error": "Register with mobile number to login"}), 400

        if not mobile_number or not password:
            return jsonify({"error": "Mobile number and password are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Query the user by mobile_number
        cursor.execute("SELECT id, password FROM users WHERE mobile_number = %s", (mobile_number,))
        user = cursor.fetchone()

        if user:
            user_id, stored_password = user

            # Verify the password
            if stored_password == password:
                return jsonify({"message": "Login successful", "user_id": user_id}), 200
            else:
                return jsonify({"error": "Invalid password"}), 401
        else:
            return jsonify({"error": "Mobile number not registered. Please register."}), 404

    except psycopg2.DatabaseError as db_err:
        logging.error(f"Database error: {str(db_err)}")
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        # Close cursor and connection if they are defined
        if cursor is not None:
            cursor.close()
        if conn is not None:
            release_db_connection(conn)
  #get total users and bookings                   
@app.route('/upasanaUsersSummary', methods=['GET'])
def upasanaUsersSummary():
    # Get total number of registered users
    total_users = User.query.count()

    # Get total number of bookings
    total_bookings = Booking.query.count()

    # Get total number of distinct users who have made bookings
    total_booking_users = db.session.query(Booking.user_id).distinct().count()

    # Return the results as a JSON response
    return jsonify({
        "total_users": total_users,
        "total_bookings": total_bookings,
        "total_booking_users": total_booking_users
    }), 200

# Get Booking dates for booking date must be gray
@app.route('/bookingsDates', methods=['GET'])
def get_all_booked_dates():
    booked_dates = Booking.query.with_entities(Booking.booking_date).all()
    # Return dates in ISO format
    dates = [date.booking_date.strftime("%Y-%m-%d") for date in booked_dates]
    print("Booked Dates are:", dates)
    return jsonify({"booked_dates": dates}), 200

@app.route('/health')
def health_check():
    return "Healthy", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000,debug=True)