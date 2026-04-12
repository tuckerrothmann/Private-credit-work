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


def _get_latest_10kq_period(cik: str) -> Optional[str]:
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
        edgar_period  = _get_latest_10kq_period(cik)
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
    """Re-score all funds with live NA enrichment and return ScoreRecord dict."""
    from red_flag_screener import load_universe, score_fund, enrich_funds_with_live_na
    from price_feed import enrich_funds_with_prices

    funds = enrich_funds_with_prices(enrich_funds_with_live_na(load_universe()))
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

_TIER_EMOJI = {"RED": "🔴", "ORANGE": "🟠", "YELLOW": "🟡", "GREEN": "🟢"}
# ASCII fallbacks for email/plain environments
_TIER_ASCII = {"RED": "[RED]", "ORANGE": "[ORA]", "YELLOW": "[YEL]", "GREEN": "[GRN]"}


def format_digest(
    diffs:        list[ScoreDiff],
    new_filings:  dict[str, str],
    run_dt:       str,
    use_emoji:    bool = True,
) -> str:
    tier_tag = _TIER_EMOJI if use_emoji else _TIER_ASCII

    changed  = [d for d in diffs if d.score_delta != 0 or d.tier_changed or d.new_flags or d.cleared_flags]
    same     = [d for d in diffs if d not in changed]
    downgraded = [d for d in changed if d.tier_direction == "downgraded"]
    upgraded   = [d for d in changed if d.tier_direction == "upgraded"]
    score_only = [d for d in changed if not d.tier_changed]

    lines: list[str] = []
    lines.append(f"# BDC Weekly Refresh Digest — {run_dt}")
    lines.append("")
    lines.append(
        f"**{len(new_filings)} new filings**  |  "
        f"**{len(changed)} score changes**  |  "
        f"**{len(downgraded)} tier downgrades**  |  "
        f"**{len(upgraded)} tier upgrades**"
    )
    lines.append("")

    # ── Tier changes ──────────────────────────────────────────────────────
    if downgraded:
        lines.append("## Downgrades (watch closely)")
        for d in downgraded:
            tag = f"{tier_tag[d.old.tier]} → {tier_tag[d.new.tier]}"
            delta = f"{d.score_delta:+d} pts" if d.score_delta else "tier only"
            lines.append(f"- **{d.ticker}** {tag}  score {d.old.score} → {d.new.score} ({delta})")
            if d.new_flags:
                lines.append(f"  - New flags: {', '.join(d.new_flags)}")
            if d.cleared_flags:
                lines.append(f"  - Cleared: {', '.join(d.cleared_flags)}")
        lines.append("")

    if upgraded:
        lines.append("## Upgrades (improvement)")
        for d in upgraded:
            tag = f"{tier_tag[d.old.tier]} → {tier_tag[d.new.tier]}"
            delta = f"{d.score_delta:+d} pts" if d.score_delta else "tier only"
            lines.append(f"- **{d.ticker}** {tag}  score {d.old.score} → {d.new.score} ({delta})")
            if d.cleared_flags:
                lines.append(f"  - Cleared: {', '.join(d.cleared_flags)}")
            if d.new_flags:
                lines.append(f"  - New flags: {', '.join(d.new_flags)}")
        lines.append("")

    # ── Score-only changes ─────────────────────────────────────────────────
    if score_only:
        lines.append("## Score changes (same tier)")
        for d in score_only:
            delta_s = f"{d.score_delta:+d}"
            lines.append(f"- **{d.ticker}** {tier_tag[d.new.tier]}  {d.old.score} → {d.new.score} ({delta_s})")
            if d.new_flags:
                lines.append(f"  - New: {', '.join(d.new_flags)}")
            if d.cleared_flags:
                lines.append(f"  - Cleared: {', '.join(d.cleared_flags)}")
        lines.append("")

    # ── New filings ────────────────────────────────────────────────────────
    if new_filings:
        lines.append("## New filings pulled")
        for ticker, period in sorted(new_filings.items()):
            lines.append(f"- **{ticker}** — {period}")
        lines.append("")

    # ── No change ─────────────────────────────────────────────────────────
    if same:
        same_tickers = ", ".join(d.ticker for d in same)
        lines.append(f"## No change ({len(same)} funds)")
        lines.append(same_tickers)
        lines.append("")

    # ── Full scorecard ─────────────────────────────────────────────────────
    lines.append("## Full scorecard")
    lines.append("")
    lines.append("| Ticker | Score | Tier | P/NAV | NA Rate | Key Flags |")
    lines.append("|--------|------:|------|------:|--------:|-----------|")
    from price_feed import enrich_funds_with_prices
    from red_flag_screener import load_universe
    funds_with_prices = {
        f["ticker"]: f
        for f in enrich_funds_with_prices(load_universe())
    }
    for d in sorted(diffs, key=lambda d: (-d.new.score, d.ticker)):
        r    = d.new
        fund = funds_with_prices.get(r.ticker, {})
        p2n  = fund.get("price_to_nav")
        p2n_s = f"{p2n:.3f}x" if p2n is not None else "n/a"
        na_s  = f"{r.na_rate:.1%}" if r.na_rate is not None else "n/a"
        flags = ", ".join(r.flags[:3]) + (" ..." if len(r.flags) > 3 else "")
        lines.append(f"| {r.ticker:<6} | {r.score:>5} | {tier_tag[r.tier]} | {p2n_s:>7} | {na_s:>7} | {flags} |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Email (optional)
# ---------------------------------------------------------------------------

def send_email(subject: str, body: str, to_addr: str) -> bool:
    """Send digest via SMTP. Reads config from environment / .env file."""
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
        from email.mime.text import MIMEText

        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"]    = from_
        msg["To"]      = to_addr

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
            new_filings = check_new_filings(funds, verbose=verbose)

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
    digest = format_digest(diffs, new_filings, run_dt, use_emoji=False)

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
        DIGEST_PATH.write_text(digest, encoding="utf-8")
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
        send_email(subject, digest, notify)

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
