# Data Dictionary (Week 1)

> **Draft.** Claude drafted this from our verified docs checks and test runs on Nov 1, 2026.
> Before submitting: check every claim, rewrite the ethics answers in my own words, and fill in
> anything marked **TODO**.

## Source

| | |
|---|---|
| **API** | Mockaroo (realistic fake data generator) |
| **Base URL** | `https://api.mockaroo.com/api` |
| **Endpoint used** | `POST /generate.json?count=N`, with the field definitions (schema) sent as the JSON body |
| **Documentation** | https://docs.mockaroo.com/ (field types) and https://www.mockaroo.com/docs (API) |
| **Terms of service** | TODO: paste the link from the footer of mockaroo.com |
| **Authentication** | API key from a free Mockaroo account, sent as the `X-API-Key` header. The docs also allow a `key` query parameter; I chose the header so the key never appears in URLs, logs or my screencast. The key lives only in `.env` as `MOCKAROO_API_KEY`. |
| **Plan and limits** | Free plan: 200 API requests per day, up to 1,000 rows per request. A full run uses 6 requests. |
| **Output format** | JSON. Mockaroo also offers CSV and custom-delimited output; I use JSON because the assignment asks for raw JSON responses. |

**Why fake data:** this project tracks faculty-student mentor groups. Real student records are
protected by FERPA and the website becomes public in Week 4, so every person in this dataset is
generated. Departments and programs are my college's real ones; names, emails and all other
values are fake.

## What one record means

- **Faculty (`data/raw/faculty.json`):** one record is one (fake) faculty member at my college:
  their department and program, what kind of mentoring they're best at, whether they're willing to
  mentor, and how many mentees they can take.
- **Student (`data/raw/students_batch_NNN.json`):** one record is one (fake) student in the mentoring
  program: their intended department and program, when they started, a few factors the committee
  considers (first-generation, athlete), what kind of mentoring they need, and their assigned
  faculty mentor, if they have one yet.

## Fields

### Faculty (60 records)

| Field | Type | Example | Meaning | Can be missing? |
|---|---|---|---|---|
| `faculty_id` | integer | `1` | Unique ID for the faculty member (1-60) | No |
| `first_name` | text | `Gerti` | First name (fake) | No |
| `last_name` | text | `Guiducci` | Last name (fake) | No |
| `email` | text | `gerti.guiducci@example.edu` | Built from the name on a reserved fake domain | No |
| `department` | code | `MS` | Department code (see table below) | No |
| `subject_area` | text | `Biology` | Program within the department; always one of that department's programs | No |
| `mentoring_focus` | text | `Career Preparation` | The kind of mentoring this person is strongest at | No |
| `willing_to_mentor` | true/false | `true` | Whether they've agreed to mentor | No |
| `max_mentees` | integer | `6` | Most students they're willing to take (1-6) | No |
| `years_at_institution` | integer | `7` | Years at the college (1-30) | No |

### Students (500 records)

| Field | Type | Example | Meaning | Can be missing? |
|---|---|---|---|---|
| `student_id` | integer | `1` | Unique ID for the student (1-500) | No |
| `first_name` | text | `Vito` | First name (fake) | No |
| `last_name` | text | `McGing` | Last name (fake) | No |
| `email` | text | `vito.mcging@students.example.edu` | Built from the name on a fake student domain | No |
| `department` | code | `SS` | Intended department, or `UND` if undeclared | No |
| `subject_area` | text | `Secondary Education` | Intended program; `Undeclared` when department is `UND` | No |
| `entry_term` | text | `Fall 2026` | Term the student started | No |
| `first_generation` | true/false | `false` | First in their family to attend college | No |
| `athlete` | true/false | `true` | On a college athletic team (about 50%, to be updated with a real count) | No |
| `mentoring_need` | text | `Life Skills` | The kind of mentoring the student most needs; same choices as faculty `mentoring_focus` | No |
| `preferred_meeting` | text | `Online` | In person, Online, or Either | No |
| `mentor_faculty_id` | integer | `45` | The `faculty_id` of the assigned mentor | **Yes:** about 30% of students have no mentor yet, and the field is then **left out of the record entirely** |

### Department codes

