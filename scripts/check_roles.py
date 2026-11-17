"""Week 3 proof that app_reader can read and nothing else. Run it from the project folder:

    python scripts/check_roles.py

Connects as app_reader (APP_DATABASE_URL) and tries three statements:
  1. a SELECT, which should work;
  2. a DELETE, which should fail with "permission denied";
  3. an INSERT, which should fail with "permission denied".

Each statement runs inside a transaction that is always rolled back, so even if a
permission were wrong, nothing would be saved. Never prints the connection string.
"""

import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()

CHECKS = [
    ("SELECT should work", "select count(*) from students", True),
    ("DELETE should fail", "delete from students where student_id = 1", False),
    ("INSERT should fail",
     "insert into departments (department_code, department_name, students_only) "
     "values ('TEST', 'Permission test', false)", False),
]

url = os.environ.get("APP_DATABASE_URL")
if not url:
    sys.exit("[FAIL] APP_DATABASE_URL is not set. Add it to your .env file (see .env.example).")

try:
    conn = psycopg.connect(url, connect_timeout=10)
except psycopg.OperationalError as error:
    print("[FAIL] Could not connect using APP_DATABASE_URL.")
    sys.exit(f"       {str(error).strip().splitlines()[0]}")

passed = 0
with conn:
    user = conn.execute("select current_user").fetchone()[0]
    conn.rollback()
    print(f"Connected as database user: {user}\n")

    for label, statement, should_work in CHECKS:
        print(f"-- {label}")
        print(f"{statement};")
        try:
            result = conn.execute(statement)
            rows = result.fetchall() if result.description else []
            outcome = f"OK: {rows[0][0]} rows" if rows else "OK"
            worked = True
        except psycopg.errors.InsufficientPrivilege as error:
            outcome = f"ERROR: {str(error).strip().splitlines()[0]}"
            worked = False
        finally:
            conn.rollback()  # never keep anything, whatever happened

        ok = worked == should_work
        passed += ok
        print(f"{outcome}")
        print(f"[{'ok' if ok else 'FAIL'}] {'as expected' if ok else 'NOT as expected'}\n")

print(f"{passed} of {len(CHECKS)} checks behaved as expected.")
if user != "app_reader":
    print("[FAIL] Not connected as app_reader. Check the user name in APP_DATABASE_URL.")
    sys.exit(1)
sys.exit(0 if passed == len(CHECKS) else 1)
