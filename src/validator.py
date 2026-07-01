"""
validator.py
-------------
Step 6 of the pipeline: VALIDATE.

Ensures the final output always matches the schema shape -- every expected
top-level key is present, missing values become explicit `null` (never an
absent key, never a crash), and obviously wrong types are coerced or
nulled rather than allowed to propagate. This is what makes the pipeline
"Robust" per the assignment's constraints: a missing or garbage source
degrades the output, it never crashes the run.
"""

SCHEMA_FIELDS = {
    "candidate_id": str,
    "full_name": str,
    "emails": list,
    "phones": list,
    "location": dict,
    "links": dict,
    "headline": str,
    "years_experience": (int, float),
    "skills": list,
    "experience": list,
    "education": list,
    "provenance": list,
    "overall_confidence": (int, float),
}


def validate_record(record):
    """Return (clean_record, warnings). Never raises."""
    warnings = []
    clean = {}
    for field, expected_type in SCHEMA_FIELDS.items():
        value = record.get(field)
        if value is None:
            clean[field] = None
            continue
        if not isinstance(value, expected_type):
            warnings.append(f"{field}: expected {expected_type}, got {type(value).__name__} -> set to null")
            clean[field] = None
            continue
        clean[field] = value
    return clean, warnings


def validate_all(records):
    clean_records = []
    all_warnings = {}
    for rec in records:
        clean, warnings = validate_record(rec)
        clean_records.append(clean)
        if warnings:
            all_warnings[rec.get("candidate_id", "unknown")] = warnings
    return clean_records, all_warnings
