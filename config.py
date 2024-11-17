import os
from dotenv import load_dotenv
from psycopg2 import pool
from cryptography.fernet import Fernet

load_dotenv()

class Config:
    # Decrypt the password
    cipher = Fernet(os.getenv("ENCRYPTION_KEY").encode())
    ENCRYPTED_PASSWORD = os.getenv("ENCRYPTED_PASSWORD").encode()
    DB_PASSWORD = cipher.decrypt(ENCRYPTED_PASSWORD).decode()

    # Database URI
    SQLALCHEMY_DATABASE_URI = f"postgresql://doadmin:{DB_PASSWORD}@db-postgresql-blr1-14444-do-user-18154576-0.i.db.ondigitalocean.com:25060/defaultdb"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Database credentials
    DB_HOST = "db-postgresql-blr1-14444-do-user-18154576-0.i.db.ondigitalocean.com"
    DB_PORT = "25060"
    DB_NAME = "defaultdb"
    DB_USER = "doadmin"

    # Connection pool
    connection_pool = pool.SimpleConnectionPool(
        int(os.getenv("DB_POOL_MIN", 5)),
        int(os.getenv("DB_POOL_MAX", 22)),
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def get_db_connection():
    try:
        return Config.connection_pool.getconn()
    except Exception as e:
        raise RuntimeError("Failed to get a connection from the pool") from e

def release_db_connection(conn):
    try:
        Config.connection_pool.putconn(conn)
    except Exception as e:
        raise RuntimeError("Failed to release a connection back to the pool") from e

def log_pool_status():
    print(f"Total connections: {Config.connection_pool._used}")
    print(f"Idle connections: {Config.connection_pool._idle}")
