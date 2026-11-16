-- db/schema.sql: mentor-group database (Week 2), extended in Weeks 3 and 6.
--
-- Eight tables in three kinds:
--   Lookups (short fixed lists):  departments, programs, mentoring_focus_areas
--   Entities (the people):        faculty, students
--   Relationships (links):        faculty_focus_areas, faculty_subjects, mentor_assignments
--
-- Every table has first_seen_at and last_updated_at (audit columns), filled in automatically.
-- Safe to run more than once: "if not exists" skips tables that are already there.

-- ---------------------------------------------------------------- lookups

-- One academic department. UND (Undeclared) exists for students only.
create table if not exists departments (
    department_code text primary key check (department_code ~ '^[A-Z]{2,4}$'),
    department_name text not null unique,
    students_only   boolean not null default false,
    first_seen_at   timestamptz not null default now(),
    last_updated_at timestamptz not null default now()
);

-- One program (major) and the department it belongs to.
create table if not exists programs (
    program_name    text primary key,
    department_code text not null references departments (department_code),
    first_seen_at   timestamptz not null default now(),
    last_updated_at timestamptz not null default now(),
    -- Lets students point at (program, department) together, so a student's
    -- program must belong to the student's department.
    unique (program_name, department_code)
);

-- One kind of mentoring. Faculty strengths and student needs both use this list.
create table if not exists mentoring_focus_areas (
    focus_area      text primary key,
    first_seen_at   timestamptz not null default now(),
    last_updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- entities

-- One faculty member. Their focus areas and subjects live in the junction
-- tables below, because faculty can mentor in more than one of each.
create table if not exists faculty (
    faculty_pk           bigint generated always as identity primary key,
    faculty_id           integer not null unique check (faculty_id > 0),  -- Mockaroo's ID
    first_name           text not null,
    last_name            text not null,
    email                text not null unique check (email like '%@example.edu'),
    department_code      text not null references departments (department_code),
    willing_to_mentor    boolean not null,
    max_mentees          integer not null check (max_mentees between 1 and 6),
    years_at_institution integer not null check (years_at_institution between 1 and 30),
    raw                  jsonb,  -- the original Mockaroo record
    first_seen_at        timestamptz not null default now(),
    last_updated_at      timestamptz not null default now()
);

-- One student in the mentoring program (the main table: 500 rows).
create table if not exists students (
    student_pk        bigint generated always as identity primary key,
    student_id        integer not null unique check (student_id > 0),  -- Mockaroo's ID
    first_name        text not null,
    last_name         text not null,
    email             text not null unique check (email like '%@students.example.edu'),
    department_code   text not null references departments (department_code),
    program_name      text not null,
    entry_term        text not null check (entry_term ~ '^(Spring|Summer|Fall) [0-9]{4}$'),
    -- First day of entry_term as a real date, so queries can filter by time.
    entry_term_start  date not null,
    first_generation  boolean not null,
    athlete           boolean not null,
    mentoring_need    text not null references mentoring_focus_areas (focus_area),
    preferred_meeting text not null check (preferred_meeting in ('In person', 'Online', 'Either')),
    raw               jsonb,  -- the original Mockaroo record
    first_seen_at     timestamptz not null default now(),
    last_updated_at   timestamptz not null default now(),
    foreign key (program_name, department_code)
        references programs (program_name, department_code)
);

-- ---------------------------------------------------------------- relationships

-- One row = "this faculty member will mentor in this focus area".
create table if not exists faculty_focus_areas (
    faculty_pk      bigint not null references faculty (faculty_pk) on delete cascade,
    focus_area      text not null references mentoring_focus_areas (focus_area),
    first_seen_at   timestamptz not null default now(),
    last_updated_at timestamptz not null default now(),
    primary key (faculty_pk, focus_area)
);

-- One row = "this faculty member can mentor students in this program".
create table if not exists faculty_subjects (
    faculty_pk      bigint not null references faculty (faculty_pk) on delete cascade,
    program_name    text not null references programs (program_name),
    first_seen_at   timestamptz not null default now(),
    last_updated_at timestamptz not null default now(),
    primary key (faculty_pk, program_name)
);

-- One row = one student-mentor pairing. A student with no mentor has no row.
-- unique (student_pk) allows one current mentor per student; to keep a history
-- of reassignments later, replace it with an "ended_at" column.
-- Capacity (max_mentees) and willingness are NOT enforced here on purpose:
-- the data breaks both rules, and finding those cases is a job for queries.sql.
create table if not exists mentor_assignments (
    assignment_pk   bigint generated always as identity primary key,
    student_pk      bigint not null unique references students (student_pk) on delete cascade,
    faculty_pk      bigint not null references faculty (faculty_pk),
    first_seen_at   timestamptz not null default now(),
    last_updated_at timestamptz not null default now()
);

-- Indexes for the foreign keys queries join on (Postgres doesn't add these automatically).
create index if not exists students_department_idx on students (department_code);
create index if not exists mentor_assignments_faculty_idx on mentor_assignments (faculty_pk);
