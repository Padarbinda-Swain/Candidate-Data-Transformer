"""
normalizer.py
-------------
Step 2 of the pipeline: NORMALIZE.

Pure functions that take one messy value and return one clean value (or
None if it cannot be normalized). Nothing here knows about "candidates" or
"sources" -- that keeps these functions trivially testable in isolation.
"""
import re
import datetime

try:
    import phonenumbers
except ImportError:
    phonenumbers = None

try:
    import pycountry
except ImportError:
    pycountry = None


# ---------------------------------------------------------------- email ---

def normalize_email(value):
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    if "@" not in v or "." not in v.split("@")[-1]:
        return None
    return v


# ---------------------------------------------------------------- phone ---

def normalize_phone(value, default_region="IN"):
    """Best-effort E.164 normalization. Falls back to a digits-only string
    if the phonenumbers library can't parse it, rather than dropping the
    value -- a malformed phone is still a useful (if low-confidence) lead."""
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if phonenumbers:
        try:
            parsed = phonenumbers.parse(raw, default_region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            pass
    digits = re.sub(r"\D", "", raw)
    return digits or None


# -------------------------------------------------------------- country ---

def normalize_country(value):
    """Map a free-text country name (or existing code) to ISO-3166 alpha-2."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    if len(v) == 2 and v.isalpha():
        return v.upper()
    if not pycountry:
        return v
    try:
        match = pycountry.countries.search_fuzzy(v)
        if match:
            return match[0].alpha_2
    except Exception:
        pass
    return v


# ----------------------------------------------------------------- date ---

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def normalize_date_yyyymm(value):
    """Normalize a wide range of date spellings to 'YYYY-MM'.
    Returns None for unparseable or open-ended ("present", "current") dates
    -- callers should treat None+is_current as 'still ongoing'."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in ("present", "current", "now", "ongoing", ""):
        return None

    m = re.match(r"^(\d{4})-(\d{1,2})$", v)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"

    m = re.match(r"^(\d{4})$", v)
    if m:
        return f"{m.group(1)}-01"

    m = re.match(r"^([a-z]+)[\s,\-]+(\d{4})$", v)
    if m and m.group(1) in _MONTHS:
        return f"{m.group(2)}-{_MONTHS[m.group(1)]:02d}"

    m = re.match(r"^(\d{1,2})/(\d{4})$", v)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"

    return None


# --------------------------------------------------------------- skills ---

# A small canonical skill table: maps common spelling/casing/alias variants
# to one canonical display name. In a production system this would be a
# config-driven lookup or an embeddings-based matcher; a static table is
# enough to demonstrate the normalization contract for this assignment.
_SKILL_CANON = {
    "js": "JavaScript", "javascript": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "py": "Python", "python": "Python", "python3": "Python",
    "reactjs": "React", "react.js": "React", "react": "React",
    "nodejs": "Node.js", "node.js": "Node.js", "node": "Node.js",
    "c++": "C++", "cpp": "C++",
    "c#": "C#", "csharp": "C#",
    "sql": "SQL", "mysql": "MySQL", "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "aws": "AWS", "amazon web services": "AWS",
    "gcp": "GCP", "google cloud": "GCP", "google cloud platform": "GCP",
    "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "nlp": "NLP", "natural language processing": "NLP",
    "html": "HTML", "html5": "HTML", "css": "CSS", "css3": "CSS",
    "git": "Git", "github": "Git",
    "rest api": "REST APIs", "rest apis": "REST APIs", "restful api": "REST APIs",
    "wireshark": "Wireshark", "nmap": "Nmap",
    "tls": "TLS Cryptography", "tls cryptography": "TLS Cryptography",
    "cybersecurity": "Cybersecurity", "cyber security": "Cybersecurity",
    "java": "Java",
    "flask": "Flask", "django": "Django",
    "devops": "DevOps",
}


def normalize_skill(value):
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    key = v.lower()
    return _SKILL_CANON.get(key, v.title() if v.isupper() or v.islower() else v)


def normalize_name(value):
    if not value or not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value.strip())


def normalize_string(value):
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        return v or None
    return value
