"""
refresh.py — Automated weekly refresh for the BDC surveillance system.

Workflow
--------
1. Check EDGAR for 10-K/10-Q filings newer than what we have cached.
2. Re-run portfolio_collector for any fund with a new filing.
3. Re-score all funds using the latest data.
4. Diff current scores against the stored score history.
5. Print a digest; optionally email it; write digest to data/processed/.

Usage
-----
    python refresh.py                       # check + update + diff
    python refresh.py --force               # re-parse all funds regardless
    python refresh.py --score-only          # skip filing check; just re-score + diff
    python refresh.py --notify you@x.com   # email digest after run
    python refresh.py --dry-run            # show what would change, write nothing

Scheduling (Windows Task Scheduler)
------------------------------------
    Action:  python C:\\path\\to\\refresh.py --notify you@example.com
    Trigger: Weekly, Sunday 07:00

Environment variables (optional, in .env):
    SMTP_HOST   SMTP_PORT   SMTP_USER   SMTP_PASS   SMTP_FROM
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

UNIVERSE_PATH    = Path("data/bdc_universe.json")
SCORES_HISTORY   = Path("data/scores_history.json")
DIGEST_PATH      = Path("data/processed/refresh_digest.md")
PORTFOLIO_CACHE  = Path("data/portfolio_cache")
EDGAR_CACHE      = Path("data/edgar_cache")

_RATE_DELAY = 0.15
_LAST_REQ: float = 0.0


# ---------------------------------------------------------------------------
# Score record (persisted between runs)
# ---------------------------------------------------------------------------

@dataclass
class ScoreRecord:
    ticker:   str
    score:    int
    tier:     str
    flags:    list[str]
    na_rate:  Optional[float]
    as_of:    str   # ISO date string of latest cache file

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ScoreRecord":
        return cls(**d)


@dataclass
class ScoreDiff:
    ticker:          str
    old:             ScoreRecord
    new:             ScoreRecord
    tier_changed:    bool
    tier_direction:  str   # "upgraded" (better) | "downgraded" (worse) | ""
    score_delta:     int
    new_flags:       list[str]
    cleared_flags:   list[str]

    @property
    def is_significant(self) -> bool:
        return self.tier_changed or abs(self.score_delta) >= 2 or bool(self.new_flags)


_TIER_ORDER = {"GREEN": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}


# ---------------------------------------------------------------------------
# EDGAR helpers (minimal — mirrors portfolio_collector)
# ---------------------------------------------------------------------------

import urllib.request
import urllib.error

_EDGAR_BASE = "https://data.sec.gov"
_HEADERS    = {"User-Agent": "private-research/1.0 jroth@example.com"}


def _fetch_json(url: str) -> dict:
    global _LAST_REQ
    wait = _RATE_DELAY - (time.time() - _LAST_REQ)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    _LAST_REQ = time.time()
    return data


def _get_latest_10kq_period(cik: str, allow_cache_write: bool = True) -> Optional[str]:
    """Return the reportDate of the most recent 10-K or 10-Q for this CIK."""
    padded = cik.zfill(10)
    cache_path = EDGAR_CACHE / "submissions" / f"CIK{padded}.json"

    # Use cache if fresh (< 24 h)
    if cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_h < 24:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            data = None
    else:
        data = None

    if data is None:
        try:
            url  = f"{_EDGAR_BASE}/submissions/CIK{padded}.json"
            data = _fetch_json(url)
            if allow_cache_write:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            return None

    filings = data.get("filings", {}).get("recent", {})
    forms   = filings.get("form", [])
    periods = filings.get("reportDate", [])

    for form, period in zip(forms, periods):
        if form in ("10-K", "10-Q") and period:
            return period

    return None


# ---------------------------------------------------------------------------
# Filing freshness check
# ---------------------------------------------------------------------------

def _latest_cached_period(ticker: str) -> Optional[str]:
    """Return the most recent period we have in portfolio_cache for this ticker."""
    files = sorted(PORTFOLIO_CACHE.glob(f"{ticker}_*.json"))
    # Filter out internal files like _sub_*, _facts_*, _tickers.json
    period_files = [f for f in files if not f.stem.startswith("_")]
    if not period_files:
        return None
    # Stem is "TICKER_YYYY-MM-DD"; extract the date
    return period_files[-1].stem.split("_", 1)[1]


def check_new_filings(
    funds: list[dict],
    verbose: bool = True,
    dry_run: bool = False,
) -> dict[str, str]:
    """
    For each listed BDC, compare the latest EDGAR 10-K/10-Q period against
    the most recent portfolio_cache file.

    Returns {ticker: edgar_period} for funds that have a newer filing.
    """
    stale: dict[str, str] = {}

    listed = [f for f in funds if f.get("type") == "listed_bdc" and f.get("sec_cik")]
    if verbose:
        print(f"Checking EDGAR for new filings ({len(listed)} listed BDCs)...")

    for fund in listed:
        ticker = fund["ticker"]
        cik    = str(fund["sec_cik"])
        edgar_period  = _get_latest_10kq_period(cik, allow_cache_write=not dry_run)
        cached_period = _latest_cached_period(ticker)

        if edgar_period is None:
            if verbose:
                print(f"  {ticker:<8} [!] could not fetch EDGAR period")
            continue

        if cached_period is None or edgar_period > cached_period:
            stale[ticker] = edgar_period
            if verbose:
                print(f"  {ticker:<8} new filing: {edgar_period}  (have: {cached_period or 'none'})")
        else:
            if verbose:
                print(f"  {ticker:<8} up to date ({cached_period})")

    return stale


# ---------------------------------------------------------------------------
# Refresh runner
# ---------------------------------------------------------------------------

def run_collection(tickers: list[str], verbose: bool = True) -> None:
    """Run portfolio_collector for *tickers* to pull the latest SOI data."""
    if not tickers:
        return

    if verbose:
        print(f"\nCollecting SOI data for: {', '.join(tickers)}")

    # Call portfolio_collector's main collection logic directly
    import subprocess, sys
    cmd = [sys.executable, "portfolio_collector.py", "--tickers"] + tickers
    result = subprocess.run(cmd, capture_output=not verbose, text=True)
    if result.returncode != 0 and not verbose:
        print(f"  [!] portfolio_collector failed:\n{result.stderr[-500:]}")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_all_funds(verbose: bool = False) -> dict[str, ScoreRecord]:
    """Re-score all funds using the canonical enriched scoring universe."""
    from red_flag_screener import load_scoring_funds, score_fund

    funds = load_scoring_funds()
    records: dict[str, ScoreRecord] = {}

    for fund in funds:
        ticker = fund.get("ticker", "")
        sc     = score_fund(fund)
        period = _latest_cached_period(ticker) or fund.get("as_of", "")
        records[ticker] = ScoreRecord(
            ticker  = ticker,
            score   = sc["composite_score"],
            tier    = sc["risk_tier"],
            flags   = sorted(sc["flags_triggered"]),
            na_rate = fund.get("nonaccrual_pct_fair_value"),
            as_of   = period,
        )

    return records


# ---------------------------------------------------------------------------
# Score history persistence
# ---------------------------------------------------------------------------

def load_score_history() -> dict[str, ScoreRecord]:
    if not SCORES_HISTORY.exists():
        return {}
    try:
        raw = json.loads(SCORES_HISTORY.read_text(encoding="utf-8"))
        return {t: ScoreRecord.from_dict(v) for t, v in raw.items()}
    except Exception:
        return {}


def save_score_history(records: dict[str, ScoreRecord]) -> None:
    SCORES_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    SCORES_HISTORY.write_text(
        json.dumps({t: r.to_dict() for t, r in records.items()}, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------

def compute_diffs(
    old: dict[str, ScoreRecord],
    new: dict[str, ScoreRecord],
) -> list[ScoreDiff]:
    """Return a sorted list of ScoreDiffs for funds whose scores changed."""
    diffs: list[ScoreDiff] = []

    for ticker, new_rec in new.items():
        old_rec = old.get(ticker)
        if old_rec is None:
            # New fund — treat as if previous score was 0 / GREEN
            old_rec = ScoreRecord(
                ticker=ticker, score=0, tier="GREEN",
                flags=[], na_rate=None, as_of="",
            )

        old_flag_set = set(old_rec.flags)
        new_flag_set = set(new_rec.flags)

        new_flags     = sorted(new_flag_set - old_flag_set)
        cleared_flags = sorted(old_flag_set - new_flag_set)

        tier_changed = old_rec.tier != new_rec.tier
        old_order    = _TIER_ORDER.get(old_rec.tier, 0)
        new_order    = _TIER_ORDER.get(new_rec.tier, 0)

        direction = ""
        if tier_changed:
            direction = "downgraded" if new_order > old_order else "upgraded"

        diffs.append(ScoreDiff(
            ticker         = ticker,
            old            = old_rec,
            new            = new_rec,
            tier_changed   = tier_changed,
            tier_direction = direction,
            score_delta    = new_rec.score - old_rec.score,
            new_flags      = new_flags,
            cleared_flags  = cleared_flags,
        ))

    # Sort: tier changes first, then by abs score delta, then alpha
    diffs.sort(key=lambda d: (
        0 if d.tier_changed else 1,
        -abs(d.score_delta),
        d.ticker,
    ))
    return diffs


# ---------------------------------------------------------------------------
# Digest formatting
# ---------------------------------------------------------------------------

_TIER_COLOR = {
    "RED":    "#dc2626",
    "ORANGE": "#ea580c",
    "YELLOW": "#ca8a04",
    "GREEN":  "#16a34a",
}
_TIER_BG = {
    "RED":    "#fef2f2",
    "ORANGE": "#fff7ed",
    "YELLOW": "#fefce8",
    "GREEN":  "#f0fdf4",
}


def _tier_badge(tier: str) -> str:
    color = _TIER_COLOR.get(tier, "#6b7280")
    bg    = _TIER_BG.get(tier, "#f3f4f6")
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;'
        f'font-size:11px;font-weight:700;letter-spacing:0.06em;'
        f'color:{color};background:{bg};border:1px solid {color}40;">'
        f'{tier}</span>'
    )


def _arrow(direction: str) -> str:
    if direction == "downgraded":
        return '<span style="color:#dc2626;font-weight:700;">&#x2193;</span>'
    if direction == "upgraded":
        return '<span style="color:#16a34a;font-weight:700;">&#x2191;</span>'
    return ""


def format_digest(
    diffs:       list[ScoreDiff],
    new_filings: dict[str, str],
    run_dt:      str,
) -> tuple[str, str]:
    """Return (html, plain_text) tuple."""
    from price_feed import enrich_funds_with_prices
    from red_flag_screener import load_universe

    changed    = [d for d in diffs if d.score_delta != 0 or d.tier_changed or d.new_flags or d.cleared_flags]
    same       = [d for d in diffs if d not in changed]
    downgraded = [d for d in changed if d.tier_direction == "downgraded"]
    upgraded   = [d for d in changed if d.tier_direction == "upgraded"]
    score_only = [d for d in changed if not d.tier_changed]

    funds_with_prices = {
        f["ticker"]: f
        for f in enrich_funds_with_prices(load_universe())
    }

    # ── HTML ──────────────────────────────────────────────────────────────

    css = """
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
             max-width: 680px; margin: 32px auto; color: #111827;
             font-size: 14px; line-height: 1.6; background: #ffffff; }
      h1   { font-size: 20px; font-weight: 700; margin: 0 0 4px; color: #111827; }
      h2   { font-size: 13px; font-weight: 700; letter-spacing: 0.08em;
             text-transform: uppercase; color: #6b7280; margin: 28px 0 10px;
             padding-bottom: 6px; border-bottom: 1px solid #e5e7eb; }
      .meta { font-size: 12px; color: #6b7280; margin-bottom: 24px; }
      .stats { display: flex; gap: 12px; margin-bottom: 28px; flex-wrap: wrap; }
      .stat  { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
               padding: 10px 16px; text-align: center; min-width: 100px; }
      .stat-val { font-size: 22px; font-weight: 700; color: #111827; line-height: 1.1; }
      .stat-lbl { font-size: 11px; color: #6b7280; text-transform: uppercase;
                  letter-spacing: 0.05em; margin-top: 2px; }
      .change-row { display: flex; align-items: baseline; gap: 8px;
                    padding: 8px 0; border-bottom: 1px solid #f3f4f6; }
      .ticker { font-weight: 700; font-size: 14px; min-width: 52px; }
      .score-arrow { color: #6b7280; font-size: 13px; }
      .flag-list { font-size: 12px; color: #6b7280; margin: 2px 0 6px 60px; }
      table  { width: 100%; border-collapse: collapse; font-size: 13px; }
      th     { text-align: left; padding: 6px 10px; background: #f9fafb;
               border-bottom: 2px solid #e5e7eb; font-weight: 600;
               font-size: 11px; letter-spacing: 0.05em; text-transform: uppercase;
               color: #374151; }
      td     { padding: 7px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
      tr:hover td { background: #f9fafb; }
      .no-change { font-size: 12px; color: #9ca3af; line-height: 1.8; }
      .footer { margin-top: 36px; padding-top: 12px; border-top: 1px solid #e5e7eb;
                font-size: 11px; color: #9ca3af; }
    </style>
    """

    def stat_box(val: str, label: str) -> str:
        return (
            f'<div class="stat">'
            f'<div class="stat-val">{val}</div>'
            f'<div class="stat-lbl">{label}</div>'
            f'</div>'
        )

    sections: list[str] = []

    # Header
    sections.append(
        f'<h1>BDC Surveillance Digest</h1>'
        f'<div class="meta">{run_dt} &nbsp;·&nbsp; {len(diffs)} funds scored</div>'
    )

    # Stats row
    sections.append(
        f'<div class="stats">'
        + stat_box(str(len(new_filings)), "New Filings")
        + stat_box(str(len(downgraded)), "Downgrades")
        + stat_box(str(len(upgraded)),   "Upgrades")
        + stat_box(str(len(score_only)), "Score Moves")
        + stat_box(str(len(same)),       "Unchanged")
        + '</div>'
    )

    # Downgrades
    if downgraded:
        rows = []
        for d in downgraded:
            delta = f"{d.score_delta:+d} pts" if d.score_delta else "tier only"
            flags_html = ""
            if d.new_flags:
                flags_html += f'<div class="flag-list">&#x25b6; New: {", ".join(d.new_flags)}</div>'
            if d.cleared_flags:
                flags_html += f'<div class="flag-list">&#x2713; Cleared: {", ".join(d.cleared_flags)}</div>'
            rows.append(
                f'<div class="change-row">'
                f'{_arrow("downgraded")}'
                f'<span class="ticker">{d.ticker}</span>'
                f'{_tier_badge(d.old.tier)} &rarr; {_tier_badge(d.new.tier)}'
                f'<span class="score-arrow">&nbsp;{d.old.score} &rarr; {d.new.score} &nbsp;({delta})</span>'
                f'</div>{flags_html}'
            )
        sections.append('<h2>Downgrades</h2>' + "".join(rows))

    # Upgrades
    if upgraded:
        rows = []
        for d in upgraded:
            delta = f"{d.score_delta:+d} pts" if d.score_delta else "tier only"
            flags_html = ""
            if d.cleared_flags:
                flags_html += f'<div class="flag-list">&#x2713; Cleared: {", ".join(d.cleared_flags)}</div>'
            if d.new_flags:
                flags_html += f'<div class="flag-list">&#x25b6; New: {", ".join(d.new_flags)}</div>'
            rows.append(
                f'<div class="change-row">'
                f'{_arrow("upgraded")}'
                f'<span class="ticker">{d.ticker}</span>'
                f'{_tier_badge(d.old.tier)} &rarr; {_tier_badge(d.new.tier)}'
                f'<span class="score-arrow">&nbsp;{d.old.score} &rarr; {d.new.score} &nbsp;({delta})</span>'
                f'</div>{flags_html}'
            )
        sections.append('<h2>Upgrades</h2>' + "".join(rows))

    # Score-only changes
    if score_only:
        rows = []
        for d in score_only:
            flags_html = ""
            if d.new_flags:
                flags_html += f'<div class="flag-list">&#x25b6; New: {", ".join(d.new_flags)}</div>'
            if d.cleared_flags:
                flags_html += f'<div class="flag-list">&#x2713; Cleared: {", ".join(d.cleared_flags)}</div>'
            rows.append(
                f'<div class="change-row">'
                f'<span class="ticker">{d.ticker}</span>'
                f'{_tier_badge(d.new.tier)}'
                f'<span class="score-arrow">&nbsp;{d.old.score} &rarr; {d.new.score} &nbsp;({d.score_delta:+d} pts)</span>'
                f'</div>{flags_html}'
            )
        sections.append('<h2>Score Moves (same tier)</h2>' + "".join(rows))

    # New filings
    if new_filings:
        rows = [
            f'<div class="change-row"><span class="ticker">{t}</span>'
            f'<span class="score-arrow">{p}</span></div>'
            for t, p in sorted(new_filings.items())
        ]
        sections.append('<h2>New Filings Collected</h2>' + "".join(rows))

    # No change
    if same:
        tickers = " &nbsp; ".join(d.ticker for d in same)
        sections.append(
            f'<h2>No Change ({len(same)} funds)</h2>'
            f'<div class="no-change">{tickers}</div>'
        )

    # Full scorecard table
    table_rows = []
    for d in sorted(diffs, key=lambda d: (-d.new.score, d.ticker)):
        r     = d.new
        fund  = funds_with_prices.get(r.ticker, {})
        p2n   = fund.get("price_to_nav")
        p2n_s = f"{p2n:.3f}x" if p2n is not None else "—"
        na_s  = f"{r.na_rate:.1%}" if r.na_rate is not None else "—"
        flags = ", ".join(r.flags[:3]) + (" …" if len(r.flags) > 3 else "")
        tier_c = _TIER_COLOR.get(r.tier, "#6b7280")
        score_style = f'font-weight:700;color:{tier_c};'
        table_rows.append(
            f"<tr>"
            f"<td style='font-weight:600'>{r.ticker}</td>"
            f"<td style='{score_style}text-align:right'>{r.score}</td>"
            f"<td>{_tier_badge(r.tier)}</td>"
            f"<td style='text-align:right;color:#374151'>{p2n_s}</td>"
            f"<td style='text-align:right;color:#374151'>{na_s}</td>"
            f"<td style='color:#6b7280;font-size:12px'>{flags}</td>"
            f"</tr>"
        )
    sections.append(
        '<h2>Full Scorecard</h2>'
        '<table>'
        '<thead><tr>'
        '<th>Ticker</th><th style="text-align:right">Score</th><th>Tier</th>'
        '<th style="text-align:right">P/NAV</th><th style="text-align:right">NA Rate</th>'
        '<th>Key Flags</th>'
        '</tr></thead>'
        '<tbody>' + "".join(table_rows) + '</tbody>'
        '</table>'
    )

    sections.append(
        '<div class="footer">Private Credit Workbench &bull; automated refresh</div>'
    )

    html = f"<!DOCTYPE html><html><head><meta charset='utf-8'>{css}</head><body>"
    html += "\n".join(sections)
    html += "</body></html>"

    # ── Plain-text fallback ───────────────────────────────────────────────
    plain_lines: list[str] = [
        f"BDC Surveillance Digest — {run_dt}",
        f"{len(diffs)} funds  |  {len(downgraded)} downgrades  |  {len(upgraded)} upgrades  |  {len(score_only)} score moves",
        "",
    ]
    if downgraded:
        plain_lines.append("DOWNGRADES")
        for d in downgraded:
            plain_lines.append(f"  {d.ticker}  {d.old.tier} -> {d.new.tier}  ({d.old.score} -> {d.new.score})")
        plain_lines.append("")
    if upgraded:
        plain_lines.append("UPGRADES")
        for d in upgraded:
            plain_lines.append(f"  {d.ticker}  {d.old.tier} -> {d.new.tier}  ({d.old.score} -> {d.new.score})")
        plain_lines.append("")
    if score_only:
        plain_lines.append("SCORE MOVES")
        for d in score_only:
            plain_lines.append(f"  {d.ticker}  {d.new.tier}  {d.old.score} -> {d.new.score} ({d.score_delta:+d})")
        plain_lines.append("")
    plain_lines.append("FULL SCORECARD")
    plain_lines.append(f"{'Ticker':<8} {'Score':>5}  {'Tier':<8}  {'P/NAV':>7}  {'NA%':>6}  Flags")
    plain_lines.append("-" * 72)
    for d in sorted(diffs, key=lambda d: (-d.new.score, d.ticker)):
        r     = d.new
        fund  = funds_with_prices.get(r.ticker, {})
        p2n   = fund.get("price_to_nav")
        p2n_s = f"{p2n:.3f}x" if p2n is not None else "n/a"
        na_s  = f"{r.na_rate:.1%}" if r.na_rate is not None else "n/a"
        flags = ", ".join(r.flags[:3])
        plain_lines.append(f"{r.ticker:<8} {r.score:>5}  {r.tier:<8}  {p2n_s:>7}  {na_s:>6}  {flags}")

    return html, "\n".join(plain_lines)


# ---------------------------------------------------------------------------
# Email (optional)
# ---------------------------------------------------------------------------

def send_email(subject: str, html: str, plain: str, to_addr: str) -> bool:
    """Send HTML digest via SMTP. Reads config from environment / .env file."""
    # Load .env if present
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    host  = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port  = int(os.environ.get("SMTP_PORT", "587"))
    user  = os.environ.get("SMTP_USER", "")
    pw    = os.environ.get("SMTP_PASS", "")
    from_ = os.environ.get("SMTP_FROM", user)

    if not user or not pw:
        print("[email] SMTP_USER / SMTP_PASS not set in .env — skipping email.")
        return False

    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_
        msg["To"]      = to_addr
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html,  "html"))   # html last = preferred by clients

        if port == 465:
            with smtplib.SMTP_SSL(host, port) as smtp:
                smtp.login(user, pw)
                smtp.sendmail(from_, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(host, port) as smtp:
                smtp.starttls()
                smtp.login(user, pw)
                smtp.sendmail(from_, [to_addr], msg.as_string())

        print(f"[email] Digest sent to {to_addr}")
        return True
    except Exception as exc:
        print(f"[email] Failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(
    force:      bool = False,
    score_only: bool = False,
    notify:     Optional[str] = None,
    dry_run:    bool = False,
    verbose:    bool = True,
) -> list[ScoreDiff]:
    run_dt = datetime.now().strftime("%Y-%m-%d %H:%M")

    from red_flag_screener import load_universe
    funds = load_universe()

    new_filings: dict[str, str] = {}

    # ── Step 1: Detect new filings ──────────────────────────────────────────
    if not score_only:
        if force:
            listed = [f["ticker"] for f in funds if f.get("type") == "listed_bdc"]
            new_filings = {t: "forced" for t in listed}
            if verbose:
                print(f"Force mode: refreshing all {len(listed)} listed BDCs")
        else:
            new_filings = check_new_filings(funds, verbose=verbose, dry_run=dry_run)

    # ── Step 2: Pull new SOI data ───────────────────────────────────────────
    tickers_to_refresh = [t for t in new_filings if new_filings[t] != "forced" or force]
    if tickers_to_refresh and not dry_run:
        run_collection(tickers_to_refresh, verbose=verbose)
    elif tickers_to_refresh and dry_run:
        print(f"[dry-run] Would collect: {', '.join(tickers_to_refresh)}")

    # ── Step 3: Score all funds ─────────────────────────────────────────────
    if verbose:
        print("\nScoring all funds...")
    current_scores = score_all_funds(verbose=False)

    # ── Step 4: Diff vs history ─────────────────────────────────────────────
    history = load_score_history()
    diffs   = compute_diffs(history, current_scores)

    # ── Step 5: Format digest ───────────────────────────────────────────────
    html_digest, plain_digest = format_digest(diffs, new_filings, run_dt)

    # ── Step 6: Print summary ───────────────────────────────────────────────
    changed = [d for d in diffs if d.score_delta != 0 or d.tier_changed or d.new_flags or d.cleared_flags]
    print(f"\n{'='*60}")
    print(f"  BDC Refresh  {run_dt}")
    print(f"  New filings: {len(new_filings)}  |  Score changes: {len(changed)}")
    print(f"{'='*60}")

    tier_changes = [d for d in diffs if d.tier_changed]
    if tier_changes:
        print("\nTier changes:")
        for d in tier_changes:
            arrow = "v" if d.tier_direction == "downgraded" else "^"
            print(f"  {arrow} {d.ticker:<8} {d.old.tier} -> {d.new.tier}  ({d.score_delta:+d} pts)")
    elif changed:
        print("\nScore changes (same tier):")
        for d in changed[:8]:
            print(f"  {d.ticker:<8} {d.old.score} -> {d.new.score} ({d.score_delta:+d})")
    else:
        print("\n  No score changes since last run.")

    # ── Step 7: Persist ─────────────────────────────────────────────────────
    if not dry_run:
        save_score_history(current_scores)
        DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        DIGEST_PATH.write_text(html_digest, encoding="utf-8")
        if verbose:
            print(f"\nDigest written to {DIGEST_PATH}")

    # ── Step 8: Email ──────────────────────────────────────────────────────
    if notify and not dry_run:
        n_changes = len(changed)
        n_tier    = len(tier_changes)
        subject   = (
            f"BDC Alert: {n_tier} tier change{'s' if n_tier!=1 else ''} — {run_dt}"
            if tier_changes else
            f"BDC Digest: {n_changes} change{'s' if n_changes!=1 else ''} — {run_dt}"
        )
        send_email(subject, html_digest, plain_digest, notify)

    return diffs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="BDC weekly refresh and score diff.")
    parser.add_argument("--force",      action="store_true", help="Re-parse all funds, ignoring cache.")
    parser.add_argument("--score-only", action="store_true", help="Skip filing check; just re-score.")
    parser.add_argument("--notify",     metavar="EMAIL",     help="Send digest to this email address.")
    parser.add_argument("--dry-run",    action="store_true", help="Show changes without writing anything.")
    parser.add_argument("--quiet",      action="store_true", help="Minimal output.")
    args = parser.parse_args()

    run(
        force      = args.force,
        score_only = args.score_only,
        notify     = args.notify,
        dry_run    = args.dry_run,
        verbose    = not args.quiet,
    )


if __name__ == "__main__":
    main()
