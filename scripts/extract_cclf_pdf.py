#!/usr/bin/env python3
"""Convert Cliffwater report PDFs in data/raw into plaintext sidecar files."""
from __future__ import annotations

from pathlib import Path

from pdfminer.high_level import extract_text

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
REPORT_FILES = [
    RAW_DIR / "CCLFX-Annual-Report.pdf",
    RAW_DIR / "CCLFX-Semi-Annual-Report.pdf",
]


def dump_plaintext() -> None:
    missing = [path for path in REPORT_FILES if not path.exists()]
    if missing:
        missing_text = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Missing expected report file(s):\n{missing_text}")

    for pdf_path in REPORT_FILES:
        text = extract_text(str(pdf_path))
        out_path = pdf_path.with_suffix(".txt")
        out_path.write_text(text, encoding="utf-8")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    dump_plaintext()
