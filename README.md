# Multi-Source Candidate Data Transformer

An ETL pipeline that ingests candidate data from several differently-shaped
sources (ATS JSON export, recruiter CSV export, resume PDF, recruiter
notes .txt) and produces one deduplicated, schema-valid, confidence-scored
canonical JSON profile per candidate.

Built for the Eightfold "Multi-Source Candidate Data Transformer" take-home
assignment. See `DESIGN.pdf` for the full one-page technical design.

## Project description

Eightfold ingests candidate data from many places at once, and every source
has its own field names, its own missing/garbage values, and sometimes
disagrees with the others about the same fact. This project turns that mess
into one clean, normalized, provenance-tracked profile per person, with a
runtime-configurable output shape so downstream consumers can rename/select
fields without touching code.

Pipeline stages (one module each, `src/`):

| Stage | Module | Responsibility |
|---|---|---|
| 1. Extract | `extractor.py` | Read raw bytes/text from each file type |
| 2. Parse | `parser.py` | Resolve each source's own field names into a common shape |
| 3. Normalize | `normalizer.py` | Clean emails, phones (E.164), countries (ISO-3166), dates, skills |
| 4. Merge | `merger.py` | Group records into one candidate per real person |
| 5. Resolve conflicts | `merger.py` | Pick winning values via configurable source priority, with provenance |
| 6. Validate | `validator.py` | Guarantee schema-valid output; missing -> `null`, never a crash |
| 7. Project | `config_loader.py` | Reshape the result per the runtime `config.json` |

## Installation

```bash
git clone <this-repo>
cd candidate-transformer
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
```

## How to run

```bash
python main.py input output/output.json --config config/config.json
```

Arguments:
- `input_folder` — folder containing source files (any mix of `.json`, `.csv`, `.pdf`, `.txt`)
- `output.json` — where the canonical JSON array gets written
- `--config` (optional) — path to a runtime projection config; omit to use the built-in default schema
- `--source-priority` (optional) — comma-separated source-type priority for conflict resolution, e.g. `resume_pdf,ats_json,recruiter_csv,recruiter_notes` (this is the default)
- `--quiet` — suppress the step-by-step log lines

A second, pre-built example config (`config/config_custom.json`) demonstrates
renaming (`full_name` → `name`), nesting (`emails`/`phones` → `contact.*`),
dropping fields (no `experience`/`education`), and omit-on-missing behavior:

```bash
python main.py input output/output_custom.json --config config/config_custom.json
```

### Run the tests

```bash
pytest -q
```

## Sample input

`input/` contains 4 sample source files spanning both required groups:

- `candidate_ats.json` — **structured**, ATS export (3 records, including one
  deliberately empty/garbage record to exercise the "must not crash" path)
- `recruiter_export.csv` — **structured**, recruiter export with its own
  column names (`Full Name`, `current_company`, ...)
- `resume.pdf` — **unstructured**, a generated one-page resume for "John A. Doe"
- `recruiter_notes.txt` — **unstructured**, free-text recruiter notes for "Priya Sharma"

These are wired together on purpose: "John Doe" (ATS) / "John A. Doe" (CSV,
resume) is the same person across 3 sources with a name spelling difference
and a real conflict (ATS says `IBM`, CSV says `Infosys`, the resume — the
highest-priority source — also says `IBM`, so `IBM` wins).

## Sample output

```json
{
  "candidate_id": "cand_0001",
  "full_name": "John A. Doe",
  "emails": ["john@gmail.com"],
  "phones": ["+919876543210"],
  "location": { "city": "Bengaluru", "region": null, "country": "IN" },
  "links": { "linkedin": "linkedin.com/in/johnadoe", "github": "github.com/johnadoe", "portfolio": null, "other": [] },
  "headline": "Senior Backend Engineer",
  "years_experience": 5.0,
  "skills": [
    { "name": "Python", "confidence": 0.99, "sources": ["ats_json", "recruiter_csv", "resume_pdf"] }
  ],
  "experience": [
    { "company": "IBM", "title": "Senior Software Engineer", "start": null, "end": null, "summary": null }
  ],
  "education": [],
  "provenance": [
    { "field": "headline", "source": "resume_pdf", "method": "source_priority" }
  ],
  "overall_confidence": 0.83
}
```

