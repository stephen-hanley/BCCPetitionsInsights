#!/usr/bin/env python3
"""
Brisbane City Council ePetitions Scraper (v4 - element-based parser)
=====================================================================
Usage:
    python scraper.py                          # Full scrape
    python scraper.py --max-pid 1600           # Explicit PID ceiling
    python scraper.py --resume                 # Skip already-ok PIDs
    python scraper.py --resume --refetch-partial  # Re-fetch partial/empty
    python scraper.py --delay 1.0              # Seconds between requests
"""

import requests
from bs4 import BeautifulSoup
import json, time, argparse, os, re
from datetime import datetime
from pathlib import Path

BASE_URL    = "https://epetitions.brisbane.qld.gov.au"
OUTPUT_FILE = "petitions.json"
LOG_FILE    = "scraper.log"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; civic-research-scraper/1.0; active-transport-research; contact@example.com)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-AU,en;q=0.9",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

DISCLAIMER = "Petitions express the views of the Head Petitioner and may not represent the views of Council."

NAV_FOOTER_SIGNALS = [
    "PetitionsCurrent ePetitions",
    "Petitions\nCurrent ePetitions",
    "Want to know what's happening around Brisbane",
    "Keep me in the loop",
]


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def fetch(url, retries=3, delay=1.0):
    for attempt in range(retries):
        try:
            time.sleep(delay)
            resp = SESSION.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 404:
                return None
            else:
                log(f"  HTTP {resp.status_code} for {url} (attempt {attempt+1})")
        except requests.RequestException as e:
            log(f"  Request error: {e} (attempt {attempt+1})")
        time.sleep(delay * 2)
    return None


def parse_petition_page(html, pid):
    """
    Parse by extracting non-empty text elements, then locating
    'Principal Petitioner' as an anchor to find title, petitioner,
    date, signatures, and body relative to it.

    Page element sequence (after stripping empties):
        ...nav garbage...
        [TITLE]
        'Principal Petitioner'
        [NAME, SUBURB]
        'Date Closed'
        [DATE]
        'This epetition has ended'
        [N] + 'signatures'
        '(View signatures)'
        DISCLAIMER
        [BODY TEXT lines]
        'Council response'       <- optional
        [RESPONSE lines]
        nav footer garbage...
    """
    soup = BeautifulSoup(html, "html.parser")

    out = {
        "pid":              pid,
        "url":              f"{BASE_URL}/petition/view/pid/{pid}",
        "title":            None,
        "status":           None,
        "petitioner":       None,
        "suburb":           None,
        "close_date":       None,
        "signatures":       None,
        "petition_body":    None,
        "council_response": None,
        "scraped_at":       datetime.now().isoformat(),
        "_parse_status":    "empty",
    }

    # Extract all non-empty text tokens from the page
    tokens = [t.strip() for t in soup.get_text(separator="\n").splitlines() if t.strip()]

    # Find 'Principal Petitioner' token — this is our anchor
    try:
        pp_idx = tokens.index("Principal Petitioner")
    except ValueError:
        # No petition content — empty/redirect page
        # Still try to get signatures in case partial data exists
        m = re.search(r"(\d[\d,]*)\s+signatures?", "\n".join(tokens), re.I)
        if m:
            out["signatures"]    = int(m.group(1).replace(",", ""))
            out["_parse_status"] = "partial"
        return out

    # Title: the token immediately before 'Principal Petitioner'
    if pp_idx > 0:
        out["title"] = tokens[pp_idx - 1][:200]

    # Petitioner + suburb: token after 'Principal Petitioner'
    if pp_idx + 1 < len(tokens):
        petitioner_raw = tokens[pp_idx + 1]
        if "," in petitioner_raw:
            parts = petitioner_raw.rsplit(",", 1)
            out["petitioner"] = parts[0].strip()
            out["suburb"]     = parts[1].strip()
        else:
            out["petitioner"] = petitioner_raw

    # Scan forward from pp_idx for date, signatures, body
    i = pp_idx + 2
    while i < len(tokens):
        t = tokens[i]

        if t == "Date Closed" and i + 1 < len(tokens):
            raw_date = tokens[i + 1]
            # Date may have trailing whitespace/tab garbage — clean it
            m = re.match(r"(\w+,\s+\d+\s+\w+\s+\d{4})", raw_date)
            if m:
                out["close_date"] = m.group(1)
                out["status"]     = "closed"
            i += 2
            continue

        if re.match(r"^\d[\d,]*$", t) and i + 1 < len(tokens) and "signature" in tokens[i+1].lower():
            out["signatures"] = int(t.replace(",", ""))
            i += 2
            continue

        if "signature" in t.lower() and re.search(r"\d", t):
            m = re.search(r"(\d[\d,]*)", t)
            if m:
                out["signatures"] = int(m.group(1).replace(",", ""))
            i += 1
            continue

        if DISCLAIMER in t or t == DISCLAIMER[:50]:
            # Everything after disclaimer (up to nav footer) is body + response
            body_tokens = []
            i += 1
            while i < len(tokens):
                t2 = tokens[i]
                # Stop at nav footer
                if any(sig in t2 for sig in ["Current ePetitions", "Keep me in the loop",
                                              "Want to know what's happening"]):
                    break
                body_tokens.append(t2)
                i += 1

            # Split body from council response
            try:
                cr_idx = body_tokens.index("Council response")
                petition_body    = " ".join(body_tokens[:cr_idx]).strip()
                out["council_response"] = " ".join(body_tokens[cr_idx+1:]).strip()
            except ValueError:
                petition_body = " ".join(body_tokens).strip()

            if petition_body:
                out["petition_body"] = petition_body

            break

        i += 1

    # Set final parse status
    if out["petition_body"] and out["title"]:
        out["_parse_status"] = "ok"
    elif out["title"] or out["signatures"] is not None:
        out["_parse_status"] = "partial"

    return out


