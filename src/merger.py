"""
merger.py
---------
Step 3 (MERGE) and Step 4 (RESOLVE CONFLICTS) of the pipeline.

Merge identity rule
--------------------
Two parsed records are considered the same person if:
  1. They share at least one normalized email address (strong signal), OR
  2. They have no email overlap but their normalized full names are a close
     fuzzy match (ratio >= NAME_MATCH_THRESHOLD) AND neither has an email
     that conflicts with the other's.
Records that match neither rule become their own single-record candidate
group. This mirrors how a human recruiter would dedupe: an email match is
near-certain identity; a name-only match is a "probably the same person"
heuristic and is scored lower in provenance.

Conflict resolution rule
-------------------------
For scalar fields (full_name, headline, company/title, location, ...),
conflicting values across sources are resolved using a configurable
SOURCE_PRIORITY order (highest-priority non-null value wins), as documented
in the technical design ("Resume > JSON > CSV > Notes" by default, since a
candidate's own resume is closest to ground truth, followed by the
recruiter's ATS record). Every resolution is written to `provenance` so the
decision is auditable. List fields (emails, phones, skills) are UNIONed
rather than conflict-resolved, since more contact info / more skills is
strictly more useful and rarely wrong.
For experience/education lists, entries are merged by (company,title)
key; when end dates disagree, the candidate's own resume (or, absent a
resume, the most recently-dated source) wins -- "latest evidence wins".
"""
from rapidfuzz import fuzz

from . import normalizer as N

NAME_MATCH_THRESHOLD = 88

DEFAULT_SOURCE_PRIORITY = ["resume_pdf", "ats_json", "recruiter_csv", "recruiter_notes"]


def _priority_rank(source_type, priority_list):
    try:
        return priority_list.index(source_type)
    except ValueError:
        return len(priority_list)  # unknown sources sort last


def _norm_emails(rec):
    return {e for e in (N.normalize_email(x) for x in rec.get("emails") or []) if e}


def group_records(records):
    """Cluster parsed records into candidate groups using the identity rule above."""
    groups = []  # list of {"records": [...], "emails": set(), "names": [str,...]}

    for rec in records:
        rec_emails = _norm_emails(rec)
        rec_name = N.normalize_name(rec.get("full_name"))

        match = None
        for g in groups:
            if rec_emails and rec_emails & g["emails"]:
                match = g
                break

        if match is None and rec_name:
            for g in groups:
                if g["emails"] and rec_emails and not (rec_emails & g["emails"]):
                    continue  # both have emails but they differ -> different people
                for other_name in g["names"]:
                    if other_name and fuzz.token_sort_ratio(rec_name, other_name) >= NAME_MATCH_THRESHOLD:
                        match = g
                        break
                if match:
                    break

        if match is None:
            match = {"records": [], "emails": set(), "names": []}
            groups.append(match)

        match["records"].append(rec)
        match["emails"] |= rec_emails
        if rec_name:
            match["names"].append(rec_name)

    return [g["records"] for g in groups]


def _resolve_scalar(field_name, records, priority_list, transform=None):
    """Pick the highest-priority non-null value for `field_name` across records.
    Returns (value, provenance_entry_or_None)."""
    candidates = [r for r in records if r.get(field_name)]
    if not candidates:
        return None, None
    candidates.sort(key=lambda r: _priority_rank(r["source_type"], priority_list))
    winner = candidates[0]
    value = winner[field_name]
    if transform:
        value = transform(value)
    method = "source_priority" if len(candidates) > 1 else "single_source"
    prov = {"field": field_name, "source": winner["source_type"], "method": method}
    return value, prov


def _merge_skills(records):
    seen = {}
    for r in records:
        for s in r.get("skills") or []:
            canon = N.normalize_skill(s)
            if not canon:
                continue
            key = canon.lower()
            entry = seen.setdefault(key, {"name": canon, "confidence": 0.0, "sources": []})
            entry["confidence"] = max(entry["confidence"], r.get("confidence", 0.5))
            if r["source_type"] not in entry["sources"]:
                entry["sources"].append(r["source_type"])
    # More corroborating sources -> higher confidence, capped at 0.99.
    out = []
    for entry in seen.values():
        boost = 0.1 * (len(entry["sources"]) - 1)
        entry["confidence"] = round(min(0.99, entry["confidence"] + boost), 2)
        out.append(entry)
    return sorted(out, key=lambda e: (-e["confidence"], e["name"]))


