import os
import logging
from dotenv import load_dotenv
from psycopg2 import pool
from cryptography.fernet import Fernet

load_dotenv()  # Load environment variables from .env file

# Configure logging for database connections
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("config.log"),
        logging.StreamHandler()
    ]
)
class Config:
    # Load the encryption key and encrypted password from environment variables
    cipher = Fernet(os.getenv("ENCRYPTION_KEY").encode())
    ENCRYPTED_PASSWORD = os.getenv("ENCRYPTED_PASSWORD").encode()
    
    # Decrypt the password
    DB_PASSWORD = cipher.decrypt(ENCRYPTED_PASSWORD).decode()
    
    # Use the connection pool URI for upasanadbpool
    SQLALCHEMY_DATABASE_URI = f"postgresql://doadmin:{DB_PASSWORD}@db-postgresql-blr1-14444-do-user-18154576-0.i.db.ondigitalocean.com:25060/defaultdb?sslmode=require&application_name=upasanadbpool"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Connection Pool Configuration (use pool URI directly)
    CONNECTION_POOL_URI = f"postgresql://doadmin:{DB_PASSWORD}@db-postgresql-blr1-14444-do-user-18154576-0.i.db.ondigitalocean.com:25060/defaultdb?sslmode=require&application_name=upasanadbpool"

    # Create connection pool using the connection pool URI
    connection_pool = pool.SimpleConnectionPool(
        1, 22,  # Adjust maxconn as needed
        dsn=CONNECTION_POOL_URI
    )

# Function to get a connection from the connection pool
def get_db_connection():
   #logging.info("Acquiring a connection from the pool.")
    return Config.connection_pool.getconn()

# Function to release a connection back to the pool
def release_db_connection(conn):
    #logging.info("Releasing the connection back to the pool.")
    Config.connection_pool.putconn(conn)