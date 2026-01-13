from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    Text
)
from sqlalchemy.orm import relationship

db = SQLAlchemy()

# ============================================================
# USER
# ============================================================
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

    # Canary testing flag
    is_canary_user = db.Column(db.Boolean, default=False)

    # Relationships
    bookings = relationship("Booking", back_populates="user")
    sunday_bookings = relationship("SundayBooking", back_populates="user")

    # Multiple SevaNidhi payments allowed
    seva_nidhi_payments = relationship("SevaNidhiPayment", back_populates="user")

    def __repr__(self):
        return f"<User {self.first_name} {self.last_name}>"


# ============================================================
# BOOKINGS
# ============================================================
class Booking(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey('users.id'), nullable=False)

    booking_date = db.Column(db.Date, nullable=False)
    mahaprasad = db.Column(db.Boolean, default=False)

    created_at = db.Column(DateTime, default=datetime.utcnow)
    updated_date = db.Column(DateTime, onupdate=datetime.utcnow)

    updated_by = db.Column(Integer)
    is_active = db.Column(Boolean, default=True)

    user = relationship("User", back_populates="bookings")


class SundayBooking(db.Model):
    __tablename__ = 'sunday_bookings'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    booking_date = Column(Date, nullable=False)
    mahaprasad = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    updated_by = Column(Integer)
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="sunday_bookings")


# ============================================================
# ZONE
# ============================================================
class Zone(db.Model):
    __tablename__ = 'zone'

    id = Column(Integer, primary_key=True)
    area_name = Column(String(50), nullable=False)
    pincode = Column(String(6), nullable=False, unique=True)
    zone_code = Column(String(20), nullable=False)

    def __repr__(self):
        return f"<Zone {self.zone_code} - {self.area_name}>"


# ============================================================
# FEATURE TOGGLE
# ============================================================
class FeatureToggle(db.Model):
    __tablename__ = 'feature_toggle'

    id = Column(Integer, primary_key=True)
    toggle_name = Column(String(50), unique=True, nullable=False)
    toggle_enabled = Column(Boolean, nullable=False)

    def __repr__(self):
        return f"<FeatureToggle {self.toggle_name}: {self.toggle_enabled}>"


# ============================================================
# REFERENCE DATA
# ============================================================
class ReferenceData(db.Model):
    __tablename__ = 'reference_data'

    id = Column(Integer, primary_key=True)
    reference_key = Column(String, unique=True, nullable=False)
    reference_value = Column(String, nullable=False)

    def __repr__(self):
        return f"<ReferenceData {self.reference_key}: {self.reference_value}>"


# ============================================================
# BOOKING LOCK
# ============================================================
class BookingLock(db.Model):
    __tablename__ = "booking_locks"

    id = Column(Integer, primary_key=True)
    booking_date = Column(Date, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# JANMOTSAV YEAR
# ============================================================
class JanmotsavYear(db.Model):
    __tablename__ = "janmotsav_years"

    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False, unique=True)

    is_current = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    is_locked = Column(Boolean, default=False)
    is_event_closed = Column(Boolean, default=False)

    event_name = Column(String(255))
    location_name = Column(String(255))
    location_url = Column(String(500))

    facebook_url = Column(String(500))
    youtube_url = Column(String(500))
    instagram_url = Column(String(500))

    custom_link_1 = Column(String(500))
    custom_link_2 = Column(String(500))

    description = Column(Text)

    upi_id = Column(String(150))
    upi_name = Column(String(150))
    upi_note = Column(String(255))
    upi_min_amount = Column(Numeric(10, 2))
    upi_status = Column(Boolean, default=True)

    enable_payment_flag = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    days = relationship("JanmotsavDay", back_populates="year_info")
    attendance = relationship("JanmotsavAttendance", back_populates="year_info")
    seva_nidhi_payments = relationship("SevaNidhiPayment", back_populates="year")
    payments = relationship("YearPaymentTracking", back_populates="year")

    def __repr__(self):
        return f"<JanmotsavYear {self.year}>"


# ============================================================
# JANMOTSAV DAY
# ============================================================
class JanmotsavDay(db.Model):
    __tablename__ = "janmotsav_days"

    id = Column(Integer, primary_key=True)
    year_id = Column(Integer, ForeignKey("janmotsav_years.id"), nullable=False)

    event_date = Column(Date, nullable=False)

    breakfast = Column(Boolean, default=False)
    lunch = Column(Boolean, default=False)
    evesnacks = Column(Boolean, default=False)
    dinner = Column(Boolean, default=False)

    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    year_info = relationship("JanmotsavYear", back_populates="days")
    attendance = relationship("JanmotsavAttendance", back_populates="day_info")

    def __repr__(self):
        return f"<JanmotsavDay {self.event_date}>"


# ============================================================
# MULTIPLE SEVA NIDHI PAYMENTS (NEW)
# ============================================================
class SevaNidhiPayment(db.Model):
    __tablename__ = "seva_nidhi_payments"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    year_id = Column(Integer, ForeignKey("janmotsav_years.id"), nullable=False)

    amount = Column(Integer, nullable=False)
    account_details = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="seva_nidhi_payments")
    year = relationship("JanmotsavYear", back_populates="seva_nidhi_payments")

    def __repr__(self):
        return f"<SevaNidhiPayment user={self.user_id} year={self.year_id} amount={self.amount}>"


# ============================================================
# ATTENDANCE (CLEANED)
# ============================================================
class JanmotsavAttendance(db.Model):
    __tablename__ = "janmotsav_attendance"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    year_id = Column(Integer, ForeignKey("janmotsav_years.id"), nullable=False)
    day_id = Column(Integer, ForeignKey("janmotsav_days.id"), nullable=False)

    breakfast_count = Column(Integer, default=0)
    lunch_count = Column(Integer, default=0)
    evesnacks_count = Column(Integer, default=0)
    dinner_count = Column(Integer, default=0)

    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    year_info = relationship("JanmotsavYear", back_populates="attendance")
    day_info = relationship("JanmotsavDay", back_populates="attendance")

    def __repr__(self):
        return f"<Attendance user={self.user_id} day={self.day_id}>"


# ============================================================
# YEAR PAYMENT TRACKING
# ============================================================
class YearPaymentTracking(db.Model):
    __tablename__ = "year_payment_tracking"

    id = Column(Integer, primary_key=True)
    year_id = Column(Integer, ForeignKey("janmotsav_years.id"), nullable=False)
    user_id = Column(Integer, nullable=False)

    amount = Column(Numeric(10, 2))
    status = Column(String(20))      # SUCCESS / FAILURE
    txn_id = Column(String(120))
    utr = Column(String(120))
    response_code = Column(String(10))
    raw_response = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    year = relationship("JanmotsavYear", back_populates="payments")

    def __repr__(self):
        return f"<PaymentTracking {self.status} - {self.amount}>"
