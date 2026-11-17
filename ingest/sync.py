"""Week 3 sync: fetch what's new from Mockaroo and merge it into the database, logging every run.

Run it from the project folder:

    python ingest/sync.py                                  # a manual run
    python ingest/sync.py --trigger schedule               # what GitHub Actions runs
    python ingest/sync.py --replay data/raw/sync/run_0001.json   # reload a saved fetch, no API calls

Each run does three things:
  1. Logs the run. A sync_runs row saying 'failed' / 'run did not finish' is committed first,
     on its own, and updated at the end. A run that dies partway leaves that row behind.
  2. Fetches two batches from Mockaroo and saves them to data/raw/sync/run_NNNN.json:
       * new students (default 25), with IDs continuing after the highest student_id in the
         database (the watermark), all entering in Winter 2026;
       * a change feed (default 40) of existing students with new values for the only two fields
         that can change: mentoring_need and mentor_faculty_id. A missing mentor means the
         student's mentor was removed.
  3. Merges both batches in one transaction: if any step fails, no data changes are saved.
       * New students: insert, skipping any that are already there.
       * Changes: update only values that are actually different, so last_updated_at moves
         only when something really changed.

Idempotent: running --replay on the latest run's file inserts 0 and updates 0, because every
row it would write is already there with the same values.

Connects as the database owner (DATABASE_URL). Never prints the connection string or API key.
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from fetch import QuotaExceeded, check_records, get_api_key, request_rows
from load import term_start
from schemas import MENTORING_FOCUS, change_fields, new_student_fields

PROJECT = Path(__file__).resolve().parent.parent
SYNC_DIR = PROJECT / "data" / "raw" / "sync"

DELAY_SECONDS = 1.5  # pause between the two Mockaroo requests

log = logging.getLogger("sync")


# ---------------------------------------------------------------- the sync_runs log

def start_run(conn, trigger):
    """Insert this run's log row and commit it at once (conn is in autocommit mode)."""
    return conn.execute(
        """insert into sync_runs (status, error_message, trigger)
           values ('failed', 'run did not finish', %s) returning run_id""",
        (trigger,),
    ).fetchone()[0]


def finish_run(conn, run_id, status, counts, message):
    conn.execute(
        """update sync_runs
           set finished_at = now(), status = %s, records_fetched = %s,
               records_inserted = %s, records_updated = %s, error_message = %s
           where run_id = %s""",
        (status, counts["fetched"], counts["inserted"], counts["updated"], message, run_id),
    )


# ---------------------------------------------------------------- fetching

def fetch_batches(new_count, change_count, watermark, existing_ids):
    """Ask Mockaroo for new students and a change feed. Returns (batch, problems).

    batch["new_students"] or batch["changes"] is None when that request failed.
    """
    session = requests.Session()
    session.headers["X-API-Key"] = get_api_key()  # a header, never the URL
    problems = []
    batch = {"watermark": watermark, "new_students": None, "changes": None}

    try:
        log.info("fetching %d new students (IDs %d-%d)", new_count, watermark + 1,
                 watermark + new_count)
        batch["new_students"] = request_rows(session, new_student_fields(watermark + 1), new_count)
        if batch["new_students"] is None:
            problems.append("new-student request failed")

        # Pick which existing students "changed" this time; Mockaroo supplies their new values.
        chosen = random.sample(sorted(existing_ids), min(change_count, len(existing_ids)))
        time.sleep(DELAY_SECONDS)
        log.info("fetching change feed for %d existing students", len(chosen))
        batch["changes"] = request_rows(session, change_fields(chosen), len(chosen))
        if batch["changes"] is None:
            problems.append("change-feed request failed")
    except QuotaExceeded as exc:
        problems.append(f"Mockaroo daily limit reached: {exc}")
    return batch, problems


