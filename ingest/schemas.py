"""Mockaroo field definitions, sent with each API request so the schemas live in this repo.

All data is fake. Field types and option names follow the Mockaroo API docs; check any you change.
"""

# Department codes used in the data. Full names belong in docs/data_dictionary.md.
DEPARTMENTS = {
    "AH": "Allied Health",
    "COS": "Cosmetology",
    "FAPA": "Fine Arts & Performing Arts",
    "HPER": "Health, Physical Education, Recreation",
    "HUM": "Humanities",
    "MS": "Math & Sciences",
    "SS": "Social Sciences",
    "TV": "Technical & Vocational",
}

# Real programs offered in each department, so a generated subject always matches its department.
SUBJECTS = {
    "AH": ["Allied Health", "General Studies", "Medication Aide", "Nurse Aide", "Nursing",
           "Para-professional Nursing"],
    "COS": ["Cosmetology", "Nail Technology"],
    "FAPA": ["Art", "Creative and Performing Arts", "Music"],
    "HPER": ["Athletic Training", "Sports Administration"],
    "HUM": ["Civic Engagement", "English", "Language"],
    "MS": ["Biology", "Biotechnology", "Chemistry", "Health", "Health Sciences", "Mathematics",
           "Physical Sciences", "Physics"],
    "SS": ["Business Transfer", "Early Childhood Education", "Elementary Education", "History",
           "Political Science", "Psychology", "Secondary Education", "Social Science", "Social Work"],
    "TV": ["Ag Production/Farm & Ranch Management", "Agribusiness", "Agriculture",
           "Automotive Technology", "Building Construction Technology",
           "CDL/Commercial Truck Driving", "Diesel Technology", "Electrical Technology",
           "Flight Instructor", "HVAC", "Industrial Operations Technology", "Welding Technology"],
}

MENTORING_FOCUS = ["Career Preparation", "Academic Success", "Transfer Planning",
                   "First-Generation Support", "Life Skills"]

# Students may not have chosen a department yet; faculty always have one.
STUDENT_SUBJECTS = {**SUBJECTS, "UND": ["Undeclared"]}

ENTRY_TERMS = ["Fall 2025", "Spring 2026", "Fall 2026"]
MEETING_PREFERENCES = ["In person", "Online", "Either"]

# Faculty IDs run 1..FACULTY_COUNT, so a student's mentor_faculty_id always points at a real faculty row.
FACULTY_COUNT = 60


def subject_field(subjects=SUBJECTS):
    """A Custom List whose choices depend on the row's department (dynamic distribution).

    Tested 2026-11-01: Mockaroo ignores a rule unless its frequencies list every value,
    so subjects outside the department get weight "0". Leaving out "values" makes every row an error.
    """
    all_subjects = sorted({s for dept_subjects in subjects.values() for s in dept_subjects})
    return {
        "name": "subject_area",
        "type": "Custom List",
        "values": all_subjects,
        "selectionStyle": "dynamic",
        "distribution": [
            {
                "rule": f"department == '{code}'",
                "frequencies": {s: ("1" if s in dept_subjects else "0") for s in all_subjects},
            }
            for code, dept_subjects in subjects.items()
        ],
    }


FACULTY_FIELDS = [
    {"name": "faculty_id", "type": "Row Number"},
    {"name": "first_name", "type": "First Name"},
    {"name": "last_name", "type": "Last Name"},
    # A Formula on a fake domain, so no address looks like a real organization's.
    {"name": "email", "type": "Formula",
     "value": "lower(first_name) + '.' + lower(last_name) + '@example.edu'"},
    {"name": "department", "type": "Custom List", "values": list(DEPARTMENTS),
     "selectionStyle": "random"},
    subject_field(),
    {"name": "mentoring_focus", "type": "Custom List", "values": MENTORING_FOCUS,
     "selectionStyle": "random"},
    {"name": "willing_to_mentor", "type": "Boolean"},
    {"name": "max_mentees", "type": "Number", "min": 1, "max": 6, "decimals": 0},
    {"name": "years_at_institution", "type": "Number", "min": 1, "max": 30, "decimals": 0},
]

STUDENT_FIELDS = [
    {"name": "student_id", "type": "Row Number"},
    {"name": "first_name", "type": "First Name"},
    {"name": "last_name", "type": "Last Name"},
    {"name": "email", "type": "Formula",
     "value": "lower(first_name) + '.' + lower(last_name) + '@students.example.edu'"},
    {"name": "department", "type": "Custom List", "values": list(STUDENT_SUBJECTS),
     "selectionStyle": "random"},
    subject_field(STUDENT_SUBJECTS),
    {"name": "entry_term", "type": "Custom List", "values": ENTRY_TERMS, "selectionStyle": "random"},
    {"name": "first_generation", "type": "Boolean"},
    {"name": "athlete", "type": "Boolean"},
    {"name": "mentoring_need", "type": "Custom List", "values": MENTORING_FOCUS,
     "selectionStyle": "random"},
    {"name": "preferred_meeting", "type": "Custom List", "values": MEETING_PREFERENCES,
     "selectionStyle": "random"},
    # Blank means the student is still waiting for a mentor.
    {"name": "mentor_faculty_id", "type": "Number", "min": 1, "max": FACULTY_COUNT, "decimals": 0,
     "percentBlank": 30},
]


def student_fields(first_id, faculty_count=FACULTY_COUNT):
    """STUDENT_FIELDS for one batch. Row Number restarts at 1 on every request, so batches use a
    Sequence starting at first_id to keep student IDs unique across the whole run (tested 2026-11-01).
    Mentor IDs are limited to the faculty actually fetched."""
    id_field = {"name": "student_id", "type": "Sequence", "start": first_id, "step": 1}
    mentor_field = {**STUDENT_FIELDS[-1], "max": faculty_count}
    return [id_field] + STUDENT_FIELDS[1:-1] + [mentor_field]
