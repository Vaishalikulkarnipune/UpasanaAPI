import os
from dotenv import load_dotenv
from psycopg2 import pool
from cryptography.fernet import Fernet

load_dotenv()  # Load environment variables from .env file

class Config:
    # Load the encryption key and encrypted password from environment variables
    cipher = Fernet(os.getenv("ENCRYPTION_KEY").encode())
    ENCRYPTED_PASSWORD = os.getenv("ENCRYPTED_PASSWORD").encode()
    
    # Decrypt the password
    DB_PASSWORD = cipher.decrypt(ENCRYPTED_PASSWORD).decode()
    
    SQLALCHEMY_DATABASE_URI = f"postgresql://doadmin:{DB_PASSWORD}@db-postgresql-blr1-14444-do-user-18154576-0.i.db.ondigitalocean.com:25060/defaultdb"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Database configuration
    DB_HOST = "db-postgresql-blr1-14444-do-user-18154576-0.i.db.ondigitalocean.com"
    DB_PORT = "25060"
    DB_NAME = "defaultdb"
    DB_USER = "doadmin"
    DB_PASSWORD = DB_PASSWORD

    # Create connection pool for better performance
    connection_pool = pool.SimpleConnectionPool(
        1, 20,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

# Function to get a connection from the connection pool
def get_db_connection():
    return Config.connection_pool.getconn()

# Function to release a connection back to the pool
def release_db_connection(conn):
    Config.connection_pool.putconn(conn)
