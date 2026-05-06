#!/usr/bin/env python3
"""
Brisbane City Council ePetitions Analysis
==========================================
Run after scraper.py has produced petitions.json

Usage:
    python analyse.py                     # Full analysis + charts
    python analyse.py --no-charts         # Text analysis only
    python analyse.py --search cycling    # Search petition text
    python analyse.py --ward "The Gap"    # Filter by ward
"""

import json
import argparse
import re
from collections import Counter, defaultdict
from datetime import datetime

try:
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    from matplotlib.gridspec import GridSpec
    import seaborn as sns
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False
    print("Note: install pandas + matplotlib + seaborn for charts.")

INPUT_FILE = "petitions.json"


def load(path=INPUT_FILE):
    with open(path) as f:
        data = json.load(f)
    print(f"Loaded {len(data)} petitions from {path}")
    return data


def to_df(data):
    """Convert list of petition dicts to a DataFrame."""
    df = pd.DataFrame(data)
    # Parse dates
    for col in ["open_date", "close_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
    # Duration in days
    if "open_date" in df.columns and "close_date" in df.columns:
        df["duration_days"] = (df["close_date"] - df["open_date"]).dt.days
    # Year
    if "open_date" in df.columns:
        df["year"] = df["open_date"].dt.year
    # Signatures as numeric
    if "signatures" in df.columns:
        df["signatures"] = pd.to_numeric(df["signatures"], errors="coerce")
    return df


# ── Text analysis ──────────────────────────────────────────────────────────────

STOPWORDS = {
    "the", "a", "an", "and", "or", "in", "of", "to", "for", "on", "at",
    "is", "are", "we", "our", "that", "this", "be", "by", "with", "from",
    "as", "it", "its", "not", "have", "has", "will", "would", "council",
    "brisbane", "city", "petition", "petitioners", "undersigned", "call",
    "request", "ask", "urge", "their", "which", "all", "any", "no", "was",
    "been", "were", "they", "more", "can", "also",
}


def extract_keywords(texts, top_n=30):
    counts = Counter()
    for text in texts:
        if not text:
            continue
        words = re.findall(r"[a-zA-Z]{4,}", text.lower())
        counts.update(w for w in words if w not in STOPWORDS)
    return counts.most_common(top_n)


def topic_keywords():
    """Return topic → keyword list mapping for categorisation."""
    return {
        "Transport / Roads": [
            "road", "traffic", "speed", "pedestrian", "cycle", "cycling", "bike",
            "footpath", "crossing", "intersection", "bus", "transport", "parking",
            "safety", "path", "street", "lane"
        ],
        "Parks / Green space": [
            "park", "tree", "green", "garden", "playground", "open space",
            "nature", "environment", "conservation", "wildlife", "vegetation"
        ],
        "Development / Planning": [
            "development", "planning", "zoning", "height", "building", "approval",
            "heritage", "rezoning", "density", "neighbour", "residential"
        ],
        "Infrastructure / Maintenance": [
            "maintenance", "footpath", "drain", "sewer", "water", "flooding",
            "pothole", "repair", "infrastructure", "upgrade"
        ],
        "Community facilities": [
            "community", "library", "pool", "centre", "facility", "club",
            "sporting", "recreation", "oval", "court"
        ],
        "Noise / Amenity": [
            "noise", "amenity", "pollution", "light", "odour", "nuisance",
            "industrial", "commercial"
        ],
        "Animals": [
            "dog", "cat", "animal", "wildlife", "koala", "bird", "leash"
        ],
    }


def classify_topic(text):
    if not text:
        return "Other"
    text_lower = text.lower()
    topics = topic_keywords()
    scores = {}
    for topic, kws in topics.items():
        score = sum(1 for kw in kws if kw in text_lower)
        if score > 0:
            scores[topic] = score
    if not scores:
        return "Other"
    return max(scores, key=scores.get)


# ── Core analysis functions ────────────────────────────────────────────────────

def summary_stats(df):
    print("\n" + "=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)
    print(f"Total petitions scraped:  {len(df)}")
    if "status" in df.columns:
        print(f"\nBy status:")
        for s, n in df["status"].value_counts().items():
            print(f"  {s:15s}: {n}")
    if "signatures" in df.columns:
        sigs = df["signatures"].dropna()
        if len(sigs):
            print(f"\nSignatures:")
            print(f"  Total signatures:   {int(sigs.sum()):,}")
            print(f"  Mean per petition:  {sigs.mean():.0f}")
            print(f"  Median:             {sigs.median():.0f}")
            print(f"  Max:                {int(sigs.max()):,}")
    if "year" in df.columns:
        years = df["year"].dropna()
        if len(years):
            print(f"\nYear range:  {int(years.min())} – {int(years.max())}")
    if "ward" in df.columns:
        wards = df["ward"].dropna()
        if len(wards):
            print(f"Unique wards: {wards.nunique()}")


def top_petitions(df, n=20):
    print(f"\n{'=' * 60}")
    print(f"TOP {n} PETITIONS BY SIGNATURES")
    print("=" * 60)
    if "signatures" not in df.columns:
        print("No signature data available.")
        return
    top = df.nlargest(n, "signatures")[["pid", "title", "signatures", "ward", "year"]]
    for _, row in top.iterrows():
        print(f"  PID {row['pid']:5d} | {int(row['signatures'] or 0):6,} sigs | "
              f"{str(row.get('ward', ''))[:20]:20s} | "
              f"{str(row.get('title', ''))[:50]}")


def ward_analysis(df):
    print(f"\n{'=' * 60}")
    print("TOP WARDS BY PETITION COUNT")
    print("=" * 60)
    if "ward" not in df.columns:
        return
    ward_counts = df["ward"].value_counts().head(20)
    for ward, count in ward_counts.items():
        bar = "█" * (count * 30 // (ward_counts.max() or 1))
        print(f"  {str(ward)[:25]:25s} {count:4d} {bar}")


def keyword_analysis(df):
    print(f"\n{'=' * 60}")
    print("TOP 30 KEYWORDS IN PETITION TEXT")
    print("=" * 60)
    texts = df["body"].fillna("").tolist() + df["title"].fillna("").tolist()
    keywords = extract_keywords(texts, top_n=30)
    max_count = keywords[0][1] if keywords else 1
    for word, count in keywords:
        bar = "█" * (count * 40 // max_count)
        print(f"  {word:20s} {count:5d} {bar}")


def topic_analysis(df):
    print(f"\n{'=' * 60}")
    print("TOPIC DISTRIBUTION (keyword heuristic)")
    print("=" * 60)
    combined = df["title"].fillna("") + " " + df.get("body", pd.Series([""] * len(df))).fillna("")
    df = df.copy()
    df["topic"] = combined.apply(classify_topic)
    topic_counts = df["topic"].value_counts()
    for topic, count in topic_counts.items():
        bar = "█" * (count * 30 // (topic_counts.max() or 1))
        pct = 100 * count / len(df)
        print(f"  {topic:30s} {count:4d} ({pct:4.1f}%) {bar}")
    return df


def search_petitions(df, query):
    print(f"\n{'=' * 60}")
    print(f"SEARCH RESULTS: '{query}'")
    print("=" * 60)
    q = query.lower()
    mask = (
        df["title"].fillna("").str.lower().str.contains(q, regex=False) |
        df.get("body", pd.Series([""] * len(df))).fillna("").str.lower().str.contains(q, regex=False)
    )
    results = df[mask].sort_values("signatures", ascending=False)
    print(f"Found {len(results)} matching petitions:\n")
    for _, row in results.iterrows():
        print(f"  PID {row['pid']:5d} | {int(row.get('signatures') or 0):6,} sigs | "
              f"{str(row.get('status', '')):8s} | {str(row.get('title', ''))[:60]}")
    return results


def filter_ward(df, ward):
    mask = df["ward"].fillna("").str.lower().str.contains(ward.lower(), regex=False)
    results = df[mask]
    print(f"\nFiltered to ward '{ward}': {len(results)} petitions")
    return results


# ── Plotting ───────────────────────────────────────────────────────────────────

def make_charts(df, output="bcc_petitions_analysis.png"):
    if not HAS_PLOTTING:
        print("matplotlib not available, skipping charts.")
        return

    sns.set_theme(style="whitegrid", palette="muted")
    fig = plt.figure(figsize=(18, 14))
    fig.suptitle("Brisbane City Council ePetitions — Analysis", fontsize=16, fontweight="bold", y=0.98)
    gs = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35)

    # 1. Petitions per year
    ax1 = fig.add_subplot(gs[0, :2])
    if "year" in df.columns:
        year_data = df["year"].dropna().value_counts().sort_index()
        ax1.bar(year_data.index.astype(int), year_data.values, color="#2196F3")
        ax1.set_title("Petitions Filed Per Year")
        ax1.set_xlabel("Year")
        ax1.set_ylabel("Count")
        ax1.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    # 2. Status pie
    ax2 = fig.add_subplot(gs[0, 2])
    if "status" in df.columns:
        status_counts = df["status"].value_counts()
        ax2.pie(status_counts.values, labels=status_counts.index, autopct="%1.0f%%",
                colors=["#66BB6A", "#EF5350", "#FFA726", "#78909C"])
        ax2.set_title("Petition Status")

    # 3. Top 15 wards
    ax3 = fig.add_subplot(gs[1, :2])
    if "ward" in df.columns:
        top_wards = df["ward"].value_counts().head(15)
        ax3.barh(top_wards.index[::-1], top_wards.values[::-1], color="#7E57C2")
        ax3.set_title("Top 15 Wards by Petition Count")
        ax3.set_xlabel("Petitions")

    # 4. Signature distribution (log scale)
    ax4 = fig.add_subplot(gs[1, 2])
    if "signatures" in df.columns:
        sigs = df["signatures"].dropna()
        sigs = sigs[sigs > 0]
        ax4.hist(sigs, bins=40, color="#26A69A", edgecolor="white")
        ax4.set_title("Signature Distribution")
        ax4.set_xlabel("Signatures")
        ax4.set_ylabel("Count")
        ax4.set_yscale("log")

    # 5. Topic distribution
    ax5 = fig.add_subplot(gs[2, :2])
    combined = df["title"].fillna("") + " " + df.get("body", pd.Series([""] * len(df))).fillna("")
    topics = combined.apply(classify_topic).value_counts()
    colors = sns.color_palette("Set2", len(topics))
    ax5.barh(topics.index[::-1], topics.values[::-1], color=colors[::-1])
    ax5.set_title("Topic Distribution (Keyword Heuristic)")
    ax5.set_xlabel("Petitions")

    # 6. Median sigs by topic
    ax6 = fig.add_subplot(gs[2, 2])
    if "signatures" in df.columns:
        df2 = df.copy()
        df2["topic"] = combined.apply(classify_topic)
        med_sigs = df2.groupby("topic")["signatures"].median().sort_values()
        ax6.barh(med_sigs.index, med_sigs.values, color="#FF7043")
        ax6.set_title("Median Signatures by Topic")
        ax6.set_xlabel("Median Signatures")

    plt.savefig(output, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to: {output}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BCC ePetitions Analysis")
    parser.add_argument("--input", default=INPUT_FILE)
    parser.add_argument("--no-charts", action="store_true")
    parser.add_argument("--search", type=str, default=None, help="Search keyword")
    parser.add_argument("--ward", type=str, default=None, help="Filter by ward name")
    args = parser.parse_args()

    data = load(args.input)

    if not HAS_PLOTTING:
        # Text-only mode
        for p in data:
            body = p.get("body", "")
            p["topic"] = classify_topic((p.get("title") or "") + " " + (body or ""))
        print("\nTop petitions:")
        sorted_data = sorted(data, key=lambda x: x.get("signatures") or 0, reverse=True)
        for p in sorted_data[:20]:
            print(f"  PID {p['pid']:5d} | {p.get('signatures') or 0:6,} sigs | {(p.get('title') or '')[:60]}")
        return

    df = to_df(data)

    if args.search:
        search_petitions(df, args.search)
        return

    if args.ward:
        df = filter_ward(df, args.ward)

    summary_stats(df)
    top_petitions(df)
    ward_analysis(df)
    keyword_analysis(df)
    df = topic_analysis(df)

    if not args.no_charts:
        make_charts(df)


if __name__ == "__main__":
    main()
