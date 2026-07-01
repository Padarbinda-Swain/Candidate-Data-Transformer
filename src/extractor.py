"""
extractor.py
------------
Step 1 of the pipeline: EXTRACT.

Responsible only for turning a file on disk into raw Python data
(dict / list of rows / plain text) -- no field renaming, no normalization,
no merging happens here. Keeping extraction "dumb" makes it easy to add a
new source type later: write one function that returns raw data, register
its extension/shape, done.

Supported source types:
  Structured   : .json (ATS / recruiter export), .csv (recruiter rows)
  Unstructured : .txt (recruiter notes / GitHub-readme-style blobs),
                 .pdf (resume)

Each extractor returns a SourceFile object so downstream code knows the
file's path, its group ("structured" / "unstructured"), and a best-guess
source_type label used later for conflict-resolution priority.
"""
import csv
import json
import os
from dataclasses import dataclass, field


@dataclass
class SourceFile:
    path: str
    group: str          # "structured" | "unstructured"
    source_type: str     # e.g. "ats_json", "recruiter_csv", "resume_pdf", "recruiter_notes"
    raw: object          # dict, list[dict], or str depending on source_type


def extract_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return SourceFile(path=path, group="structured", source_type="ats_json", raw=data)


def extract_csv(path):
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    # A recruiter CSV export is one row per candidate; we treat each row as
    # its own SourceFile-equivalent record upstream, so return the list raw.
    return SourceFile(path=path, group="structured", source_type="recruiter_csv", raw=rows)


def extract_txt(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    return SourceFile(path=path, group="unstructured", source_type="recruiter_notes", raw=text)


def extract_pdf(path):
    text_chunks = []
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                text_chunks.append(t)
    except Exception:
        # Degrade gracefully per the "Robust" constraint -- a malformed/
        # unreadable PDF should not crash the run, just yield empty text.
        text_chunks = []
    return SourceFile(path=path, group="unstructured", source_type="resume_pdf", raw="\n".join(text_chunks))


EXTENSION_MAP = {
    ".json": extract_json,
    ".csv": extract_csv,
    ".txt": extract_txt,
    ".pdf": extract_pdf,
}


def extract_folder(input_folder):
    """Walk a folder and extract every recognized file. Unknown extensions
    are skipped (robust: garbage/unsupported files do not crash the run)."""
    results = []
    skipped = []
    for fname in sorted(os.listdir(input_folder)):
        fpath = os.path.join(input_folder, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[1].lower()
        fn = EXTENSION_MAP.get(ext)
        if fn is None:
            skipped.append(fname)
            continue
        try:
            results.append(fn(fpath))
        except Exception as e:
            # A single bad file should never take down the whole run.
            skipped.append(f"{fname} (error: {e})")
    return results, skipped
