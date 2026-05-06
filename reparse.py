#!/usr/bin/env python3
"""
BCC ePetitions Re-Parser v3
============================
Handles two page formats:

Format A (older, ~PID 75-200):
    "HomeAbout CouncilContact CouncilPetitions[TITLE]Principal Petitioner..."
    — all concatenated on one line

Format B (newer, ~PID 200+):
    "Petitions | Brisbane City Council
     Skip to main content
     Home
     About Council
     Contact Council
     Petitions
     [TITLE]
     Principal Petitioner
     ..."
    — split across lines

Usage:
    python reparse.py                  # reads petitions.json -> petitions_parsed.json
    python reparse.py --show 10        # print 10 parsed records for inspection
"""

import json, re, argparse

INPUT_FILE  = "petitions.json"
OUTPUT_FILE = "petitions_parsed.json"

# Format A nav header (concatenated)
NAV_HEADER_A = "HomeAbout CouncilContact CouncilPetitions"

# Format B nav header lines to strip
NAV_HEADER_B_RE = re.compile(
    r'^(Petitions \| Brisbane City Council\n?)?'
    r'(Skip to main content\n?)?'
    r'(Home\n?)?'
    r'(About Council\n?)?'
    r'(Contact Council\n?)?'
    r'(Petitions\n?)?',
    re.MULTILINE
)

NAV_FOOTER_SIGNALS = [
    "PetitionsCurrent ePetitions",
    "Current ePetitionsSubmit a new petition",
    "Petitions\nCurrent ePetitions",
    "Want to know what's happening around Brisbane",
    "Keep me in the loop",
]

DISCLAIMER = "Petitions express the views of the Head Petitioner and may not represent the views of Council."

SKIP_RE = re.compile(
    r"^(Principal Petitioner|Date Closed|No\. of signatures|"
    r"This epetition has ended|\(View signatures\)|"
    r"Petitions express the views of the Head Petitioner)",
    re.IGNORECASE
)


def strip_nav(text):
    if not text:
        return ""

    # Format A: concatenated header
    if text.startswith(NAV_HEADER_A):
        text = text[len(NAV_HEADER_A):].lstrip()
    else:
        # Format B: split lines — strip opening nav block
        text = NAV_HEADER_B_RE.sub("", text.lstrip(), count=1).lstrip("\n")

    # Strip footer
    for signal in NAV_FOOTER_SIGNALS:
        idx = text.find(signal)
        if idx != -1:
            text = text[:idx].rstrip()
            break

    return text.strip()


def reparse(record):
    pid = record["pid"]

    # Prefer council_response (old scraper fallback field) but also
    # try reconstructing from the raw body field for Format B pages
    raw = record.get("council_response") or ""

    # For Format B pages the old scraper put nothing useful in council_response
    # but the page text was sometimes partially captured in body
    if not raw or raw.strip() in ("Skip to main content", ""):
        raw = record.get("body") or ""

    content = strip_nav(raw)

    out = {
        "pid":              pid,
        "url":              record["url"],
        "title":            None,
        "status":           record.get("status"),
        "petitioner":       None,
        "suburb":           None,
        "close_date":       None,
        "signatures":       None,
        "petition_body":    None,
        "council_response": None,
        "scraped_at":       record.get("scraped_at"),
        "_parse_status":    "empty",
        "_format":          None,
    }

    if not content or content.lower().startswith("current epetitions"):
        return out

    # ----------------------------------------------------------------
    # Detect format
    # Format A: "Principal Petitioner" appears inline (no preceding newline)
    # Format B: fields are on separate lines
    # ----------------------------------------------------------------
    if "\nPrincipal Petitioner\n" in content:
        return _parse_format_b(content, out)
    elif "Principal Petitioner" in content:
        return _parse_format_a(content, out)
    else:
        # No petitioner marker — try to get at least a title
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if lines:
            out["title"] = lines[0][:200]
            out["_parse_status"] = "partial"
        return out


def _parse_format_a(content, out):
    """
    Format A: metadata concatenated without newlines.
    'TITLEPrincipal PetitionerNAME, SUBURBDate ClosedDATE...'
    """
    out["_format"] = "A"

    # Title: everything before "Principal Petitioner"
    pp_idx = content.find("Principal Petitioner")
    if pp_idx > 0:
        out["title"] = content[:pp_idx].strip()[:200]
        after_pp = content[pp_idx + len("Principal Petitioner"):]
    else:
        after_pp = content

    # Petitioner + suburb: up to "Date Closed"
    dc_idx = after_pp.find("Date Closed")
    if dc_idx > 0:
        petitioner_raw = after_pp[:dc_idx].strip()
        if "," in petitioner_raw:
            parts = petitioner_raw.rsplit(",", 1)
            out["petitioner"] = parts[0].strip()
            out["suburb"]     = parts[1].strip()
        else:
            out["petitioner"] = petitioner_raw
        after_dc = after_pp[dc_idx + len("Date Closed"):]
    else:
        after_dc = after_pp

    # Close date
    m = re.match(r"\s*(\w+,\s+\d+\s+\w+\s+\d{4})", after_dc)
    if m:
        out["close_date"] = m.group(1).strip()
        out["status"]     = "closed"

    # Signatures
    m = re.search(r"(\d[\d,]*)\s+signatures?", content, re.IGNORECASE)
    if m:
        out["signatures"] = int(m.group(1).replace(",", ""))

    # Body: after disclaimer, before council response
    disc_idx = content.find(DISCLAIMER)
    if disc_idx != -1:
        body_start = content[disc_idx + len(DISCLAIMER):]
    else:
        body_start = after_dc

    cr_match = re.search(r"\nCouncil response\n|Council response\n", body_start)
    if cr_match:
        petition_body        = body_start[:cr_match.start()].strip()
        out["council_response"] = body_start[cr_match.end():].strip()
    else:
        petition_body = body_start.strip()

    petition_body = re.sub(
        r"(This epetition has ended|\(View signatures\)|"
        r"No\. of signatures\s*\d[\d,]*\s*signatures?)",
        "", petition_body, flags=re.IGNORECASE
    ).strip()

    if petition_body:
        out["petition_body"] = petition_body
        out["_parse_status"] = "ok"
    elif out["title"] or out["signatures"] is not None:
        out["_parse_status"] = "partial"

    return out


