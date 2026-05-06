#!/usr/bin/env python3
"""
BCC ePetitions Thematic Tagger
================================
Reads petitions_parsed.json, applies multi-label theme tagging, and writes
themes.csv for analysis in Excel or upload here for further analysis.

Usage:
    python themes.py                         # tag all, write themes.csv
    python themes.py --show cycling          # print matching petitions for a theme
    python themes.py --show traffic_calming
    python themes.py --summary               # theme counts only, no CSV
    python themes.py --input petitions_parsed.json --output my_themes.csv
"""

import json, re, csv, argparse

INPUT_FILE  = "petitions_parsed.json"
OUTPUT_FILE = "themes.csv"

# ---------------------------------------------------------------------------
# Theme dictionary
# Plain strings — matched case-insensitively anywhere in title + body.
# A petition can match multiple themes.
# ---------------------------------------------------------------------------

THEMES = {

    # Active transport
    "cycling": [
        "cycl", "cyclist", "bicycle", "bikeway", "bike lane", "bike path",
        "bike way", "cycle path", "cycle lane", "cycle track", "veloway",
        "cargo bike", "e-bike", "ebike", "shared path", "shared trail",
        "bikedge", "bikeways",
    ],
    "pedestrian": [
        "pedestrian", "footpath", "foot path", "footway", "walkway",
        "walking", "walker", "footbridge", "walk to school",
        "pedestrian access", "pedestrian safety", "pedestrian network",
    ],
    "traffic_calming": [
        "traffic calm", "speed hump", "speed bump", "speed cushion",
        "chicane", "slow point", "slow zone", "raised intersection",
        "raised crossing", "traffic island", "LATM",
        "local area traffic management", "traffic management plan",
        "traffic device", "traffic measure",
        "road closure", "close to through traffic", "through traffic",
        "traffic treatment", "traffic precinct",
    ],
    "speed_limit": [
        "speed limit", "speed zone", "speed reduc", "lower the speed",
        "reduce speed", "40km", "40 km", "40kmh", "40km/h",
        "school zone", "hospital zone",
        "speeding", "excessive speed", "speed camera",
        "speed warning", "portable speed", "speed sign",
    ],
    "pedestrian_crossing": [
        "pedestrian crossing", "zebra crossing",
        "traffic light", "traffic signal", "pelican crossing",
        "pedestrian signal", "pedestrian light",
        "refuge island", "median refuge", "crossing point",
        "safe crossing", "children crossing", "school crossing",
        "crossing guard", "lollipop",
    ],
    "road_safety": [
        "road safety", "safe road", "dangerous road", "dangerous intersection",
        "dangerous crossing", "accident", "collision", "near miss",
        "fatality", "serious injury", "safety concern",
        "safety issue", "hazard", "sight line", "sightline",
        "duty of care", "safety of children", "safety for pedestrian",
        "road trauma",
    ],
    "active_transport_general": [
        "active transport", "active travel", "sustainable transport",
        "walking and cycling", "cycling and walking",
        "non-motorised", "green transport", "car-free", "car free",
    ],

    # Roads and vehicles
    "parking": [
        "parking", "car park", "carpark", "no parking", "parking meter",
        "parking restriction", "parking permit", "resident parking",
        "parking problem", "parking issue", "parking shortage",
        "disabled parking", "accessible parking",
    ],
    "traffic_congestion": [
        "traffic congestion", "traffic volume", "traffic flow",
        "heavy traffic", "congestion", "gridlock", "rat run",
        "cut-through", "cut through traffic", "traffic increase",
        "traffic management",
    ],
    "road_upgrade": [
        "road upgrade", "road widening", "road extension", "road improvement",
        "road work", "roadwork", "carriageway", "lane addition",
        "intersection upgrade", "intersection improvement", "road seal",
        "road resurface", "pothole",
    ],

    # Public transport
    "public_transport": [
        "bus route", "bus stop", "bus service", "bus shelter",
        "train station", "train service", "railway", "rail crossing",
        "ferry", "ferry terminal", "translink", "public transport",
        "transit", "CityCat", "CityFerry", "busway",
    ],

    # Green space and environment
    "parks_green_space": [
        "park", "parkland", "open space", "green space", "reserve",
        "recreation area", "playground", "oval", "sporting field",
        "nature strip", "urban forest", "conservation",
    ],
    "trees_vegetation": [
        "tree removal", "remove tree", "tree protection", "tree canopy",
        "vegetation", "koala", "wildlife corridor", "habitat",
        "native plant", "native vegetation",
    ],
    "flooding_drainage": [
        "flood", "flooding", "drainage", "stormwater", "overland flow",
        "inundation", "waterway", "creek", "drain",
    ],

    # Development and planning
    "development_planning": [
        "development application", "development approval",
        "planning scheme", "rezoning", "re-zoning", "zoning",
        "height limit", "building height", "setback",
        "heritage", "character housing", "demolition",
        "density", "infill", "neighbourhood plan",
    ],

    # Community facilities
    "community_facilities": [
        "community centre", "community hall", "community facility",
        "library", "swimming pool", "aquatic centre",
        "sporting club", "bowls club", "tennis court", "community hub",
    ],

    # Animals
    "dogs_animals": [
        "dog off-leash", "off leash", "dog park", "dog owner",
        "animal management", "koala", "wildlife",
    ],

    # Noise and amenity
    "noise_amenity": [
        "noise", "nuisance", "amenity", "light pollution",
        "odour", "vibration", "construction noise", "noise pollution",
    ],
}

