"""Week 3 data status. Run it from the project folder:

    python scripts/status.py

Answers two questions from the sync_runs log and the data tables:
  1. When was the data last successfully updated?
  2. What changed in the last 7 days?

Connects as the read-only role (APP_DATABASE_URL), the same way the website (Week 4)
and chatbot (Week 5) will, so it can never change anything. Never prints the
connection string.
"""

import os
import sys
from datetime import datetime, timezone

import psycopg
from dotenv import load_dotenv

load_dotenv()

DAYS = 7

LAST_SUCCESS = """
    select run_id, finished_at, trigger, records_fetched, records_inserted, records_updated
    from sync_runs
    where status = 'success'
    order by finished_at desc
    limit 1
"""

RECENT_RUNS = """
    select run_id, started_at, finished_at, status, trigger,
           records_fetched, records_inserted, records_updated, error_message
    from sync_runs
    where started_at >= now() - make_interval(days => %s)
    order by started_at
"""

# What changed in the data itself. A row counts as "new" if it was first seen in the window,
# and as "updated" if it was changed in the window after it was first inserted.
# At insert both timestamps get the same now() (one value per transaction), so
# last_updated_at > first_seen_at only after a real update. A row inserted and then changed
# in the same week counts in both columns. Deleted rows (removed mentors) can't show here;
# sync.py's output lists them.
DATA_CHANGES = """
    select 'students',
           count(*) filter (where first_seen_at >= now() - make_interval(days => %(days)s)),
           count(*) filter (where last_updated_at >= now() - make_interval(days => %(days)s)
                              and last_updated_at > first_seen_at)
    from students
    union all
    select 'mentor_assignments',
           count(*) filter (where first_seen_at >= now() - make_interval(days => %(days)s)),
           count(*) filter (where last_updated_at >= now() - make_interval(days => %(days)s)
                              and last_updated_at > first_seen_at)
    from mentor_assignments
"""


def when(moment):
    """'2026-11-16 14:05 UTC (3.2 hours ago)'"""
    if moment is None:
        return "not finished"
    hours = (datetime.now(timezone.utc) - moment).total_seconds() / 3600
    ago = f"{hours:.1f} hours ago" if hours < 48 else f"{hours / 24:.1f} days ago"
    return f"{moment.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC ({ago})"


def main():
    url = os.environ.get("APP_DATABASE_URL")
    if not url:
        sys.exit("[FAIL] APP_DATABASE_URL is not set. Add it to your .env file (see .env.example).")

    try:
        with psycopg.connect(url, connect_timeout=10) as conn:
            last = conn.execute(LAST_SUCCESS).fetchone()
            runs = conn.execute(RECENT_RUNS, (DAYS,)).fetchall()
            changes = conn.execute(DATA_CHANGES, {"days": DAYS}).fetchall()
    except psycopg.Error as error:
        sys.exit(f"[FAIL] {str(error).strip().splitlines()[0]}")

    print("1. When was the data last successfully updated?")
    if last:
        run_id, finished, trigger, fetched, inserted, updated = last
        print(f"   {when(finished)}, run {run_id} ({trigger}): "
              f"{fetched} fetched, {inserted} inserted, {updated} updated")
    else:
        print("   No successful sync yet.")

    print(f"\n2. What changed in the last {DAYS} days?")
    if runs:
        by_status = {}
        for run in runs:
            by_status[run[3]] = by_status.get(run[3], 0) + 1
        summary = ", ".join(f"{count} {status}" for status, count in sorted(by_status.items()))
        print(f"   {len(runs)} runs: {summary}")
        print(f"\n   {'run':>4}  {'started (UTC)':<16}  {'status':<8} {'trigger':<9}"
              f"{'fetched':>8}{'inserted':>9}{'updated':>8}  note")
        for (run_id, started, finished, status, trigger,
             fetched, inserted, updated, error) in runs:
            note = error or ""
            if finished is None and status == "failed":
                note = note or "did not finish"
            print(f"   {run_id:>4}  {started.astimezone(timezone.utc):%Y-%m-%d %H:%M}  "
                  f"{status:<8} {trigger:<9}{fetched:>8}{inserted:>9}{updated:>8}  {note[:60]}")
    else:
        print("   No sync runs in this period.")

    print(f"\n   {'table':<20}{'new':>6}{'updated':>9}")
    for table, new, updated in changes:
        print(f"   {table:<20}{new:>6}{updated:>9}")


if __name__ == "__main__":
    main()