def _merge_experience(records, priority_list):
    by_key = {}
    for r in records:
        company = r.get("company")
        headline = r.get("headline")
        entries = r.get("experience") or []
        if not entries and (company or headline):
            entries = [{"company": company, "title": headline, "start": None, "end": None, "summary": None}]
        for e in entries:
            if not isinstance(e, dict):
                continue
            key = ((e.get("company") or "").strip().lower(), (e.get("title") or "").strip().lower())
            if key == ("", ""):
                continue
            rank = _priority_rank(r["source_type"], priority_list)
            existing = by_key.get(key)
            if existing is None or rank < existing["_rank"]:
                merged = dict(e)
                merged["start"] = N.normalize_date_yyyymm(e.get("start")) if e.get("start") else None
                merged["end"] = N.normalize_date_yyyymm(e.get("end")) if e.get("end") else None
                merged["_rank"] = rank
                merged["_source"] = r["source_type"]
                by_key[key] = merged
    out = []
    for v in by_key.values():
        v.pop("_rank", None)
        v.pop("_source", None)
        out.append(v)
    return out


def _merge_education(records):
    by_key = {}
    for r in records:
        for e in r.get("education") or []:
            if not isinstance(e, dict):
                continue
            key = ((e.get("institution") or "").strip().lower(), (e.get("degree") or "").strip().lower())
            if key == ("", ""):
                continue
            by_key.setdefault(key, e)
    return list(by_key.values())


def merge_group(records, source_priority=None):
    """Merge one candidate's records into a single canonical internal record."""
    priority_list = source_priority or DEFAULT_SOURCE_PRIORITY
    provenance = []

    def resolve(field, transform=None):
        value, prov = _resolve_scalar(field, records, priority_list, transform)
        if prov:
            provenance.append(prov)
        return value

    full_name = resolve("full_name", N.normalize_name)
    city = resolve("city")
    region = resolve("region")
    country = resolve("country", N.normalize_country)
    headline = resolve("headline")
    years_experience = resolve("years_experience")
    linkedin = resolve("linkedin")
    github = resolve("github")
    portfolio = resolve("portfolio")

    emails = sorted({e for r in records for e in (N.normalize_email(x) for x in r.get("emails") or []) if e})
    phones = sorted({p for r in records for e in [r.get("phones") or []] for p in (N.normalize_phone(x) for x in e) if p})
    if emails:
        provenance.append({"field": "emails", "source": "union_all_sources", "method": "union"})
    if phones:
        provenance.append({"field": "phones", "source": "union_all_sources", "method": "union"})

    skills = _merge_skills(records)
    if skills:
        provenance.append({"field": "skills", "source": "union_all_sources", "method": "union+corroboration_boost"})

    experience = _merge_experience(records, priority_list)
    education = _merge_education(records)

    confidences = [r.get("confidence", 0.5) for r in records]
    field_fill_bonus = 0.05 * min(len(records) - 1, 3)  # more corroborating sources -> small confidence boost
    overall_confidence = round(min(0.99, (sum(confidences) / len(confidences)) + field_fill_bonus), 2)

    record = {
        "candidate_id": None,  # assigned by caller after all groups are merged
        "full_name": full_name,
        "emails": emails,
        "phones": phones,
        "location": {"city": city, "region": region, "country": country} if (city or region or country) else None,
        "links": {
            "linkedin": linkedin,
            "github": github,
            "portfolio": portfolio,
            "other": [],
        },
        "headline": headline,
        "years_experience": years_experience,
        "skills": skills,
        "experience": experience,
        "education": education,
        "provenance": provenance,
        "overall_confidence": overall_confidence,
        "_source_files": sorted({r["source_file"] for r in records}),
    }
    return record


def merge_all(records, source_priority=None):
    """Full Step 3 + Step 4: group records into candidates, merge each group,
    and assign deterministic candidate_ids."""
    groups = group_records(records)
    merged = []
    for i, g in enumerate(groups, start=1):
        rec = merge_group(g, source_priority=source_priority)
        rec["candidate_id"] = f"cand_{i:04d}"
        merged.append(rec)
    return merged
