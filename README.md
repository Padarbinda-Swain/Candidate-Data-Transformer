# 🚀 Multi-Source Candidate Data Transformer

A **Python-based ETL pipeline** that ingests candidate data from multiple structured and unstructured sources, normalizes the data, merges duplicate records, resolves conflicts, validates the output, and generates configurable canonical JSON profiles.

> **Built for the Eightfold Engineering Intern Assignment.**  
> See **`DESIGN.pdf`** for the complete technical design.

---

# 📌 Project Overview

Candidate information often comes from multiple sources such as:

- ATS JSON Export
- Recruiter CSV Export
- Resume PDF
- Recruiter Notes

Each source may have:

- Different field names
- Missing values
- Duplicate information
- Conflicting data

This project transforms all these sources into a **single normalized candidate profile** with:

- ✅ Deduplication
- ✅ Data Normalization
- ✅ Conflict Resolution
- ✅ Provenance Tracking
- ✅ Confidence Scoring
- ✅ Runtime Configurable Output

---

# 🏗️ Pipeline Architecture

| Stage | Module | Responsibility |
|--------|---------|----------------|
| 1️⃣ Extract | `extractor.py` | Read raw data from JSON, CSV, TXT and PDF |
| 2️⃣ Parse | `parser.py` | Convert source-specific fields into a common structure |
| 3️⃣ Normalize | `normalizer.py` | Normalize emails, phones, countries, skills and dates |
| 4️⃣ Merge | `merger.py` | Merge duplicate candidate records |
| 5️⃣ Resolve | `merger.py` | Resolve conflicting values using source priority |
| 6️⃣ Validate | `validator.py` | Ensure schema-valid output |
| 7️⃣ Project | `config_loader.py` | Generate configurable output using runtime config |

---

# 📂 Project Structure

```text
candidate-transformer/
│
├── config/
│   ├── config.json
│   └── config_custom.json
│
├── input/
│   ├── candidate_ats.json
│   ├── recruiter_export.csv
│   ├── recruiter_notes.txt
│   └── resume.pdf
│
├── output/
│   ├── output.json
│   ├── output_custom.json
│   └── .gitkeep
│
├── src/
│   ├── extractor.py
│   ├── parser.py
│   ├── normalizer.py
│   ├── merger.py
│   ├── validator.py
│   ├── config_loader.py
│   └── main.py
│
├── tests/
│   └── test_pipeline.py
│
├── README.md
├── DESIGN.pdf
├── requirements.txt
└── main.py
```

---

# ⚙️ Installation

Clone the repository

```bash
git clone <repository-url>
cd candidate-transformer
```

Create Virtual Environment

```bash
python -m venv venv
```

Activate

### Windows

```bash
venv\Scripts\activate
```

### Linux / macOS

```bash
source venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

---

# ▶️ Running the Project

Generate canonical output

```bash
python main.py input output/output.json
```

Generate custom output

```bash
python main.py input output/output_custom.json --config config/config_custom.json
```

Run all tests

```bash
pytest -q
```

---

# 📥 Sample Input

The **input/** folder contains:

| File | Type |
|------|------|
| candidate_ats.json | Structured |
| recruiter_export.csv | Structured |
| recruiter_notes.txt | Unstructured |
| resume.pdf | Unstructured |

These files intentionally contain overlapping candidate information to demonstrate data merging and conflict resolution.

---

# 📤 Sample Output

Each generated candidate profile contains:

- Candidate ID
- Full Name
- Contact Information
- Skills
- Experience
- Education
- Provenance
- Overall Confidence Score

Example:

```json
{
  "candidate_id": "cand_0001",
  "full_name": "John A. Doe",
  "emails": [
    "john@gmail.com"
  ],
  "phones": [
    "+919876543210"
  ],
  "headline": "Senior Backend Engineer",
  "overall_confidence": 0.83
}
```

---

# ⚡ Runtime Configuration

The project supports **runtime configurable output**.

Simply change

```
config/config.json
```

or

```
config/config_custom.json
```

without modifying any source code.

Features include:

- Rename fields
- Remove fields
- Nested objects
- Missing field handling
- Custom output schema

---

# 🔀 Merge Strategy

Candidate records are merged using:

- Email Match (Primary)
- Fuzzy Name Match (Secondary)

Conflict Resolution Priority

```
Resume PDF
        ↓
ATS JSON
        ↓
Recruiter CSV
        ↓
Recruiter Notes
```

The selected source is recorded in the **Provenance** field.

---

# 🛡️ Robustness

The pipeline safely handles:

- Unsupported file formats
- Malformed JSON
- Corrupted PDFs
- Missing values
- Invalid data types
- Empty input folders

Instead of crashing, invalid values are replaced with **null**.

---

# 🧪 Testing

Automated tests validate:

- Email Normalization
- Phone Normalization
- Country Normalization
- Candidate Merging
- Conflict Resolution
- Runtime Configuration
- End-to-End Pipeline Execution

Run

```bash
pytest -q
```

---

# 📄 Documentation

This repository includes:

- 📘 README.md
- 📑 DESIGN.pdf
- 🧪 Automated Test Suite
- ⚙️ Runtime Configurations
- 📥 Sample Input Files
- 📤 Sample Output Files

---

# 👨‍💻 Technologies Used

- Python 3
- pdfplumber
- RapidFuzz
- phonenumbers
- pycountry
- pytest

---

# 📜 License

This project was developed as part of the **Eightfold Engineering Intern Assignment** and is intended for educational and evaluation purposes.

---

## ⭐ Author

**Padarbinda Swain**

B.Tech CSE (Cyber Security)

SOA University
