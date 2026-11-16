-- db/roles.sql: who may do what in the database.
--
-- NEVER PUT A PASSWORD IN THIS FILE. It is committed to a public GitHub repository.
-- Create each role here without a password, then set the password separately
-- in the Supabase SQL editor (and nowhere in the repository):
--
--     alter role app_reader with password '...long random password...';
--
-- Then put the role's Session pooler connection string in .env as APP_DATABASE_URL.
-- With the pooler, the user name is app_reader.<project-ref>.
--
-- Safe to run more than once: the role is only created if it doesn't exist yet,
-- and granting a privilege that's already granted changes nothing. Rerun this file
-- whenever a grant line is added.


-- ---------------------------------------------------------------------------
-- app_reader (Week 3): read-only role for the golden-question checker (Week 3),
-- the website (Week 4), and the chatbot (Week 5). It can read the data tables
-- and nothing else: no insert, update, delete, or creating tables.
-- ---------------------------------------------------------------------------
do $$
begin
    if not exists (select from pg_roles where rolname = 'app_reader') then
        create role app_reader login;
    end if;
end
$$;

grant usage on schema public to app_reader;

-- Every table is listed by name, so a table added later is NOT readable until
-- it gets its own line here.
grant select on
    departments,
    programs,
    mentoring_focus_areas,
    faculty,
    students,
    faculty_focus_areas,
    faculty_subjects,
    mentor_assignments
to app_reader;

-- Week 3, Part C: uncomment after sync_runs is created, then rerun this file.
-- grant select on sync_runs to app_reader;


-- ---------------------------------------------------------------------------
-- Week 6: the agent's own role (see the Week 6 page for the exact grants).
-- create role agent_writer login;
-- grant usage on schema public to agent_writer;
-- grant select on <your data tables>, sync_runs, agent_runs, agent_proposals to agent_writer;
-- grant insert on agent_runs, agent_proposals to agent_writer;
-- grant update on agent_runs to agent_writer;
--
-- Week 6: the one write your website may do, which covers only the review columns.
-- grant select on agent_runs, agent_proposals to app_reader;
-- grant update (status, reviewed_at, reviewer_note) on agent_proposals to app_reader;