def get_listing_pids(url, delay=1.0):
    pids = set()
    page = 1
    while True:
        page_url = f"{url}?page={page}" if page > 1 else url
        html = fetch(page_url, delay=delay)
        if not html:
            break
        soup  = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", href=re.compile(r"/petition/view/pid/(\d+)"))
        if not links:
            break
        for link in links:
            m = re.search(r"/petition/view/pid/(\d+)", link["href"])
            if m:
                pids.add(int(m.group(1)))
        if not soup.find("a", string=re.compile(r"next", re.I)):
            break
        page += 1
    return pids


def _save(results_dict):
    data = sorted(results_dict.values(), key=lambda x: x["pid"])
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def scrape_all(max_pid=None, delay=1.5, resume=False, refetch_partial=False):
    existing = {}
    if resume and os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f:
            existing = {p["pid"]: p for p in json.load(f)}
        log(f"Resuming: {len(existing)} records loaded")

    log("Fetching current petitions listing...")
    known = get_listing_pids(f"{BASE_URL}/", delay)
    log("Fetching archive listing...")
    known |= get_listing_pids(f"{BASE_URL}/petition/archive", delay)
    log(f"Known PIDs from listings: {len(known)}")

    if max_pid is None:
        max_pid = max(known) + 50 if known else 1600

    all_pids = sorted(known | set(range(1, max_pid + 1)))

    skip = set()
    for pid, rec in existing.items():
        status = rec.get("_parse_status", "")
        if status == "ok":
            skip.add(pid)
        elif not refetch_partial:
            skip.add(pid)

    to_fetch = [p for p in all_pids if p not in skip]
    log(f"PIDs to fetch: {len(to_fetch)} (skipping {len(skip)})")

    results = dict(existing)
    found   = 0
    consecutive_miss = 0

    for i, pid in enumerate(to_fetch):
        html = fetch(f"{BASE_URL}/petition/view/pid/{pid}", delay=delay)

        if html is None:
            consecutive_miss += 1
            if pid > max(known or [0]) and consecutive_miss > 50:
                log(f"50+ consecutive 404s, stopping at PID {pid}")
                break
            continue

        consecutive_miss = 0
        p = parse_petition_page(html, pid)
        results[pid] = p
        found += 1

        log(f"  [{i+1}/{len(to_fetch)}] PID {pid:5d} "
            f"[{p['_parse_status']:7s}] "
            f"sigs={str(p.get('signatures')):>6} | "
            f"{(p.get('title') or '(no title)')[:60]}")

        if found % 20 == 0:
            _save(results)

    _save(results)

    from collections import Counter
    statuses = Counter(r.get("_parse_status", "?") for r in results.values())
    log(f"\nDone. {len(results)} total records.")
    for s, n in sorted(statuses.items()):
        log(f"  {s:10s}: {n}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BCC ePetitions Scraper v4")
    parser.add_argument("--max-pid",         type=int,   default=None)
    parser.add_argument("--delay",           type=float, default=1.5)
    parser.add_argument("--resume",          action="store_true")
    parser.add_argument("--refetch-partial", action="store_true")
    args = parser.parse_args()
    Path(LOG_FILE).write_text("")
    scrape_all(
        max_pid=args.max_pid,
        delay=args.delay,
        resume=args.resume,
        refetch_partial=args.refetch_partial,
    )
