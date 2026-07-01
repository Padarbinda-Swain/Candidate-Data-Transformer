"""
parser.py
---------
Bridges Step 1 (raw extraction) and Step 2 (normalization).

Real-world sources never use our field names. An ATS export might call the
name field "name", "full_name", or "candidate_name"; a recruiter CSV might
call it "Full Name". Rather than hardcoding ONE field name per source
(which would break the moment a new exporter is plugged in), we resolve
each canonical field through a small alias list. This is the
"detect -> extract" half of the pipeline described in the design doc; it is
intentionally separate from the runtime OUTPUT config (config_loader.py),
which only reshapes the *result*, not how we read messy inputs.

Output of this module: a list of ParsedRecord dicts, one per
candidate-shaped blob found in a source (a CSV with 3 rows yields 3
records; a single resume PDF yields 1 record), each tagged with
`source_file` / `source_type` for provenance and merge/conflict logic.
"""
import re

# Alias tables: canonical_field -> list of source key spellings to try, in order.
_ALIASES = {
    "full_name": ["full_name", "name", "candidate_name", "fullname", "Full Name"],
    "email": ["email", "primary_email", "emails", "Email"],
    "phone": ["phone", "phones", "mobile", "contact_number", "Phone"],
    "city": ["city", "location_city", "City"],
    "region": ["region", "state", "location_region", "State"],
    "country": ["country", "location_country", "Country"],
    "headline": ["headline", "title", "current_title", "Headline"],
    "company": ["company", "current_company", "employer", "Company"],
    "linkedin": ["linkedin", "linkedin_url", "LinkedIn"],
    "github": ["github", "github_url", "GitHub"],
    "portfolio": ["portfolio", "portfolio_url", "website"],
    "skills": ["skills", "skill_set", "Skills"],
    "years_experience": ["years_experience", "experience_years", "yoe"],
    "education": ["education", "education_history"],
    "experience": ["experience", "work_history", "employment_history"],
}


def _first(d, keys):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, "", []):
            return d[k]
    return None


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        # Recruiter CSV cells often store multi-values pipe- or comma- separated.
        parts = re.split(r"[|;,]", value)
        return [p.strip() for p in parts if p.strip()]
    return [value]


def _record_from_dict(d, source_file, source_type, base_confidence):
    rec = {
        "source_file": source_file,
        "source_type": source_type,
        "confidence": base_confidence,
        "full_name": _first(d, _ALIASES["full_name"]),
        "emails": _as_list(_first(d, _ALIASES["email"])),
        "phones": _as_list(_first(d, _ALIASES["phone"])),
        "city": _first(d, _ALIASES["city"]),
        "region": _first(d, _ALIASES["region"]),
        "country": _first(d, _ALIASES["country"]),
        "headline": _first(d, _ALIASES["headline"]),
        "company": _first(d, _ALIASES["company"]),
        "linkedin": _first(d, _ALIASES["linkedin"]),
        "github": _first(d, _ALIASES["github"]),
        "portfolio": _first(d, _ALIASES["portfolio"]),
        "skills": _as_list(_first(d, _ALIASES["skills"])),
        "years_experience": _first(d, _ALIASES["years_experience"]),
        "education": _first(d, _ALIASES["education"]) or [],
        "experience": _first(d, _ALIASES["experience"]) or [],
    }
    return rec


def parse_structured(source_file_obj):
    """ats_json -> 1 record. recruiter_csv -> N records (one per row)."""
    records = []
    if source_file_obj.source_type == "ats_json":
        data = source_file_obj.raw
        candidates = data if isinstance(data, list) else [data]
        for c in candidates:
            records.append(_record_from_dict(c, source_file_obj.path, "ats_json", 0.9))
    elif source_file_obj.source_type == "recruiter_csv":
        for row in source_file_obj.raw:
            records.append(_record_from_dict(row, source_file_obj.path, "recruiter_csv", 0.75))
    return records


# ---------------------------------------------------------- unstructured ---

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(\+?\d[\d\-\s()]{7,}\d)")
_LINKEDIN_RE = re.compile(r"(https?://)?(www\.)?linkedin\.com/in/[A-Za-z0-9_\-/]+", re.I)
_GITHUB_RE = re.compile(r"(https?://)?(www\.)?github\.com/[A-Za-z0-9_\-/]+", re.I)
_NAME_LINE_RE = re.compile(r"^\s*(?:Name|Candidate)\s*[:\-]\s*(.+)$", re.I | re.M)
_SKILLS_LINE_RE = re.compile(r"^\s*Skills?\s*[:\-]\s*(.+)$", re.I | re.M)
_COMPANY_LINE_RE = re.compile(r"^\s*(?:Company|Current Company|Employer)\s*[:\-]\s*(.+)$", re.I | re.M)
_TITLE_LINE_RE = re.compile(r"^\s*(?:Title|Role|Headline|Position)\s*[:\-]\s*(.+)$", re.I | re.M)
_YOE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?experience", re.I)


def parse_unstructured(source_file_obj):
    """Heuristic free-text parsing for resume PDFs / recruiter notes.
    Confidence is intentionally lower than structured sources -- regex
    extraction from prose is inherently less reliable."""
    text = source_file_obj.raw or ""
    base_conf = 0.55 if source_file_obj.source_type == "resume_pdf" else 0.45

    name = None
    m = _NAME_LINE_RE.search(text)
    if m:
        name = m.group(1).strip()
    elif source_file_obj.source_type == "resume_pdf":
        # Heuristic: resumes conventionally open with the candidate's name
        # on the first non-empty line.
        for line in text.splitlines():
            line = line.strip()
            if line and len(line.split()) <= 5 and not _EMAIL_RE.search(line):
                name = line
                break

    emails = list(dict.fromkeys(_EMAIL_RE.findall(text)))
    phones = list(dict.fromkeys(m.strip() for m in _PHONE_RE.findall(text)))
    linkedin_m = _LINKEDIN_RE.search(text)
    github_m = _GITHUB_RE.search(text)

    skills = []
    sm = _SKILLS_LINE_RE.search(text)
    if sm:
        skills = [s.strip() for s in re.split(r"[,/|]", sm.group(1)) if s.strip()]

    company = None
    cm = _COMPANY_LINE_RE.search(text)
    if cm:
        company = cm.group(1).strip()

    headline = None
    tm = _TITLE_LINE_RE.search(text)
    if tm:
        headline = tm.group(1).strip()

    years_experience = None
    ym = _YOE_RE.search(text)
    if ym:
        years_experience = float(ym.group(1))

    rec = {
        "source_file": source_file_obj.path,
        "source_type": source_file_obj.source_type,
        "confidence": base_conf,
        "full_name": name,
        "emails": emails,
        "phones": phones,
        "city": None,
        "region": None,
        "country": None,
        "headline": headline,
        "company": company,
        "linkedin": linkedin_m.group(0) if linkedin_m else None,
        "github": github_m.group(0) if github_m else None,
        "portfolio": None,
        "skills": skills,
        "years_experience": years_experience,
        "education": [],
        "experience": [],
        "raw_text": text,
    }
    return [rec]


def parse_source(source_file_obj):
    if source_file_obj.group == "structured":
        return parse_structured(source_file_obj)
    return parse_unstructured(source_file_obj)
