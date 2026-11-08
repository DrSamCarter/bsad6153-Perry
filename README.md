# BSAD 6153 Project: Faculty-Student Mentor Groups

**Student:** &lt;your name&gt;
**My decision:** What information should we collect from faculty who want to mentor?
**Website:** &lt;your domain, from Week 4&gt;

This repository is one complete AI system, built over eight weeks: a real API, synced on a schedule into a
PostgreSQL database, shown on a public website, with a chatbot and an agent that answer and act from your
own data. You build it with an AI coding agent, and you read and verify everything it writes.

---

## Setting up your computer (Week 1 Setup)

You need a **Windows 10/11 or macOS computer where you can install software**, Git, Python 3.12, and your AI
coding agent (Claude Code, Codex, Antigravity, or Copilot). Let your agent help with the installs, but read
every command before you approve it, and keep auto-approve off.

1. **Clone this repository** into a short folder path that isn't synced by OneDrive or Dropbox, for example
   `C:\dev\bsad6153` on Windows or `~/dev/bsad6153` on macOS.
2. **Create and activate a virtual environment** from the project folder:

   | | Windows (PowerShell) | macOS (Terminal) |
   |---|---|---|
   | Create | `py -3.12 -m venv .venv` | `python3.12 -m venv .venv` |
   | Activate | `.venv\Scripts\Activate.ps1` | `source .venv/bin/activate` |

   You'll see `(.venv)` at the start of your prompt when it's active. Activate it every time you open a new terminal.
3. **Install the packages:** `pip install -r requirements.txt`
4. **Create your secrets file:** copy `.env.example` to `.env`, and put a fake value on the `TEST_SECRET=` line.
5. **Check everything:** `python scripts/check_setup.py` should end with `Setup OK`.
6. **Try the website:** `streamlit run app/streamlit_app.py` opens it in your browser. Press Ctrl+C to stop it.

### Working with your AI agent

- **You approve every command.** Read it first, and if you don't understand it, ask the agent what it does.
- **Ask for a plan before code:** "Before writing anything, tell me your plan."
- **Never paste a real key into the chat,** and never ask the agent to print your `.env` file.
- **The agent never gets the owner database password or deploy tokens.** That's how agents delete databases.
- **Record what you directed, read, verified, and decided** in each pull request's AI review log.

---

## Project layout

| Folder | What goes there | When |
|---|---|---|
| `ingest/` | Fetch, load, and sync code | Weeks 1&ndash;3 |
| `db/` | `schema.sql`, `roles.sql`, `queries.sql` | Weeks 2&ndash;6 |
| `docs/` | Data dictionary, logs, reports (see `docs/README.md`) | Every week |
| `evals/` | Golden questions and evaluation runs | Weeks 3&ndash;7 |
| `app/` | Your website (Streamlit) | Weeks 4&ndash;6 |
| `examples/` | A reference tool-using chatbot loop | Week 5 |
| `scripts/` | Setup and database checks | Weeks 0&ndash;2 |
| `data/sample/` | A small sample of raw API data (large downloads go in `data/raw/`, which Git ignores) | Week 1 |

## Secrets: where each one lives

| Secret | On your computer | On Render (website) | In GitHub Actions (sync) |
|---|---|---|---|
| `DATABASE_URL` (owner) | `.env` | **never** | Actions secret |
| `APP_DATABASE_URL` (read-only) | `.env` | environment setting | if your checks need it |
| `AGENT_DATABASE_URL` | `.env` | environment setting | no |
| LLM key, `APP_PASSWORD` | `.env` | environment setting | no |
| Data API key | `.env` | no | Actions secret |

`.env.example` lists the names only. If a secret ever leaks, revoke or rotate it first, then tell the instructor.

---

## Deploying on Render (Week 4)

