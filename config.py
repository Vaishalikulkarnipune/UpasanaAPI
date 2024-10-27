import psycopg2
from psycopg2 import pool

class Config:
    SQLALCHEMY_DATABASE_URI = "postgresql://postgres:admin123@localhost/Upasana"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Database configurationclear
    DB_HOST = "localhost"
    DB_PORT = "5432"
    DB_NAME = "Upasana"
    DB_USER = "postgres"
    #Donot change and commit this password
    DB_PASSWORD = "admin123"
    # Create connection pool for better performance
    connection_pool = pool.SimpleConnectionPool(1, 20,
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