from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import UniqueConstraint

db = SQLAlchemy()

# ---------------------------------------------------
# USER MODEL
# ---------------------------------------------------
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    mobile_number = db.Column(db.String(15), unique=True, nullable=False)
    alternate_mobile_number = db.Column(db.String(15))
    flat_no = db.Column(db.String(20))
    full_address = db.Column(db.Text, nullable=False)
    area = db.Column(db.String(100))
    landmark = db.Column(db.String(100))
    city = db.Column(db.String(50), nullable=False)
    state = db.Column(db.String(50), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)
    anugrahit = db.Column(db.String(3), default='no')
    gender = db.Column(db.String(10), default='male')
    unique_family_code = db.Column(db.Integer, unique=True)
    zone_code = db.Column(db.String(50), nullable=False)

    bookings = db.relationship('Booking', back_populates='user')
    sunday_bookings = db.relationship('SundayBooking', back_populates='user')


# ---------------------------------------------------
# BOOKING MODELS
# ---------------------------------------------------
class Booking(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    mahaprasad = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_date = db.Column(db.DateTime, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)

    user = db.relationship('User', back_populates='bookings')


class SundayBooking(db.Model):
    __tablename__ = 'sunday_bookings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    mahaprasad = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)

    user = db.relationship('User', back_populates='sunday_bookings')


# ---------------------------------------------------
# ZONE
# ---------------------------------------------------
class Zone(db.Model):
    __tablename__ = 'zone'

    id = db.Column(db.Integer, primary_key=True)
    area_name = db.Column(db.String(50), nullable=False)
    pincode = db.Column(db.String(6), nullable=False, unique=True)
    zone_code = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f"<Zone {self.zone_code} - {self.area_name}>"


# ---------------------------------------------------
# FEATURE TOGGLE
# ---------------------------------------------------
class FeatureToggle(db.Model):
    __tablename__ = 'feature_toggle'

    id = db.Column(db.Integer, primary_key=True)
    toggle_name = db.Column(db.String(50), unique=True, nullable=False)
    toggle_enabled = db.Column(db.Boolean, nullable=False)

    def __repr__(self):
        return f"<FeatureToggle {self.toggle_name}: {self.toggle_enabled}>"


# ---------------------------------------------------
# REFERENCE DATA
# ---------------------------------------------------
class ReferenceData(db.Model):
    __tablename__ = 'reference_data'

    id = db.Column(db.Integer, primary_key=True)
    reference_key = db.Column(db.String, unique=True, nullable=False)
    reference_value = db.Column(db.String, nullable=False)

    def __repr__(self):
        return f"<ReferenceData {self.reference_key}: {self.reference_value}>"


# ---------------------------------------------------
# BOOKING LOCK
# ---------------------------------------------------
class BookingLock(db.Model):
    __tablename__ = "booking_locks"

    id = db.Column(db.Integer, primary_key=True)
    booking_date = db.Column(db.Date, unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------------------------------------------
# JANMOTSAV MODELS
# ---------------------------------------------------
class JanmotsavYear(db.Model):
    __tablename__ = "janmotsav_years"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, unique=True, nullable=False)
    event_name = db.Column(db.String(255))
    is_current = db.Column(db.Boolean, default=False)

    location_name = db.Column(db.String(255))
    location_url = db.Column(db.Text)
    facebook_url = db.Column(db.Text)
    youtube_url = db.Column(db.Text)
    instagram_url = db.Column(db.Text)
    custom_link_1 = db.Column(db.Text)
    custom_link_2 = db.Column(db.Text)
    description = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    days = db.relationship("JanmotsavDay", back_populates="year_info")


class JanmotsavDay(db.Model):
    __tablename__ = "janmotsav_days"

    id = db.Column(db.Integer, primary_key=True)
    year_id = db.Column(db.Integer, db.ForeignKey("janmotsav_years.id"))
    event_date = db.Column(db.Date, nullable=False)

    breakfast = db.Column(db.Boolean, default=False)
    lunch = db.Column(db.Boolean, default=False)
    evesnacks = db.Column(db.Boolean, default=False)
    dinner = db.Column(db.Boolean, default=False)

    year_info = db.relationship("JanmotsavYear", back_populates="days")


class JanmotsavAttendance(db.Model):
    __tablename__ = "janmotsav_attendance"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    year_id = db.Column(db.Integer, nullable=False)
    day_id = db.Column(db.Integer, db.ForeignKey("janmotsav_days.id"))

    breakfast_count = db.Column(db.Integer, default=0)
    lunch_count = db.Column(db.Integer, default=0)
    evesnacks_count = db.Column(db.Integer, default=0)
    dinner_count = db.Column(db.Integer, default=0)

    seva_nidhi = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "year_id", "day_id", name="unique_attendance"),
    )
