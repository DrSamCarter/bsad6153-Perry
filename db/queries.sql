-- db/queries.sql: business questions answered with SQL (Week 2).
--
-- My decision: what information should we collect from faculty who want to mentor?
-- Each query tests whether a piece of faculty information actually matters for matching.
--
-- Coverage: JOINs (Q1, Q2, Q4, Q5, Q6), GROUP BY (Q1, Q2, Q3, Q4, Q5, Q6),
-- time filter (Q3), surprising answer (Q6).


-- Q1: Which faculty have more mentees than they said they could take (max_mentees)?
--     If capacity is ignored anyway, is it worth asking faculty for it?
select f.faculty_id,
       f.first_name || ' ' || f.last_name as faculty_name,
       f.willing_to_mentor,
       f.max_mentees,
       count(*) as current_mentees,
       count(*) - f.max_mentees as over_by
from faculty f
join mentor_assignments ma on ma.faculty_pk = f.faculty_pk
group by f.faculty_pk
having count(*) > f.max_mentees
order by over_by desc, f.faculty_id;


-- Q2: How many students are paired with faculty who said they are NOT willing to mentor?
select f.willing_to_mentor,
       count(distinct f.faculty_pk) as faculty_with_mentees,
       count(*) as students_assigned
from faculty f
join mentor_assignments ma on ma.faculty_pk = f.faculty_pk
group by f.willing_to_mentor
order by f.willing_to_mentor;


-- Q3: Among students who started in the last 12 months, how many in each department
--     are still waiting for a mentor? (Time filter on entry_term_start.)
select s.department_code,
       d.department_name,
       count(*) as recent_students,
       count(*) filter (where ma.student_pk is null) as waiting_for_mentor,
       round(100.0 * count(*) filter (where ma.student_pk is null) / count(*), 1) as pct_waiting
from students s
join departments d on d.department_code = s.department_code
left join mentor_assignments ma on ma.student_pk = s.student_pk
where s.entry_term_start >= current_date - interval '12 months'
group by s.department_code, d.department_name
order by pct_waiting desc;


-- Q4: Do first-generation students get a mentor from their own department as often
--     as other students do? (Follows up my Week 1 data-quality finding.)
select case when s.first_generation then 'First-generation' else 'Not first-gen' end as student_group,
       count(*) as students,
       round(100.0 * count(ma.student_pk) / count(*), 1) as pct_with_mentor,
       -- Out of students who HAVE a mentor, the share whose mentor is in their department.
       round(100.0 * count(*) filter (where f.department_code = s.department_code)
             / nullif(count(ma.student_pk), 0), 1) as pct_of_mentored_in_own_department
from students s
left join mentor_assignments ma on ma.student_pk = s.student_pk
left join faculty f on f.faculty_pk = ma.faculty_pk
group by s.first_generation
order by s.first_generation desc;


-- Q5: How often does a student's mentoring need match one of their mentor's focus areas?
--     If it rarely matches, collecting focus areas from faculty isn't being used.
select s.mentoring_need,
       count(*) as mentored_students,
       count(ffa.focus_area) as need_matches_mentor_focus,
       round(100.0 * count(ffa.focus_area) / count(*), 1) as pct_matched
from students s
join mentor_assignments ma on ma.student_pk = s.student_pk
left join faculty_focus_areas ffa
       on ffa.faculty_pk = ma.faculty_pk and ffa.focus_area = s.mentoring_need
group by s.mentoring_need
order by pct_matched;


-- Q6: For each kind of mentoring, how many students need it, and how many mentee spots
--     do willing faculty with that focus offer? (Supply vs. demand.)
-- SURPRISE: there were many more students needing specific help than there were faculty available to offer that help, even if they were maxed out at the 
-- number of students we've set up for them to have (at 6). But they were maxed out well below that because they were able to choose how many students they
--  wanted to mentor. This means that we will either need more faculty to volunteer or we will have to try to rank student need. Transfer planning, for
-- example, had a shortfall of 67 spots for students.
with demand as (
    select mentoring_need as focus_area, count(*) as students_needing
    from students
    group by mentoring_need
), supply as (
    select ffa.focus_area, count(*) as willing_faculty, sum(f.max_mentees) as willing_spots
    from faculty_focus_areas ffa
    join faculty f on f.faculty_pk = ffa.faculty_pk
    where f.willing_to_mentor
    group by ffa.focus_area
)
select mfa.focus_area,
       coalesce(d.students_needing, 0) as students_needing,
       coalesce(s.willing_faculty, 0) as willing_faculty,
       coalesce(s.willing_spots, 0) as willing_spots,
       coalesce(d.students_needing, 0) - coalesce(s.willing_spots, 0) as shortfall
from mentoring_focus_areas mfa
left join demand d on d.focus_area = mfa.focus_area
left join supply s on s.focus_area = mfa.focus_area
order by shortfall desc;


-- Q7: For each student still waiting for a mentor, who is the best available mentor?
--     A candidate must be willing, offer the student's mentoring need as a focus area,
--     and still have an open spot (current mentees < max_mentees).
--     Best = same program first, then same department, then the most open spots.
--     Students with no candidate show blanks: nobody qualified has room.
--     Order: students who started earliest come first (a placeholder until the
--     committee sets real priority rules).
--     This query only SUGGESTS; recording a pairing is a separate, deliberate step.
--     Limitation: each student is matched on their own, so one mentor with 2 open spots
--     can be suggested to many students. Assign one, rerun, and the list updates.
with open_mentors as (
    select f.faculty_pk, f.faculty_id,
           f.first_name || ' ' || f.last_name as mentor_name,
           f.department_code,
           f.max_mentees - count(ma.student_pk) as open_spots
    from faculty f
    left join mentor_assignments ma on ma.faculty_pk = f.faculty_pk
    where f.willing_to_mentor
    group by f.faculty_pk
    having count(ma.student_pk) < f.max_mentees
)
select s.student_id,
       s.first_name || ' ' || s.last_name as student_name,
       s.entry_term,
       s.department_code,
       s.mentoring_need,
       best.faculty_id as suggested_mentor_id,
       best.mentor_name as suggested_mentor,
       best.open_spots,
       best.reason
from students s
left join lateral (
    select om.faculty_id, om.mentor_name, om.open_spots,
           case when fs.program_name is not null then 'same program'
                when om.department_code = s.department_code then 'same department'
                else 'focus area only' end as reason
    from open_mentors om
    join faculty_focus_areas ffa
         on ffa.faculty_pk = om.faculty_pk and ffa.focus_area = s.mentoring_need
    left join faculty_subjects fs
         on fs.faculty_pk = om.faculty_pk and fs.program_name = s.program_name
    order by (fs.program_name is not null) desc,
             (om.department_code = s.department_code) desc,
             om.open_spots desc
    limit 1
) best on true
where not exists (select 1 from mentor_assignments ma where ma.student_pk = s.student_pk)
order by s.entry_term_start, s.student_id;