# For the summary printout
ACTIVE_TRANSPORT_THEMES = [
    "cycling", "pedestrian", "traffic_calming", "speed_limit",
    "pedestrian_crossing", "road_safety", "active_transport_general",
]

# ---------------------------------------------------------------------------
# Compile matchers
# ---------------------------------------------------------------------------

def make_matcher(patterns):
    escaped = [re.escape(p) for p in patterns]
    return re.compile("|".join(escaped), re.IGNORECASE)

MATCHERS = {theme: make_matcher(patterns) for theme, patterns in THEMES.items()}


def tag(petition):
    text = " ".join(filter(None, [
        petition.get("title"),
        petition.get("petition_body"),
    ]))
    return {theme: bool(m.search(text)) for theme, m in MATCHERS.items()}


def is_active_transport(tags):
    return any(tags.get(t) for t in ACTIVE_TRANSPORT_THEMES)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="BCC ePetitions Thematic Tagger")
    ap.add_argument("--input",   default=INPUT_FILE)
    ap.add_argument("--output",  default=OUTPUT_FILE)
    ap.add_argument("--show",    default=None,
                    help="Print petitions matching this theme (e.g. cycling)")
    ap.add_argument("--summary", action="store_true",
                    help="Print theme counts only, skip CSV output")
    args = ap.parse_args()

    print(f"Loading {args.input}...")
    with open(args.input) as f:
        data = json.load(f)

    # Only work with records that have usable text
    usable = [p for p in data if p.get("title") or p.get("petition_body")]
    print(f"  {len(data)} total records, {len(usable)} with usable text\n")

    # Tag everything
    tagged = []
    for p in usable:
        tags = tag(p)
        tagged.append({**p, **tags, "active_transport_any": is_active_transport(tags)})

    # ── Summary ──────────────────────────────────────────────────────────────
    total = len(tagged)
    print(f"{'THEME':<30} {'COUNT':>6}  {'%':>5}  BAR")
    print("-" * 65)

    # Active transport group first
    print("── Active Transport ──")
    for theme in ACTIVE_TRANSPORT_THEMES:
        n = sum(1 for t in tagged if t.get(theme))
        bar = "█" * (n * 40 // max(1, total))
        print(f"  {theme:<28} {n:>6}  {100*n/total:>4.1f}%  {bar}")

    at_any = sum(1 for t in tagged if t.get("active_transport_any"))
    print(f"  {'[any active transport]':<28} {at_any:>6}  {100*at_any/total:>4.1f}%")

    print("\n── Other Themes ──")
    other_themes = [t for t in THEMES if t not in ACTIVE_TRANSPORT_THEMES]
    for theme in other_themes:
        n = sum(1 for t in tagged if t.get(theme))
        bar = "█" * (n * 40 // max(1, total))
        print(f"  {theme:<28} {n:>6}  {100*n/total:>4.1f}%  {bar}")

    # ── Show mode ────────────────────────────────────────────────────────────
    if args.show:
        theme = args.show
        if theme not in THEMES:
            print(f"\nUnknown theme '{theme}'. Available: {', '.join(THEMES)}")
        else:
            matches = [t for t in tagged if t.get(theme)]
            matches.sort(key=lambda x: x.get("signatures") or 0, reverse=True)
            print(f"\n── '{theme}' matches: {len(matches)} petitions ──\n")
            for p in matches:
                sigs  = p.get("signatures") or 0
                date  = (p.get("close_date") or "")[:11]
                title = (p.get("title") or "(no title)")[:70]
                body  = (p.get("petition_body") or "")[:120]
                print(f"  PID {p['pid']:5d} | {sigs:>5} sigs | {date} | {title}")
                if body:
                    print(f"           {body}...")
                print()
        if args.summary:
            return

    # ── CSV output ───────────────────────────────────────────────────────────
    if not args.summary:
        theme_cols = list(THEMES.keys())
        fieldnames = [
            "pid", "url", "title", "petitioner", "suburb",
            "close_date", "signatures", "status",
            "active_transport_any",
        ] + theme_cols + [
            "petition_body_excerpt",
            "council_response_excerpt",
        ]

        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in tagged:
                body = row.get("petition_body") or ""
                resp = row.get("council_response") or ""
                writer.writerow({
                    **row,
                    "petition_body_excerpt":    body[:400],
                    "council_response_excerpt": resp[:300],
                })

        print(f"\nCSV written: {args.output}  ({len(tagged)} rows)")
        print("\nTo find active transport petitions in Excel:")
        print("  Filter column 'active_transport_any' = TRUE")
        print("  Then sort by 'signatures' descending")
        print("\nTo search a specific theme:")
        print("  python themes.py --show cycling")
        print("  python themes.py --show traffic_calming")
        print("  python themes.py --show speed_limit")


if __name__ == "__main__":
    main()