| Code | Department |
|---|---|
| AH | Allied Health |
| COS | Cosmetology |
| FAPA | Fine Arts & Performing Arts |
| HPER | Health, Physical Education, Recreation |
| HUM | Humanities |
| MS | Math & Sciences |
| SS | Social Sciences |
| TV | Technical & Vocational |
| UND | Undeclared (students only) |

Codes are used in the data because the full name "Health, Physical Education, Recreation"
contains commas, which break Mockaroo's lists and CSV files. The programs in each department are
listed in `ingest/schemas.py`. Note that "Health" and "Health Sciences" are programs in Math &
Sciences, not in Allied Health or HPER.

## Identifiers and relationships

- **Faculty** are identified by `faculty_id`, **students** by `student_id`. Both are unique within a run.
- **Student to faculty:** `students.mentor_faculty_id` refers to `faculty.faculty_id`. Many students
  can share one mentor; a student has at most one. Every mentor ID in the data points at a real
  faculty record (checked: 0 broken links in the full run).
- **Both to departments:** `department` holds a code from the table above. In Week 2 this becomes a
  small `departments` table that faculty and students both refer to.
- **Matching fields (not keys):** `mentoring_need` (student) uses the same values as
  `mentoring_focus` (faculty), and `subject_area` uses the same program names, so students can be
  matched to suitable mentors.

## Update behavior

- **New data:** Mockaroo stores nothing. Every request generates brand-new records, so there's no
  "what changed on the server" to ask about. New data appears whenever I request it.
- **Do old records change?** No. Once saved in `data/raw/`, a record never changes on its own. But
  rerunning the fetch generates a different set of people with the same IDs, so **an ID is only
  meaningful within one run**.
- **Detecting "what's new since last time" (Week 3):** I control the IDs, so new incoming students
  will be generated with IDs that continue after the highest `student_id` already in the database,
  and with the current `entry_term`. "New since last time" = IDs above the last loaded maximum.

## Surprises

1. **Mockaroo silently ignored my rules.** The first test returned HTTP 200 with every subject wrong
   for its department (e.g. a Cosmetology faculty member teaching Allied Health), with no error.
2. **An undocumented requirement.** Dynamic rules only work when every rule lists *every* possible
   value, with weight `0` for the ones that don't apply. The docs' examples don't show this; I found
   it by testing. Leaving out the `values` list made every row contain an error message instead.
3. **Missing means absent, not empty.** When a student has no mentor, Mockaroo doesn't send
   `null`; the `mentor_faculty_id` key isn't in the record at all. My first checker crashed on it.
4. **IDs restart every request.** Mockaroo's Row Number starts at 1 on each request, so batch 2
   would have duplicated students 1-100. I switched to a Sequence that starts where the last batch ended.
5. **Mentor assignments break the rules.** Random assignment ignores capacity: in the full run 43 of
   60 faculty had more mentees than their `max_mentees`, and 31 faculty marked unwilling still had
   mentees. This is the kind of problem the system should catch.
6. **The docs disagree about the limit.** The pricing page says "200 requests/day," but the library
   docs describe exceeding a number of *records* per 24 hours. The docs also don't say which HTTP
   status the limit returns, so the script checks the error message as well as for 429.
7. **Realistic-looking emails used real domains** (house.gov, utexas.edu) by default, so I replaced
   them with a formula on `example.edu`.

## Data-use ethics check

> TODO: rewrite each answer in my own words.

- **What do the terms allow and forbid?** TODO after reading the terms: storage, public display,
  commercial use, attribution. The data itself is generated for me, so I expect storing and
  displaying it to be allowed; confirm, and add any required attribution to the README's Credits.
- **Does this data describe real, identifiable people?** No. Every person is generated, and emails
  use reserved fake domains. The only real information is my college's department and program
  names, which are public. If this system were later used with real students, that data would be
  protected by FERPA and could never be shown on a public site.
- **Worst realistic harm if it leaked or were misread?** A leak exposes no one. The real risk is
  misreading: someone could mistake the fake records or the random mentor loads for real
  information about my college's faculty. The website should clearly say all people are fictional.
- **Who should be allowed to read or change these records?** Only me (the sync, as database owner)
  should change records. The public website and chatbot get read-only access, and the Week 6 agent
  should be able to *propose* mentor assignments but not change them without my approval.
