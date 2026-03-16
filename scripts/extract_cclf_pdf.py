"""Extract leverage tables from Cliffwater PDFs.

This is a work-in-progress parser that will eventually emit structured JSON/CSV
for the liquidity model. For now it just sets up the plumbing around pdfminer.
"""

from pathlib import Path

from pdfminer.high_level import extract_text

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

REPORT_FILES = [
    RAW_DIR / "CCLFX-Annual-Report.pdf",
    RAW_DIR / "CCLFX-Semi-Annual-Report.pdf",
]


def dump_plaintext():
    for pdf_path in REPORT_FILES:
        text = extract_text(pdf_path)
        out_path = pdf_path.with_suffix(".txt")
        out_path.write_text(text, encoding="utf-8")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    dump_plaintext()
