#!/usr/bin/env python3
"""Extract Cliffwater leverage and liquidity disclosures from report PDFs.

Outputs newline-delimited JSON (JSONL) blocks keyed off anchor phrases that are
useful for manual review or downstream parsing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import json
from pathlib import Path
from typing import Iterable, List, Sequence

from pdfminer.high_level import extract_text

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_DIR = ROOT / "data" / "processed"
DEFAULT_ANCHORS = [
    "Senior Credit Facility",
    "Senior Notes",
    "Liquidity",
    "Borrowings",
    "Repurchase program",
]


@dataclass
class ExtractionBlock:
    source: str
    label: str
    start: int
    end: int
    text: str


def extract_blocks(pdf_path: Path, anchors: Iterable[str], window: int = 4000) -> List[ExtractionBlock]:
    text = extract_text(str(pdf_path))
    lower = text.lower()
    blocks: List[ExtractionBlock] = []
    for label in anchors:
        idx = lower.find(label.lower())
        if idx == -1:
            continue
        end = min(len(text), idx + window)
        blocks.append(
            ExtractionBlock(
                source=pdf_path.name,
                label=label,
                start=idx,
                end=end,
                text=text[idx:end].strip(),
            )
        )
    return blocks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pattern",
        default="CCLFX-*.pdf",
        help="Glob pattern for PDFs inside data/raw (default: %(default)s)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=4000,
        help="Characters to keep after each anchor hit (default: %(default)s)",
    )
    parser.add_argument(
        "--anchor",
        action="append",
        dest="anchors",
        help="Anchor phrase to search for; may be supplied multiple times. Defaults are used if omitted.",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR / "cliffwater_blocks.jsonl"),
        help="Output JSONL path (default: %(default)s)",
    )
    return parser


def iter_pdfs(pattern: str) -> Sequence[Path]:
    return sorted(RAW_DIR.glob(pattern))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    pdfs = iter_pdfs(args.pattern)
    if not pdfs:
        parser.error(f"No PDFs matched pattern {args.pattern!r} in {RAW_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    anchors = args.anchors or DEFAULT_ANCHORS
    out_path = Path(args.output).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results: List[ExtractionBlock] = []
    for pdf in pdfs:
        results.extend(extract_blocks(pdf, anchors, window=args.window))

    with out_path.open("w", encoding="utf-8") as fh:
        for block in results:
            fh.write(json.dumps(asdict(block), ensure_ascii=False) + "\n")

    print(f"Wrote {len(results)} blocks from {len(pdfs)} PDFs to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
