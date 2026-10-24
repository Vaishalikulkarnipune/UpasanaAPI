"""
Create the admin account, or change its password.

    python create_admin.py            asks for mobile, name and password; prints the SQL to run
    python create_admin.py --apply    same, and runs it on the database in .env

The password is only ever stored hashed. Run the printed SQL on production after
migrations/add_admin_accounts.sql (or after the API has started once, which creates the tables).
Changing the password also logs the admin out everywhere.
"""
import getpass
import os
import sys

from werkzeug.security import generate_password_hash


def main():
    mobile = (os.environ.get("ADMIN_MOBILE") or input("Admin mobile number: ")).strip()
    name = (os.environ.get("ADMIN_NAME") or input("Admin name [Admin]: ")).strip() or "Admin"
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("New admin password: ")
    if not os.environ.get("ADMIN_PASSWORD") and password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    if len(password) < 8:
        sys.exit("Use at least 8 characters.")

    pw_hash = generate_password_hash(password)
    sql = (
        "INSERT INTO admin_accounts (mobile_number, name, password_hash, is_active)\n"
        f"VALUES ('{mobile}', '{name.replace(chr(39), chr(39) * 2)}', '{pw_hash}', TRUE)\n"
        "ON CONFLICT (mobile_number) DO UPDATE\n"
        "   SET name = EXCLUDED.name, password_hash = EXCLUDED.password_hash, is_active = TRUE;\n"
        f"DELETE FROM admin_sessions WHERE admin_id = (SELECT id FROM admin_accounts WHERE mobile_number = '{mobile}');\n"
    )
    print("\n-- Run this SQL:\n" + sql)

    if "--apply" in sys.argv:
        import psycopg2
        from dotenv import load_dotenv
        load_dotenv()
        conn = psycopg2.connect(host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"), user=os.getenv("DB_USER"),
                                password=os.getenv("DB_PASSWORD"), dbname=os.getenv("DB_NAME"))
        with conn, conn.cursor() as cur:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from admin_auth import SCHEMA
            for ddl in SCHEMA:
                cur.execute(ddl)
            cur.execute(sql)
        conn.close()
        print(f"Applied to {os.getenv('DB_NAME')}.")


if __name__ == "__main__":
    main()
