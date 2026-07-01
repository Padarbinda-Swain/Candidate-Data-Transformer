#!/usr/bin/env python3
"""Thin convenience wrapper so the command from the assignment brief
(`python main.py input_folder output.json`) works when run from the repo
root. The real implementation lives in src/main.py."""
from src.main import main

if __name__ == "__main__":
    main()
