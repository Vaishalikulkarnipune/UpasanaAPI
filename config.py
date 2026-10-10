import os
import logging
from dotenv import load_dotenv
from psycopg2 import pool

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
LOCAL_DB_HOSTS = ("localhost", "127.0.0.1", "::1")


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Never commit passwords here. Local dev sets DB_HOST=localhost and
    # DB_PASSWORD in .env (gitignored); production uses the encrypted password.
    if os.getenv("DB_HOST") in LOCAL_DB_HOSTS:
        DB_HOST = os.getenv("DB_HOST")
        DB_PORT = os.getenv("DB_PORT", "5432")
        DB_USER = os.getenv("DB_USER", "postgres")
        DB_PASSWORD = os.getenv("DB_PASSWORD", "")
        DB_NAME = os.getenv("DB_NAME", "upasana local db")

        # Real dbname goes via connect_args because it contains spaces.
        SQLALCHEMY_DATABASE_URI = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/postgres"
        SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"dbname": DB_NAME}}

        connection_pool = pool.SimpleConnectionPool(
            1, 22,
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME,
        )
    else:
        from cryptography.fernet import Fernet

        DB_HOST = "db-postgresql-blr1-14444-do-user-18154576-0.i.db.ondigitalocean.com"

        # Load the encryption key and encrypted password from environment variables
        cipher = Fernet(os.getenv("ENCRYPTION_KEY").encode())
        ENCRYPTED_PASSWORD = os.getenv("ENCRYPTED_PASSWORD").encode()

        # Decrypt the password
        DB_PASSWORD = cipher.decrypt(ENCRYPTED_PASSWORD).decode()

        # Use the connection pool URI for upasanadbpool
        SQLALCHEMY_DATABASE_URI = f"postgresql://doadmin:{DB_PASSWORD}@{DB_HOST}:25060/defaultdb?sslmode=require&application_name=upasanadbpool"
        SQLALCHEMY_ENGINE_OPTIONS = {}

        CONNECTION_POOL_URI = SQLALCHEMY_DATABASE_URI
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
