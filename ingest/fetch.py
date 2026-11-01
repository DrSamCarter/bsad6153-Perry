"""Fetch fake faculty and student records from the Mockaroo API and save the raw JSON.

Run from the project folder:  python ingest/fetch.py
Options:  --students 500  --batch-size 100  --faculty 60  --delay 1.5

Mockaroo doesn't page through stored data; every request generates new rows. So "pagination" here
means asking for the students in batches, with IDs that continue from one batch to the next.
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from schemas import FACULTY_COUNT, FACULTY_FIELDS, student_fields

API_URL = "https://api.mockaroo.com/api/generate.json"
PROJECT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT / "data" / "raw"
SAMPLE_DIR = PROJECT / "data" / "sample"

TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 5          # per request, counting the first try
BACKOFF_SECONDS = 2       # doubles after each failed attempt: 2, 4, 8, 16

# Fields every record must have. mentor_faculty_id is optional: Mockaroo leaves the key out
# entirely when a student has no mentor yet.
REQUIRED = {
    "faculty": ["faculty_id", "first_name", "last_name", "email", "department", "subject_area",
                "willing_to_mentor", "max_mentees"],
    "students": ["student_id", "first_name", "last_name", "email", "department", "subject_area",
                 "entry_term"],
}

log = logging.getLogger("fetch")


class QuotaExceeded(Exception):
    """The daily Mockaroo limit is used up. Retrying won't help until it resets."""


def get_api_key():
    load_dotenv(PROJECT / ".env")
    key = os.getenv("MOCKAROO_API_KEY")
    if not key:
        sys.exit("MOCKAROO_API_KEY is missing. Add it to .env (see .env.example).")
    return key


def request_rows(session, fields, count):
    """POST one batch request, retrying timeouts, 429s and 5xx errors with exponential backoff.

    Returns the list of rows, or None if every attempt failed. Raises QuotaExceeded if the
    daily limit is reached.
    """
    wait = BACKOFF_SECONDS
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = session.post(API_URL, params={"count": count}, json=fields, timeout=TIMEOUT_SECONDS)
        except (requests.Timeout, requests.ConnectionError) as exc:
            log.warning("attempt %d/%d: network problem (%s)", attempt, MAX_ATTEMPTS, type(exc).__name__)
        else:
            if resp.status_code == 200:
                rows = resp.json()
                # Asking for one row returns a single object rather than a list.
                return rows if isinstance(rows, list) else [rows]

            message = resp.text[:200]
            # The docs don't say which status means "daily limit reached", so check the message too.
            if "limit" in message.lower() and resp.status_code != 429:
                raise QuotaExceeded(f"HTTP {resp.status_code}: {message}")
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = max(wait, int(retry_after))
                log.warning("attempt %d/%d: 429 Too Many Requests", attempt, MAX_ATTEMPTS)
            elif resp.status_code >= 500:
                log.warning("attempt %d/%d: server error %d", attempt, MAX_ATTEMPTS, resp.status_code)
            else:
                # Other 4xx errors (bad key, bad schema) won't fix themselves, so don't retry.
                log.error("request rejected, HTTP %d: %s", resp.status_code, message)
                return None

        if attempt < MAX_ATTEMPTS:
            log.info("waiting %d seconds before retrying", wait)
            time.sleep(wait)
            wait *= 2
    log.error("giving up after %d attempts", MAX_ATTEMPTS)
    return None


def check_records(kind, rows):
    """Count records with missing fields or Mockaroo error values. Returns the number of problems."""
    id_field = REQUIRED[kind][0]
    problems = 0
    for row in rows:
        missing = [f for f in REQUIRED[kind] if f not in row or row[f] in (None, "")]
        errors = [f for f, v in row.items() if isinstance(v, str) and v.startswith("error:")]
        if missing or errors:
            problems += 1
            log.warning("%s record %s: missing %s, error values in %s", kind, row.get(id_field, "?"),
                        missing or "none", errors or "none")
    return problems


def save(path, rows):
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    log.info("saved %d records to %s", len(rows), path.relative_to(PROJECT))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--students", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--faculty", type=int, default=FACULTY_COUNT)
    parser.add_argument("--delay", type=float, default=1.5, help="seconds to wait between requests")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    # The key goes in a header, not the URL, so it never shows up in logs or error messages.
    session.headers["X-API-Key"] = get_api_key()

    summary = {"requests": 0, "failed_batches": 0, "faculty": 0, "students": 0, "problem_records": 0}
    try:
        # Faculty first: students' mentor_faculty_id values point at these IDs.
        log.info("fetching %d faculty", args.faculty)
        summary["requests"] += 1
        faculty = request_rows(session, FACULTY_FIELDS, args.faculty)
        if faculty is None:
            sys.exit("Could not fetch faculty; stopping, because students depend on them.")
        summary["faculty"] = len(faculty)
        summary["problem_records"] += check_records("faculty", faculty)
        save(RAW_DIR / "faculty.json", faculty)

        # Students in batches. Each batch's IDs continue where the last batch ended.
        batches = range(0, args.students, args.batch_size)
        for number, offset in enumerate(batches, start=1):
            count = min(args.batch_size, args.students - offset)
            time.sleep(args.delay)  # be polite: never fire requests back to back
            log.info("fetching students batch %d of %d (IDs %d-%d)",
                     number, len(batches), offset + 1, offset + count)
            summary["requests"] += 1
            rows = request_rows(session, student_fields(offset + 1, len(faculty)), count)
            if rows is None:
                summary["failed_batches"] += 1
                log.error("skipping batch %d", number)
                continue
            summary["students"] += len(rows)
            summary["problem_records"] += check_records("students", rows)
            save(RAW_DIR / f"students_batch_{number:03d}.json", rows)
    except QuotaExceeded as exc:
        log.error("daily Mockaroo limit reached, stopping: %s", exc)
        summary["failed_batches"] += 1

    # A small committed sample shows the data's shape. Written once, so reruns don't change Git.
    sample = SAMPLE_DIR / "sample_records.json"
    if not sample.exists() and summary["students"]:
        first_batch = json.loads((RAW_DIR / "students_batch_001.json").read_text(encoding="utf-8"))
        sample.write_text(json.dumps({"faculty": faculty[:3], "students": first_batch[:5]}, indent=2),
                          encoding="utf-8")
        log.info("wrote sample to %s", sample.relative_to(PROJECT))

    log.info("done: %(requests)d requests, %(faculty)d faculty, %(students)d students, "
             "%(failed_batches)d failed batches, %(problem_records)d records with problems", summary)
    if summary["failed_batches"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
