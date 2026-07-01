"""
tests/test_pipeline.py
-----------------------
Run with: pytest -q   (from repo root)

Covers:
  - normalizer functions (email, phone, country, date, skill)
  - merge identity rule (email match + name-fuzzy match)
  - conflict resolution (source priority)
  - config-driven output projection (rename/select/omit)
  - end-to-end run against the bundled sample input/ folder, including the
    deliberately broken/empty record (robustness: must not crash)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import normalizer as N
from src import merger
from src import config_loader
from src.main import run_pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(os.path.dirname(HERE), "input")


# ----------------------------------------------------------- normalizer ---

def test_normalize_email():
    assert N.normalize_email("John@Gmail.com") == "john@gmail.com"
    assert N.normalize_email("not-an-email") is None
    assert N.normalize_email(None) is None


def test_normalize_phone_e164():
    assert N.normalize_phone("+91-9876543210") == "+919876543210"
    assert N.normalize_phone("9876543210", default_region="IN") == "+919876543210"


def test_normalize_country():
    assert N.normalize_country("India") == "IN"
    assert N.normalize_country("IN") == "IN"


def test_normalize_date():
    assert N.normalize_date_yyyymm("March 2021") == "2021-03"
    assert N.normalize_date_yyyymm("2021-3") == "2021-03"
    assert N.normalize_date_yyyymm("Present") is None


def test_normalize_skill_canonical():
    assert N.normalize_skill("js") == "JavaScript"
    assert N.normalize_skill("python") == "Python"


# --------------------------------------------------------------- merger ---

def _rec(**kwargs):
    base = {
        "source_file": "x", "source_type": "ats_json", "confidence": 0.9,
        "full_name": None, "emails": [], "phones": [], "city": None, "region": None,
        "country": None, "headline": None, "company": None, "linkedin": None,
        "github": None, "portfolio": None, "skills": [], "years_experience": None,
        "education": [], "experience": [],
    }
    base.update(kwargs)
    return base


def test_group_by_email_match():
    a = _rec(full_name="John Doe", emails=["john@gmail.com"], source_type="ats_json")
    b = _rec(full_name="John A. Doe", emails=["john@gmail.com"], source_type="resume_pdf")
    groups = merger.group_records([a, b])
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_group_different_emails_stay_separate():
    a = _rec(full_name="John Doe", emails=["john@gmail.com"])
    b = _rec(full_name="Jane Doe", emails=["jane@gmail.com"])
    groups = merger.group_records([a, b])
    assert len(groups) == 2


def test_conflict_resolution_source_priority():
    # resume_pdf should beat ats_json beats recruiter_csv by default priority.
    json_rec = _rec(full_name="John Doe", emails=["john@gmail.com"],
                     source_type="ats_json", company="IBM", headline="Eng")
    resume_rec = _rec(full_name="John A. Doe", emails=["john@gmail.com"],
                       source_type="resume_pdf", company="IBM", headline="Senior Backend Engineer")
    merged = merger.merge_group([json_rec, resume_rec])
    assert merged["headline"] == "Senior Backend Engineer"
    prov = {p["field"]: p["source"] for p in merged["provenance"]}
    assert prov["headline"] == "resume_pdf"


# ---------------------------------------------------------- config proj ---

def test_apply_config_rename_and_omit():
    internal = {"candidate_id": "cand_0001", "full_name": "John Doe", "headline": None}
    cfg = {
        "fields": [
            {"path": "id", "from": "candidate_id", "type": "string", "required": True},
            {"path": "name", "from": "full_name", "type": "string", "required": True},
            {"path": "title", "from": "headline", "type": "string", "required": False},
        ],
        "include_confidence": True,
        "on_missing": "omit",
    }
    out = config_loader.apply_config(internal, cfg)
    assert out == {"id": "cand_0001", "name": "John Doe"}  # title omitted, not nulled


def test_apply_config_required_missing_defaults_to_null():
    internal = {"candidate_id": "cand_0001"}
    cfg = config_loader.DEFAULT_CONFIG
    out = config_loader.apply_config(internal, cfg)
    assert out["full_name"] is None  # required but missing -> null, never crashes


# ----------------------------------------------------------- end to end ---

def test_end_to_end_sample_input_runs_without_crashing():
    output = run_pipeline(INPUT_DIR, config_path=None, verbose=False)
    assert isinstance(output, list)
    assert len(output) >= 3
    # Every candidate must be schema-valid JSON-serializable.
    json.dumps(output)
    names = [c["full_name"] for c in output if c["full_name"]]
    assert "John A. Doe" in names or "John Doe" in names
    # The deliberately empty/garbage ATS record must degrade to nulls, not crash.
    assert any(c["full_name"] is None for c in output)


def test_end_to_end_merges_john_doe_into_one_record():
    output = run_pipeline(INPUT_DIR, config_path=None, verbose=False)
    john_records = [c for c in output if c["emails"] and "john@gmail.com" in c["emails"]]
    assert len(john_records) == 1  # ats_json + recruiter_csv + resume_pdf all merged into one