Full output: `output/output.json`. The 4th record in that file is the
deliberately empty ATS row — it produces a schema-valid record full of
`null`s rather than crashing the run.

## Design decisions

**Identity / merge rule.** Two records are the same candidate if they share
a normalized email (high confidence), or — absent any email overlap — if
their normalized full names fuzzy-match above a threshold (88, via
`rapidfuzz.token_sort_ratio`). Records with conflicting emails are never
merged on name alone, even if the names match exactly, since email is the
stronger identity signal.

**Conflict resolution rule.** Scalar fields are resolved by a configurable
source-priority order, default `resume_pdf > ats_json > recruiter_csv >
recruiter_notes` — the reasoning being that a candidate's own resume is
closest to ground truth, the ATS record is usually filled in carefully at
intake, a recruiter's CSV export can be stale, and free-text notes are the
least structured/reliable. Every resolution is recorded in `provenance` so
the decision is auditable. List fields (`emails`, `phones`, `skills`) are
**unioned**, not conflict-resolved — more contact info or more corroborated
skills is strictly more useful, never wrong, and a skill seen in multiple
sources gets a small confidence boost.

**Runtime config (no code changes).** `config_loader.py` applies a small
projection DSL on top of the internal canonical record: each output field
declares its target `path` and the internal `from` path (dot + `[]` list
syntax), with `required`/`on_missing` controlling null vs. omit vs. error
behavior. The pipeline's internal engine never changes — only the final
reshape does — which keeps extraction/merge logic stable while still
satisfying "changing the config should change the output without changing
code."

**Robustness.** Every extraction step is wrapped so that one bad/garbage/
unsupported file degrades the run instead of crashing it: unknown
extensions are skipped with a warning, unparseable PDFs yield empty text,
malformed JSON/CSV rows are logged and skipped, and any value that doesn't
fit the schema's expected type is coerced to `null` in `validator.py`
rather than raised. A top-level `try/except` in `main.py` further guarantees
the CLI always writes a (possibly empty) schema-valid JSON file rather than
exiting with an unhandled traceback.

**Assumptions.**
- Default phone region for E.164 parsing is `IN` (configurable via
  `--source-priority`'s sibling flag would be a natural extension; today it's
  a constant in `normalizer.py`) since the sample sources are India-based.
- Free-text resume/notes parsing uses lightweight regex heuristics
  (`Name:`, `Skills:`, email/phone/LinkedIn/GitHub patterns, an "N years
  experience" phrase) rather than an LLM or full NLP pipeline, to keep the
  solution dependency-light and deterministic for grading; documented as a
  "lower priority" trade-off per the assignment brief.
- `years_experience` and dates favor the highest-priority source on
  conflict rather than always taking "the largest number," since a stale
  source might overstate it.

## Edge cases covered

1. **Same person, different name spelling** across 3 sources, merged via
   shared email (`John Doe` / `John A. Doe`).
2. **Conflicting field values** (`company = IBM` vs `Infosys`) resolved by
   source-priority rule, with the decision recorded in `provenance`.
3. **Completely empty/garbage structured record** (blank ATS row) — produces
   a schema-valid all-`null` candidate instead of crashing.
4. **Unsupported file extension** in the input folder — skipped with a
   warning, run continues.
5. **Malformed JSON file** — caught, logged, skipped, run continues.
6. **Empty input folder** — produces a valid empty `[]` output.

## Folder structure

```
candidate-transformer/
├── input/                  sample source files
├── output/                 generated output JSON
├── config/                 runtime projection configs
├── src/                    pipeline modules
├── tests/                  pytest suite
├── DESIGN.pdf              one-page technical design (Step 1 deliverable)
├── main.py                 CLI entrypoint (thin wrapper over src/main.py)
├── requirements.txt
└── README.md
```
#   C a n d i d a t e - D a t a - T r a n s f o r m e r  
 