def valid_changes(rows):
    """Drop change records that aren't usable. Returns (good_rows, number_dropped)."""
    good = []
    for row in rows:
        mentor = row.get("mentor_faculty_id")
        if (isinstance(row.get("student_id"), int)
                and row.get("mentoring_need") in MENTORING_FOCUS
                and (mentor is None or isinstance(mentor, int))):
            good.append(row)
        else:
            log.warning("change record unusable, skipped: %s", row)
    return good, len(rows) - len(good)


# ---------------------------------------------------------------- merging

def insert_new_students(cur, students, existing_ids):
    """Insert new students and their mentors. Returns (inserted, skipped)."""
    inserted = skipped = 0
    for s in students:
        # "on conflict do nothing" with no column named covers every unique rule:
        # a student_id that's already there (a replay) or an email another student has.
        cur.execute(
            """insert into students (student_id, first_name, last_name, email, department_code,
                                     program_name, entry_term, entry_term_start, first_generation,
                                     athlete, mentoring_need, preferred_meeting, raw)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict do nothing""",
            (s["student_id"], s["first_name"], s["last_name"], s["email"], s["department"],
             s["subject_area"], s["entry_term"], term_start(s["entry_term"]),
             s["first_generation"], s["athlete"], s["mentoring_need"], s["preferred_meeting"],
             Jsonb(s)),
        )
        if cur.rowcount == 0:
            if s["student_id"] not in existing_ids:
                # Not a replay, so the email must already belong to someone else.
                log.warning("student %s not added: email %s is already taken",
                            s["student_id"], s["email"])
                skipped += 1
            continue
        inserted += 1
        if s.get("mentor_faculty_id") is not None:
            cur.execute(
                """insert into mentor_assignments (student_pk, faculty_pk)
                   select s.student_pk, f.faculty_pk
                   from students s, faculty f
                   where s.student_id = %s and f.faculty_id = %s""",
                (s["student_id"], s["mentor_faculty_id"]),
            )
    return inserted, skipped