1. Claim your free domain through the GitHub Student Developer Pack.
2. In Render, choose **New &gt; Blueprint**, pick this repository, and enter each secret when asked.
   (`render.yaml` describes the service.) Or create a **Web Service** by hand with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `streamlit run app/streamlit_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
   - Environment variables: `PYTHON_VERSION=3.12.4`, `APP_DATABASE_URL`, and later your LLM key and `APP_PASSWORD`
3. Under **Settings &gt; Custom Domains**, add your domain, then add the DNS records Render shows you at your
   registrar. Ask your agent to explain each record before you add it. HTTPS turns on automatically.
4. Free services sleep when idle and take about a minute to wake. Say so on your site.

---

## Troubleshooting

- **`pip install` fails with "No such file or directory" on Windows:** the folder path is too long. Move the
  project to a short path such as `C:\dev\bsad6153` and recreate `.venv`.
- **PowerShell says running scripts is disabled when you activate:** use Command Prompt instead and run
  `.venv\Scripts\activate.bat`, or ask the instructor. Don't change system security settings without asking.
- **`python` opens the Microsoft Store or isn't found:** use `py -3.12` on Windows or `python3.12` on macOS.
- **The database check can't connect:** use Supabase's Session pooler string, check the password, and check
  that your Supabase project isn't paused.

---

## Project proposal (Week 1)

<!-- DRAFT by Claude: rewrite in your own words. -->

**Data source and backup.** I lead the committee developing faculty-student mentor groups at my
college. Real student records are protected by FERPA and this site goes public in Week 4, so the
project uses **Mockaroo**, an API that generates realistic fake records from a schema I define.
Departments and programs are my college's real ones; every person is fictional. Mockaroo
provides two related resource types, faculty and students, linked by each student's assigned mentor.
My instructor approved dummy data. **Backup:** the Random User API (randomuser.me), which needs no
key and pages through generated people with a seed; departments and programs would then be added
in my own code.

**My decision and workflow.** Our mentor program is new, so my current decision is what
information we should collect from faculty who want to mentor. Today I make it by email with my
committee over several days: I draft a list from my notes and the faculty roster, send it out,
then review replies and revise. My first session took 17 minutes, and my confidence afterward was
only 2 out of 5 because I didn't know what the other committee members felt was important. The
system should make that information concrete: store each faculty member's department, program,
mentoring strengths, willingness and capacity in one place, so the committee can see which fields
actually matter for matching students, and where current assignments break those limits.

**Agent idea (first draft).** When a new cohort of students arrives, an agent proposes mentor
assignments: it matches each student's program and mentoring need to a willing faculty member with
room, flags faculty who are over capacity, and drafts welcome emails. It never assigns a student
or sends an email without my approval.

**Risks.** Rate limits: the free plan allows 200 requests a day, and a full fetch uses 6; the
script waits between requests and stops cleanly if the daily limit is reached. Key expiry: the key
is tied to my Mockaroo account and can be regenerated if it leaks. Data volume: small (about 560
records), well under the 1,000-rows-per-request limit. Terms of service: Mockaroo allows any use
of generated data except building another data generator, so storing and publicly displaying it
is fine; the data comes without warranty, so I verify it myself. Finally, the
fake data must never be mistaken for real people; the website will say so.

## How to run this project

1. Set up the virtual environment and packages (see "Setting up your computer" above).
2. Create a free Mockaroo account, copy your API key, and add it to `.env` as
   `MOCKAROO_API_KEY=...` (the name is listed in `.env.example`).
3. Fetch the data from the project folder:

   ```
   python ingest/fetch.py
   ```

   This fetches 60 faculty and 500 students (in 5 batches of 100) and saves raw JSON to
   `data/raw/`, which Git ignores. It uses 6 of the free plan's 200 daily requests. Options:
   `--students`, `--batch-size`, `--faculty`, `--delay`. A small sample is committed in
   `data/sample/`. Field definitions are in `ingest/schemas.py`; field meanings are in
   `docs/data_dictionary.md`.

## Credits

- Fake data generated with [Mockaroo](https://www.mockaroo.com/). Its
  [terms of use](https://www.mockaroo.com/help/terms_of_use) allow any use except building another
  data generator and don't require attribution; I credit it anyway.
- Department and program names are my college's real ones; all people, emails and other values are
  fictional.
