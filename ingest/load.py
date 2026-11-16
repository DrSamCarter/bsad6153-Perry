"""Week 2 loader: turns the raw Mockaroo JSON in data/raw/ into rows in the database.

Run it from the project folder:

    python ingest/load.py                  # load data/raw/ into the tables
    python ingest/load.py --create-schema  # first run db/schema.sql, then load

Rules it follows:
  * Parents before children: lookups, then faculty and students, then the link tables,
    so every foreign key already has a row to point at.
  * Every value goes in through a %s placeholder (parameterized query). No SQL is ever
    built by gluing strings together.
  * Running it twice adds nothing the second time: every insert is ON CONFLICT DO NOTHING.
    (Week 3 upgrades this to update rows that changed.)
  * Everything happens in one transaction: if any step fails, nothing is saved.

Connects as the database owner (DATABASE_URL). Never prints the connection string.
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.types.json import Jsonb

from schemas import DEPARTMENTS, MENTORING_FOCUS, STUDENT_SUBJECTS

PROJECT = Path(__file__).resolve().parent.parent
RAW = PROJECT / "data" / "raw"
SCHEMA_FILE = PROJECT / "db" / "schema.sql"

TABLES = ["departments", "programs", "mentoring_focus_areas", "faculty", "students",
          "faculty_focus_areas", "faculty_subjects", "mentor_assignments"]

# First day of each kind of term (an assumption: adjust to the college calendar).
TERM_START = {"Spring": (1, 15), "Summer": (6, 1), "Fall": (8, 20)}


def term_start(entry_term):
    """'Fall 2025' -> date(2025, 8, 20)."""
    season, year = entry_term.split()
    month, day = TERM_START[season]
    return date(int(year), month, day)


def read_raw():
    faculty = json.loads((RAW / "faculty.json").read_text(encoding="utf-8"))
    students = []
    for path in sorted(RAW.glob("students_batch_*.json")):
        students.extend(json.loads(path.read_text(encoding="utf-8")))
    return faculty, students


def count_rows(cur):
    # Table names come from the fixed TABLES list above, never from input,
    # and sql.Identifier quotes them safely.
    counts = {}
    for table in TABLES:
        query = sql.SQL("select count(*) from {}").format(sql.Identifier(table))
        counts[table] = cur.execute(query).fetchone()[0]
    return counts


def load(conn, faculty, students):
    """Insert everything. Returns row counts before and after, per table."""
    cur = conn.cursor()
    before = count_rows(cur)

    # 1. Lookups (no parents).
    departments = [(code, name, False) for code, name in DEPARTMENTS.items()]
    departments.append(("UND", "Undeclared", True))
    cur.executemany(
        """insert into departments (department_code, department_name, students_only)
           values (%s, %s, %s) on conflict (department_code) do nothing""",
        departments,
    )
    cur.executemany(
        """insert into programs (program_name, department_code)
           values (%s, %s) on conflict (program_name) do nothing""",
        [(program, code) for code, programs in STUDENT_SUBJECTS.items() for program in programs],
    )
    cur.executemany(
        """insert into mentoring_focus_areas (focus_area)
           values (%s) on conflict (focus_area) do nothing""",
        [(focus,) for focus in MENTORING_FOCUS],
    )

    # 2. Entities (parents: departments, programs, focus areas).
    cur.executemany(
        """insert into faculty (faculty_id, first_name, last_name, email, department_code,
                                willing_to_mentor, max_mentees, years_at_institution, raw)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           on conflict (faculty_id) do nothing""",
        [(f["faculty_id"], f["first_name"], f["last_name"], f["email"], f["department"],
          f["willing_to_mentor"], f["max_mentees"], f["years_at_institution"], Jsonb(f))
         for f in faculty],
    )
    cur.executemany(
        """insert into students (student_id, first_name, last_name, email, department_code,
                                 program_name, entry_term, entry_term_start, first_generation,
                                 athlete, mentoring_need, preferred_meeting, raw)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           on conflict (student_id) do nothing""",
        [(s["student_id"], s["first_name"], s["last_name"], s["email"], s["department"],
          s["subject_area"], s["entry_term"], term_start(s["entry_term"]),
          s["first_generation"], s["athlete"], s["mentoring_need"], s["preferred_meeting"],
          Jsonb(s))
         for s in students],
    )

    # 3. Relationships (parents: faculty, students). Mockaroo IDs are looked up to the
    #    database's own keys inside the query.
    cur.executemany(
        """insert into faculty_focus_areas (faculty_pk, focus_area)
           select faculty_pk, %s from faculty where faculty_id = %s
           on conflict (faculty_pk, focus_area) do nothing""",
        [(f["mentoring_focus"], f["faculty_id"]) for f in faculty],
    )
    cur.executemany(
        """insert into faculty_subjects (faculty_pk, program_name)
           select faculty_pk, %s from faculty where faculty_id = %s
           on conflict (faculty_pk, program_name) do nothing""",
        [(f["subject_area"], f["faculty_id"]) for f in faculty],
    )
    # About 30% of students have no mentor: Mockaroo leaves the key out, so they get no row.
    pairs = [(s["student_id"], s["mentor_faculty_id"]) for s in students
             if s.get("mentor_faculty_id") is not None]
    cur.executemany(
        """insert into mentor_assignments (student_pk, faculty_pk)
           select s.student_pk, f.faculty_pk
           from students s, faculty f
           where s.student_id = %s and f.faculty_id = %s
           on conflict (student_pk) do nothing""",
        pairs,
    )

    return before, count_rows(cur)


def main():
    parser = argparse.ArgumentParser(description="Load data/raw/ into the database.")
    parser.add_argument("--create-schema", action="store_true",
                        help="run db/schema.sql before loading")
    args = parser.parse_args()

    load_dotenv(PROJECT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("[FAIL] DATABASE_URL is not set. Add it to .env (see .env.example).")

    faculty, students = read_raw()
    print(f"Read {len(faculty)} faculty and {len(students)} students from {RAW.name}/")

    try:
        with psycopg.connect(url, connect_timeout=10) as conn:  # commits on success
            if args.create_schema:
                conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
                print("Ran db/schema.sql")
            before, after = load(conn, faculty, students)
    except psycopg.Error as error:
        sys.exit(f"[FAIL] Load stopped and nothing was saved: {str(error).strip().splitlines()[0]}")

    print(f"\n{'table':<24}{'before':>8}{'added':>8}{'total':>8}")
    for table in TABLES:
        print(f"{table:<24}{before[table]:>8}{after[table] - before[table]:>8}{after[table]:>8}")
    added = sum(after[t] - before[t] for t in TABLES)
    print("\n[ok] Load finished." + (" No new rows: nothing was duplicated." if added == 0 else ""))


if __name__ == "__main__":
    main()