def apply_changes(cur, changes):
    """Apply the change feed. Returns (students_updated, detail counts)."""
    detail = {"need changed": 0, "mentor added": 0, "mentor switched": 0, "mentor removed": 0,
              "unknown student": 0, "unknown mentor": 0}
    updated = 0
    for c in changes:
        current = cur.execute(
            """select s.student_pk, f.faculty_id
               from students s
               left join mentor_assignments m on m.student_pk = s.student_pk
               left join faculty f on f.faculty_pk = m.faculty_pk
               where s.student_id = %s""",
            (c["student_id"],),
        ).fetchone()
        if current is None:
            log.warning("change for unknown student %s skipped", c["student_id"])
            detail["unknown student"] += 1
            continue
        student_pk, old_mentor = current
        new_mentor = c.get("mentor_faculty_id")
        changed = False

        # The WHERE ... is distinct from ... part makes this a no-op when the value is the same,
        # so last_updated_at isn't touched.
        cur.execute(
            """update students set mentoring_need = %s, last_updated_at = now()
               where student_pk = %s and mentoring_need is distinct from %s""",
            (c["mentoring_need"], student_pk, c["mentoring_need"]),
        )
        if cur.rowcount:
            detail["need changed"] += 1
            changed = True

        if new_mentor is None:
            cur.execute("delete from mentor_assignments where student_pk = %s", (student_pk,))
            if cur.rowcount:
                log.info("student %s: mentor %s removed, back to waiting", c["student_id"], old_mentor)
                detail["mentor removed"] += 1
                changed = True
        else:
            # Upsert: add a row if the student has no mentor, otherwise switch the mentor,
            # but only if it's a different one.
            cur.execute(
                """insert into mentor_assignments (student_pk, faculty_pk)
                   select %s, faculty_pk from faculty where faculty_id = %s
                   on conflict (student_pk) do update
                       set faculty_pk = excluded.faculty_pk, last_updated_at = now()
                       where mentor_assignments.faculty_pk is distinct from excluded.faculty_pk""",
                (student_pk, new_mentor),
            )
            if cur.rowcount:
                detail["mentor added" if old_mentor is None else "mentor switched"] += 1
                changed = True
            elif old_mentor != new_mentor:
                log.warning("student %s: mentor %s is not a known faculty_id, skipped",
                            c["student_id"], new_mentor)
                detail["unknown mentor"] += 1

        updated += changed
    return updated, detail


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--new", type=int, default=25, help="new students to fetch")
    parser.add_argument("--changes", type=int, default=40, help="existing students to change")
    parser.add_argument("--trigger", choices=["manual", "schedule"], default="manual")
    parser.add_argument("--replay", type=Path, help="merge a saved run file instead of fetching")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    load_dotenv(PROJECT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("[FAIL] DATABASE_URL is not set. Add it to .env (see .env.example).")

    counts = {"fetched": 0, "inserted": 0, "updated": 0}
    problems = []
    try:
        # Autocommit: each statement saves on its own, except inside conn.transaction() below.
        with psycopg.connect(url, connect_timeout=10, autocommit=True) as conn:
            run_id = start_run(conn, args.trigger)
            log.info("run %d started (%s)", run_id, args.trigger)
            status = "failed"
            message = None
            try:
                existing_ids = {r[0] for r in conn.execute("select student_id from students")}
                watermark = max(existing_ids, default=0)

                if args.replay:
                    batch = json.loads(args.replay.read_text(encoding="utf-8"))
                    log.info("replaying %s (no API calls)", args.replay)
                else:
                    batch, problems = fetch_batches(args.new, args.changes, watermark, existing_ids)
                    batch.update(run_id=run_id, fetched_at=datetime.now(timezone.utc).isoformat())
                    SYNC_DIR.mkdir(parents=True, exist_ok=True)
                    path = SYNC_DIR / f"run_{run_id:04d}.json"
                    path.write_text(json.dumps(batch, indent=2), encoding="utf-8")
                    log.info("saved raw fetch to %s", path.relative_to(PROJECT))

                new_students = batch.get("new_students") or []
                changes = batch.get("changes") or []
                counts["fetched"] = len(new_students) + len(changes)

                # Records with missing fields or Mockaroo error values are left out.
                good = [s for s in new_students if check_records("students", [s]) == 0]
                changes, dropped = valid_changes(changes)
                dropped += len(new_students) - len(good)
                new_students = good
                if dropped:
                    problems.append(f"{dropped} unusable records skipped")

                with conn.transaction():  # all of the merge, or none of it
                    cur = conn.cursor()
                    inserted, skipped = insert_new_students(cur, new_students, existing_ids)
                    updated, detail = apply_changes(cur, changes)
                counts.update(inserted=inserted, updated=updated)
                if skipped:
                    problems.append(f"{skipped} new students skipped (email already taken)")
                if detail["unknown student"] or detail["unknown mentor"]:
                    problems.append(f"{detail['unknown student']} unknown students, "
                                    f"{detail['unknown mentor']} unknown mentors in change feed")

                log.info("changes: %s", ", ".join(f"{v} {k}" for k, v in detail.items()))
                if counts["fetched"] == 0 and problems:
                    status = "failed"
                else:
                    status = "partial" if problems else "success"
                message = "; ".join(problems) or None
            except (psycopg.Error, OSError, ValueError, KeyError) as error:
                status = "failed"
                message = f"{type(error).__name__}: {str(error).strip().splitlines()[0]}"[:500]
                counts.update(inserted=0, updated=0)  # the transaction rolled back
                log.error("run failed, no data changes saved: %s", message)
            finish_run(conn, run_id, status, counts, message)
    except psycopg.Error as error:
        # Couldn't connect, or couldn't write the log row.
        sys.exit(f"[FAIL] database problem: {str(error).strip().splitlines()[0]}")

    print(f"\nrun {run_id}: {status}  fetched {counts['fetched']}, "
          f"inserted {counts['inserted']}, updated {counts['updated']}"
          + (f"\n  note: {message}" if message else ""))
    if status == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
