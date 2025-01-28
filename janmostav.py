from flask import Blueprint, request, jsonify,Flask
import psycopg2
import logging
from config import get_db_connection, release_db_connection  # Ensure this module handles DB connections.
from janmostav import janmostav_bp  # Import the janmostav blueprint

app = Flask(__name__)
# Define a blueprint for janmostav routes
janmostav_bp = Blueprint('janmostav', __name__)

@janmostav_bp.route('/add_event', methods=['POST'])
def add_event():
    print("add_event route hit!")  # Debug log
    conn = None
    cursor = None
    try:
        data = request.get_json()

        # Extracting required fields
        event_name = data.get('event_name')
        event_year = data.get('event_year')
        location = data.get('location')

        # Validation checks
        if not event_name or not event_year or not location:
            return jsonify({"error": "Missing required fields"}), 400

        # Insert the event data into PostgreSQL
        conn = get_db_connection()
        cursor = conn.cursor()

        # Step 4: Insert query
        insert_query = """
        INSERT INTO event (EventName, EventYear, Location,created_at)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """

        # Execute the query
        cursor.execute(insert_query, (event_name, event_year, location))
        conn.commit()  # Commit the transaction

        return jsonify({"message": "Event added successfully"}), 201

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

@janmostav_bp.route('/events', methods=['GET'])
def get_all_events():
    print("List event route hit!")  # Debug log
    conn = None
    cursor = None
    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Query to fetch all events
        fetch_query = "SELECT EventId, EventName, EventYear, Location FROM event"
        cursor.execute(fetch_query)
        
        # Fetch all records
        events = cursor.fetchall()

        # Transform the data into a list of dictionaries
        event_list = [
            {
                "EventId": event[0],
                "EventName": event[1],
                "EventYear": event[2],
                "Location": event[3]
            }
            for event in events
        ]

        return jsonify(event_list), 200

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

@janmostav_bp.route('/update_event/<int:event_id>', methods=['PUT'])
def update_event(event_id):
    conn = None
    cursor = None
    try:
        # Parse the JSON request data
        data = request.get_json()

        # Extract the fields to be updated
        event_name = data.get('event_name')
        event_year = data.get('event_year')
        location = data.get('location')

        # Validation checks
        if not event_name and not event_year and not location:
            return jsonify({"error": "No fields provided for update"}), 400

        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build the update query dynamically
        update_query = "UPDATE event SET "
        update_fields = []
        update_values = []

        if event_name:
            update_fields.append("EventName = %s")
            update_values.append(event_name)
        if event_year:
            update_fields.append("EventYear = %s")
            update_values.append(event_year)
        if location:
            update_fields.append("Location = %s")
            update_values.append(location)

        # Join the update fields and add the condition
        update_query += ", ".join(update_fields) + " WHERE EventId = %s"
        update_values.append(event_id)

        # Execute the update query
        cursor.execute(update_query, tuple(update_values))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Event not found"}), 404

        return jsonify({"message": "Event updated successfully"}), 200

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

@janmostav_bp.route('/add_prasad_count', methods=['POST'])
def add_prasad_count():
    conn = None
    cursor = None
    try:
        data = request.get_json()

        # Extracting the required fields from the request
        event_id = data.get('event_id')
        user_id = data.get('user_id')
        date = data.get('date')
        prasad_afternoon = data.get('prasad_afternoon')
        prasad_evening = data.get('prasad_evening')
        next_day_prasad_afternoon = data.get('next_day_prasad_afternoon')
        next_day_prasad_evening = data.get('next_day_prasad_evening')
        nidhi = data.get('nidhi')

        # Validation checks
        if not all([event_id, user_id, date, prasad_afternoon, prasad_evening, next_day_prasad_afternoon, next_day_prasad_evening, nidhi]):
            return jsonify({"error": "Missing required fields"}), 400

        # Ensure numeric values are valid
        try:
            prasad_afternoon = int(prasad_afternoon)
            prasad_evening = int(prasad_evening)
            next_day_prasad_afternoon = int(next_day_prasad_afternoon)
            next_day_prasad_evening = int(next_day_prasad_evening)
        except ValueError:
            return jsonify({"error": "Prasad counts must be integers"}), 400

        if not isinstance(nidhi, bool):
            return jsonify({"error": "'nidhi' must be a boolean value"}), 400

        # Database connection and query execution
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure the EventId and UserId exist in their respective tables
        cursor.execute("SELECT EventId FROM event WHERE EventId = %s", (event_id,))
        if cursor.fetchone() is None:
            return jsonify({"error": "Invalid EventId"}), 400

        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if cursor.fetchone() is None:
            return jsonify({"error": "Invalid UserId"}), 400

        # Insert query for prasadCount
        insert_query = """
        INSERT INTO prasadCount (
            EventId, UserId, date, prasadAfternoon, prasadEvening, 
            nextDayPrasadAfternoon, nextDayPrasadEvening, Nidhi, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,CURRENT_TIMESTAMP)
        """

        # Execute the query
        cursor.execute(insert_query, (
            event_id, user_id, date, prasad_afternoon, prasad_evening,
            next_day_prasad_afternoon, next_day_prasad_evening, nidhi
        ))

        conn.commit()  # Commit the transaction

        return jsonify({"message": "Prasad count added successfully"}), 201

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

