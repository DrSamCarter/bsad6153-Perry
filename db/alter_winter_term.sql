-- db/alter_winter_term.sql: one-time change to the live database (Week 3).
--
-- schema.sql uses "create table if not exists", so rerunning it never changes a table that
-- already exists. This file makes the same change to the live students table: it lets
-- entry_term be a Winter term (the short session over the holiday break, which new students
-- from ingest/sync.py join). Safe to run more than once.

begin;
alter table students drop constraint if exists students_entry_term_check;
alter table students add constraint students_entry_term_check
    check (entry_term ~ '^(Winter|Spring|Summer|Fall) [0-9]{4}$');
commit;
