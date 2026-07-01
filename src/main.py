#!/usr/bin/env python3
"""
main.py
-------
CLI entrypoint for the Eightfold Multi-Source Candidate Data Transformer.

Usage:
    python main.py <input_folder> <output.json> [--config config/config.json]

Pipeline (see DESIGN.pdf for the full architecture write-up):
    1. EXTRACT    extractor.py   read every file in input_folder
    2. PARSE      parser.py      shape raw data into per-candidate records,
                                  resolving each source's own field names
    3. NORMALIZE  normalizer.py  clean emails/phones/countries/dates/skills
    4. MERGE      merger.py      group records into candidates (dedupe)
    5. RESOLVE    merger.py      pick winning values on conflict, with
                                  full provenance tracking
    6. VALIDATE   validator.py   guarantee schema-valid output, nulls not crashes
    7. PROJECT    config_loader  reshape into the user-configured output schema
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import extractor, parser, merger, validator, config_loader
from src import normalizer as N


def run_pipeline(input_folder, config_path=None, source_priority=None, verbose=True):
    # --- Step 1: Extract -------------------------------------------------
    source_files, skipped = extractor.extract_folder(input_folder)
    if verbose:
        print(f"[extract] read {len(source_files)} file(s) from {input_folder}")
        for s in skipped:
            print(f"[extract] WARNING skipped unsupported/broken file: {s}")

    # --- Step 2: Parse (per-source field-name resolution) ----------------
    all_records = []
    for sf in source_files:
        try:
            recs = parser.parse_source(sf)
            all_records.extend(recs)
        except Exception as e:
            print(f"[parse] WARNING failed to parse {sf.path}: {e}")
    if verbose:
        print(f"[parse]   produced {len(all_records)} raw candidate record(s)")

    # --- Step 3: Normalize per-field --------------------------------------
    for r in all_records:
        r["emails"] = [e for e in (N.normalize_email(x) for x in r.get("emails") or []) if e]
        r["phones"] = [p for p in (N.normalize_phone(x) for x in r.get("phones") or []) if p]
        r["country"] = N.normalize_country(r.get("country")) if r.get("country") else r.get("country")
        r["full_name"] = N.normalize_name(r.get("full_name")) if r.get("full_name") else None
        r["skills"] = [s for s in r.get("skills") or [] if s]
    if verbose:
        print("[normalize] applied email/phone/country/name/skill normalization")

    # --- Step 4 + 5: Merge & resolve conflicts ----------------------------
    merged = merger.merge_all(all_records, source_priority=source_priority)
    if verbose:
        print(f"[merge]   grouped into {len(merged)} unique candidate(s)")

    # --- Step 6: Validate --------------------------------------------------
    clean, warnings = validator.validate_all(merged)
    if verbose and warnings:
        for cid, msgs in warnings.items():
            for m in msgs:
                print(f"[validate] WARNING {cid}: {m}")

    # --- Step 7: Project through runtime config -----------------------------
    config = config_loader.load_config(config_path)
    final_output = [config_loader.apply_config(rec, config) for rec in clean]
    if verbose:
        print(f"[project] applied config ({'default' if not config_path else config_path})")

    return final_output


def main():
    ap = argparse.ArgumentParser(description="Multi-Source Candidate Data Transformer")
    ap.add_argument("input_folder", help="Folder containing source files (json/csv/pdf/txt)")
    ap.add_argument("output_json", help="Path to write the canonical output JSON")
    ap.add_argument("--config", default=None, help="Path to runtime projection config.json")
    ap.add_argument("--source-priority", default=None,
                     help="Comma-separated source_type priority for conflict resolution, "
                          "e.g. resume_pdf,ats_json,recruiter_csv,recruiter_notes")
    ap.add_argument("--quiet", action="store_true", help="Suppress step-by-step log output")
    args = ap.parse_args()

    priority = args.source_priority.split(",") if args.source_priority else None

    try:
        output = run_pipeline(args.input_folder, config_path=args.config,
                               source_priority=priority, verbose=not args.quiet)
    except Exception as e:
        # Top-level safety net: per the "Robust" constraint, the run itself
        # must not crash even on unexpected errors -- emit an empty,
        # schema-valid result and a clear diagnostic instead.
        print(f"[fatal] pipeline error: {e}", file=sys.stderr)
        output = []

    os.makedirs(os.path.dirname(os.path.abspath(args.output_json)) or ".", exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    if not args.quiet:
        print(f"[done]    wrote {len(output)} candidate record(s) -> {args.output_json}")


if __name__ == "__main__":
    main()