@janmostav_bp.route('/update_prasad_count/<int:record_id>', methods=['PUT'])
def update_prasad_count(record_id):
    conn = None
    cursor = None
    try:
        data = request.get_json()

        # Extract the fields to be updated
        event_id = data.get('event_id')
        user_id = data.get('user_id')
        date = data.get('date')
        prasad_afternoon = data.get('prasad_afternoon')
        prasad_evening = data.get('prasad_evening')
        next_day_prasad_afternoon = data.get('next_day_prasad_afternoon')
        next_day_prasad_evening = data.get('next_day_prasad_evening')
        nidhi = data.get('nidhi')

        # Validation: Ensure at least one field is provided
        if not any([event_id, user_id, date, prasad_afternoon, prasad_evening, next_day_prasad_afternoon, next_day_prasad_evening, nidhi]):
            return jsonify({"error": "No fields provided for update"}), 400

        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build the update query dynamically
        update_query = "UPDATE prasadCount SET "
        update_fields = []
        update_values = []

        if event_id:
            # Check if EventId exists
            cursor.execute("SELECT EventId FROM event WHERE EventId = %s", (event_id,))
            if cursor.fetchone() is None:
                return jsonify({"error": "Invalid EventId"}), 400
            update_fields.append("EventId = %s")
            update_values.append(event_id)

        if user_id:
            # Check if UserId exists
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if cursor.fetchone() is None:
                return jsonify({"error": "Invalid UserId"}), 400
            update_fields.append("UserId = %s")
            update_values.append(user_id)

        if date:
            update_fields.append("date = %s")
            update_values.append(date)

        if prasad_afternoon is not None:
            update_fields.append("prasadAfternoon = %s")
            update_values.append(prasad_afternoon)

        if prasad_evening is not None:
            update_fields.append("prasadEvening = %s")
            update_values.append(prasad_evening)

        if next_day_prasad_afternoon is not None:
            update_fields.append("nextDayPrasadAfternoon = %s")
            update_values.append(next_day_prasad_afternoon)

        if next_day_prasad_evening is not None:
            update_fields.append("nextDayPrasadEvening = %s")
            update_values.append(next_day_prasad_evening)

        if nidhi is not None:
            if not isinstance(nidhi, bool):
                return jsonify({"error": "'nidhi' must be a boolean value"}), 400
            update_fields.append("Nidhi = %s")
            update_values.append(nidhi)

        # Finalize the query
        update_query += ", ".join(update_fields) + " WHERE id = %s"
        update_values.append(record_id)

        # Execute the query
        cursor.execute(update_query, tuple(update_values))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Record not found"}), 404

        return jsonify({"message": "Prasad count updated successfully"}), 200

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

@janmostav_bp.route('/list_prasad_counts', methods=['GET'])
def list_prasad_counts():
    conn = None
    cursor = None
    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Query to retrieve all records from prasadCount table
        query = """
        SELECT pc.id, pc.EventId, e.EventName, pc.UserId, u.first_name, u.last_name, pc.date, 
               pc.prasadAfternoon, pc.prasadEvening, pc.nextDayPrasadAfternoon, pc.nextDayPrasadEvening, pc.Nidhi
        FROM prasadCount pc
        INNER JOIN event e ON pc.EventId = e.EventId
        INNER JOIN users u ON pc.UserId = u.id
        ORDER BY pc.date, pc.id;
        """

        # Execute the query
        cursor.execute(query)
        results = cursor.fetchall()

        # Convert the result into a list of dictionaries
        prasad_counts = []
        for row in results:
            prasad_counts.append({
                "id": row[0],
                "event_id": row[1],
                "event_name": row[2],
                "user_id": row[3],
                "user_name": f"{row[4]} {row[5]}",
                "date": row[6].strftime("%Y-%m-%d"),
                "prasad_afternoon": row[7],
                "prasad_evening": row[8],
                "next_day_prasad_afternoon": row[9],
                "next_day_prasad_evening": row[10],
                "nidhi": row[11]
            })

        return jsonify(prasad_counts), 200

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

@janmostav_bp.route('/get_prasad_by_id/<int:prasad_id>', methods=['GET'])
def get_prasad_by_id(prasad_id):
    conn = None
    cursor = None
    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Query to retrieve the record for the specific prasad_id
        query = """
        SELECT pc.id, pc.EventId, e.EventName, pc.UserId, u.first_name, u.last_name, pc.date, 
               pc.prasadAfternoon, pc.prasadEvening, pc.nextDayPrasadAfternoon, pc.nextDayPrasadEvening, pc.Nidhi
        FROM prasadCount pc
        INNER JOIN event e ON pc.EventId = e.EventId
        INNER JOIN users u ON pc.UserId = u.id
        WHERE pc.id = %s;
        """

        # Execute the query
        cursor.execute(query, (prasad_id,))
        result = cursor.fetchone()

        # Check if the record exists
        if not result:
            return jsonify({"message": "No Prasad record found for the given ID"}), 404

        # Convert the result into a dictionary
        prasad_details = {
            "id": result[0],
            "event_id": result[1],
            "event_name": result[2],
            "user_id": result[3],
            "user_name": f"{result[4]} {result[5]}",
            "date": result[6].strftime("%Y-%m-%d"),
            "prasad_afternoon": result[7],
            "prasad_evening": result[8],
            "next_day_prasad_afternoon": result[9],
            "next_day_prasad_evening": result[10],
            "nidhi": result[11]
        }

        return jsonify(prasad_details), 200

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

    # Save payment details
