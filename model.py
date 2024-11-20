from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize the SQLAlchemy instance
db = SQLAlchemy()

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
    zone_code = db.Column(db.String(50), nullable=False)  # Add zone column
    
    # Relationship with Booking
    bookings = db.relationship('Booking', back_populates='user')
    
class Booking(db.Model):
    __tablename__ = 'bookings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    mahaprasad = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_date = db.Column(db.DateTime, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, nullable=True)

    user = db.relationship('User', back_populates='bookings')

class Zone(db.Model):
    __tablename__ = 'Zone'
    
    id = db.Column(db.Integer, primary_key=True)
    area_name = db.Column(db.String(50), nullable=False)
    pincode = db.Column(db.String(6), nullable=False, unique=True)
    zone_code = db.Column(db.String(20), nullable=False)  # Zone A, B, or C


    # Add a string representation for better debugging
    def __repr__(self):
        return f"<Booking {self.id}, User {self.user_id}, Date {self.booking_date}, Zone {self.zone}>"

class FeatureToggle(db.Model):
    __tablename__ = 'feature_toggle'

    id = db.Column(db.Integer, primary_key=True)
    toggle_name = db.Column(db.String(50), unique=True, nullable=False)
    toggle_enabled = db.Column(db.Boolean, nullable=False)  # Corrected typo here

    def __repr__(self):
        return f"<FeatureToggle {self.toggle_name}: {self.toggle_enabled}>"