def _parse_format_b(content, out):
    """
    Format B: fields on separate lines.
    Line 0: TITLE
    Line 1: 'Principal Petitioner'
    Line 2: NAME, SUBURB  (or split across two lines)
    Line 3: 'Date Closed'
    Line 4: DATE
    ...
    """
    out["_format"] = "B"

    lines = [l.strip() for l in content.split("\n") if l.strip()]

    # Find Principal Petitioner line index
    pp_line = next((i for i, l in enumerate(lines)
                    if l == "Principal Petitioner"), None)

    if pp_line is None:
        # Fallback to Format A logic
        return _parse_format_a(content, out)

    # Title: everything before Principal Petitioner line
    title_lines = lines[:pp_line]
    if title_lines:
        out["title"] = " ".join(title_lines)[:200]

    # Petitioner: line after "Principal Petitioner"
    if pp_line + 1 < len(lines):
        petitioner_raw = lines[pp_line + 1]
        if "," in petitioner_raw:
            parts = petitioner_raw.rsplit(",", 1)
            out["petitioner"] = parts[0].strip()
            out["suburb"]     = parts[1].strip()
        else:
            out["petitioner"] = petitioner_raw

    # Find Date Closed line
    dc_line = next((i for i, l in enumerate(lines)
                    if l == "Date Closed"), None)
    if dc_line is not None and dc_line + 1 < len(lines):
        out["close_date"] = lines[dc_line + 1].strip()
        out["status"]     = "closed"

    # Signatures
    m = re.search(r"(\d[\d,]*)\s+signatures?", content, re.IGNORECASE)
    if m:
        out["signatures"] = int(m.group(1).replace(",", ""))

    # Body: after disclaimer
    disc_idx = content.find(DISCLAIMER)
    if disc_idx != -1:
        body_raw = content[disc_idx + len(DISCLAIMER):]
    else:
        # Fall back to after the signatures line
        sig_m = re.search(r"\d[\d,]*\s+signatures?\s*(\(View signatures\))?",
                          content, re.IGNORECASE)
        body_raw = content[sig_m.end():] if sig_m else content

    # Split off council response
    cr_match = re.search(r"\nCouncil response\n|^Council response$",
                         body_raw, re.MULTILINE)
    if cr_match:
        petition_body           = body_raw[:cr_match.start()].strip()
        out["council_response"] = body_raw[cr_match.end():].strip()
    else:
        petition_body = body_raw.strip()

    # Clean body lines
    body_lines = [l.strip() for l in petition_body.split("\n")
                  if l.strip() and not SKIP_RE.match(l.strip())]
    petition_body = " ".join(body_lines).strip()

    if petition_body:
        out["petition_body"] = petition_body
        out["_parse_status"] = "ok"
    elif out["title"] or out["signatures"] is not None:
        out["_parse_status"] = "partial"

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default=INPUT_FILE)
    ap.add_argument("--output", default=OUTPUT_FILE)
    ap.add_argument("--show",   type=int, default=0)
    args = ap.parse_args()

    print(f"Loading {args.input}...")
    with open(args.input) as f:
        data = json.load(f)
    print(f"  {len(data)} records")

    parsed = [reparse(r) for r in data]

    from collections import Counter
    statuses = Counter(p["_parse_status"] for p in parsed)
    formats  = Counter(p.get("_format") for p in parsed if p.get("_format"))

    print(f"\nParse results:")
    for s, n in sorted(statuses.items()):
        print(f"  {s:10s}: {n}")
    print(f"\nFormat breakdown:")
    for f, n in sorted(formats.items()):
        print(f"  Format {f}: {n}")

    fields = ["title", "petition_body", "signatures", "council_response", "petitioner", "suburb", "close_date"]
    print(f"\nField coverage ({len(parsed)} records):")
    for f in fields:
        n = sum(1 for p in parsed if p.get(f))
        print(f"  {f:20s}: {n}")

    if args.show:
        print(f"\n--- {args.show} records with status=ok ---")
        shown = 0
        for p in parsed:
            if p["_parse_status"] != "ok":
                continue
            print(f"\nPID {p['pid']} [Format {p.get('_format')}]")
            print(f"  Title:      {p.get('title')}")
            print(f"  Petitioner: {p.get('petitioner')}, {p.get('suburb')}")
            print(f"  Close:      {p.get('close_date')}  |  Sigs: {p.get('signatures')}")
            body = p.get("petition_body") or ""
            print(f"  Body:       {body[:200]}{'...' if len(body) > 200 else ''}")
            shown += 1
            if shown >= args.show:
                break

    with open(args.output, "w") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"\nWritten to {args.output}")


if __name__ == "__main__":
    main()
