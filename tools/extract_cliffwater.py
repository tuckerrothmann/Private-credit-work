#!/usr/bin/env python3
"""Utility to extract leverage and liquidity disclosures from Cliffwater PDFs."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List

from pdfminer.high_level import extract_text

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"

@dataclass
class ExtractionBlock:
    source: str
    label: str
    text: str


def extract_blocks(pdf_path: Path, anchors: Iterable[str]) -> List[ExtractionBlock]:
    text = extract_text(pdf_path)
    lower = text.lower()
    blocks: List[ExtractionBlock] = []
    for label in anchors:
        idx = lower.find(label.lower())
        if idx == -1:
            continue
        snippet = text[idx: idx + 4000]
        blocks.append(ExtractionBlock(source=pdf_path.name, label=label, text=snippet))
    return blocks


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    anchors = [
        "Senior Credit Facility",
        "Senior Notes",
        "Liquidity",
        "Borrowings",
        "Repurchase program",
    ]
    results: List[ExtractionBlock] = []
    for pdf in RAW_DIR.glob("CCLFX-*.pdf"):
        results.extend(extract_blocks(pdf, anchors))
    out_path = OUTPUT_DIR / "cliffwater_blocks.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for block in results:
            fh.write(asdict(block).__repr__() + "\n")
    print(f"Wrote {len(results)} blocks to {out_path}")


if __name__ == "__main__":
    main()