@janmostav_bp.route('/payment', methods=['POST'])
def save_payment_details():
    conn = None
    cursor = None
    try:
        data = request.get_json()

        # Extract required fields
        event_id = data.get('event_id')
        user_id = data.get('user_id')
        name_of_donar = data.get('name_of_donar')
        date = data.get('date')
        amount = data.get('amount')
        transaction_id = data.get('transaction_id')
        mode_of_payment = data.get('mode_of_payment')

        # Validate required fields
        if not all([event_id, user_id, name_of_donar, date, amount, transaction_id, mode_of_payment]):
            return jsonify({"error": "Missing required fields"}), 400

        # Database connection
        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert query
        insert_query = """
        INSERT INTO paymentDetails (
            EventId, UserId, name_of_donar, date, amount, transaction_id, mode_of_payment, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s,CURRENT_TIMESTAMP)
        """
        cursor.execute(insert_query, (event_id, user_id, name_of_donar, date, amount, transaction_id, mode_of_payment))
        conn.commit()

        return jsonify({"message": "Payment details saved successfully"}), 201

    except psycopg2.IntegrityError as int_err:
        logging.error(f"Integrity error: {str(int_err)}")
        return jsonify({"error": "Transaction ID already exists or foreign key constraint failed"}), 400
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_db_connection(conn)

# Update payment details by ID
@janmostav_bp.route('/payment/<int:payment_id>', methods=['PUT'])
def update_payment_details(payment_id):
    conn = None
    cursor = None
    try:
        data = request.get_json()

        # Extract fields to update
        name_of_donar = data.get('name_of_donar')
        date = data.get('date')
        amount = data.get('amount')
        mode_of_payment = data.get('mode_of_payment')

        if not any([name_of_donar, date, amount, mode_of_payment]):
            return jsonify({"error": "No fields provided for update"}), 400

        # Build update query dynamically
        update_query = "UPDATE paymentDetails SET "
        update_fields = []
        update_values = []

        if name_of_donar:
            update_fields.append("name_of_donar = %s")
            update_values.append(name_of_donar)
        if date:
            update_fields.append("date = %s")
            update_values.append(date)
        if amount:
            update_fields.append("amount = %s")
            update_values.append(amount)
        if mode_of_payment:
            update_fields.append("mode_of_payment = %s")
            update_values.append(mode_of_payment)

        update_query += ", ".join(update_fields) + " WHERE id = %s"
        update_values.append(payment_id)

        # Execute query
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(update_query, tuple(update_values))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Payment record not found"}), 404

        return jsonify({"message": "Payment details updated successfully"}), 200

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_db_connection(conn)

# Get payment details by ID
@janmostav_bp.route('/payment/<int:payment_id>', methods=['GET'])
def get_payment_details(payment_id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch query
        fetch_query = "SELECT * FROM paymentDetails WHERE id = %s"
        cursor.execute(fetch_query, (payment_id,))
        payment = cursor.fetchone()

        if not payment:
            return jsonify({"error": "Payment record not found"}), 404

        # Map to dictionary
        payment_data = {
            "id": payment[0],
            "EventId": payment[1],
            "UserId": payment[2],
            "name_of_donar": payment[3],
            "date": payment[4],
            "amount": float(payment[5]),
            "transaction_id": payment[6],
            "mode_of_payment": payment[7]
        }

        return jsonify(payment_data), 200

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_db_connection(conn)

# List all payment details
@janmostav_bp.route('/payments', methods=['GET'])
def list_all_payments():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Query all records
        fetch_query = "SELECT * FROM paymentDetails"
        cursor.execute(fetch_query)
        payments = cursor.fetchall()

        # Map results
        payment_list = [
            {
                "id": payment[0],
                "EventId": payment[1],
                "UserId": payment[2],
                "name_of_donar": payment[3],
                "date": payment[4],
                "amount": float(payment[5]),
                "transaction_id": payment[6],
                "mode_of_payment": payment[7]
            }
            for payment in payments
        ]

        return jsonify(payment_list), 200

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_db_connection(conn)

# Register the blueprint with the app
app.register_blueprint(janmostav_bp, url_prefix='/janmostav')

# Debug: Print all registered routes
print(app.url_map)

# Run the application
if __name__ == "__main__":
    app.run(debug=True)  # You can set `debug=False` in production

