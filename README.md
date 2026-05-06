# BCC ePetitions Scraper & Analyser

Scrapes all petitions (current + archived) from
`epetitions.brisbane.qld.gov.au` and runs analysis.

## Setup

```bash
pip install requests beautifulsoup4 pandas matplotlib seaborn
```

## Step 1: Scrape

```bash
# Full scrape (auto-detects PID range, ~1.5s delay between requests)
python scraper.py

# Quick test run (only sweeps PIDs 1–200)
python scraper.py --max-pid 200

# Faster (be polite — don't go below 1.0s on a govt site)
python scraper.py --delay 1.0

# Resume interrupted scrape
python scraper.py --resume
```

The scraper:
- Fetches the current petitions listing page
- Fetches the archive listing (paginated)
- Sweeps all PIDs from 1 → max (skipping 404s)
- Saves incrementally to `petitions.json` every 20 records
- Logs progress to `scraper.log`

Output: `petitions.json` — array of petition objects.

## Step 2: Analyse

```bash
# Full analysis + charts
python analyse.py

# Text-only (no matplotlib required)
python analyse.py --no-charts

# Search for keywords in title/body
python analyse.py --search cycling
python analyse.py --search "speed limit"
python analyse.py --search footpath

# Filter by ward
python analyse.py --ward "The Gap"
python analyse.py --ward Paddington
```

Output: `bcc_petitions_analysis.png` with 6 charts:
1. Petitions filed per year
2. Status breakdown (open / closed / etc.)
3. Top 15 wards by petition count
4. Signature distribution (log scale)
5. Topic distribution (keyword heuristic)
6. Median signatures by topic

## Petition JSON schema

Each petition object has:

| Field            | Description                          |
|------------------|--------------------------------------|
| pid              | Petition ID (integer)                |
| url              | Full URL                             |
| title            | Petition title                       |
| status           | open / closed / unknown              |
| category         | BCC category if present              |
| ward             | Brisbane ward                        |
| councillor       | Responsible councillor               |
| petitioner       | Head petitioner name                 |
| open_date        | Date opened (string)                 |
| close_date       | Date closed (string)                 |
| signatures       | Signature count (integer)            |
| body             | Petition text                        |
| council_response | Council response text (if any)       |
| scraped_at       | ISO timestamp of scrape              |

## Notes

- The site's robots.txt disallows crawlers. For civic/research use,
  identify yourself clearly in the User-Agent string and use a polite delay.
- PIDs are not necessarily contiguous — gaps are normal.
- The parser uses heuristic HTML extraction since BCC doesn't publish an API.
  If the page structure differs from expectations, some fields may be null —
  check a few raw pages and adjust the CSS selectors in `parse_petition_page()`.
- Run `python scraper.py --max-pid 50` first to check a handful of pages
  render correctly before committing to a full scrape.
# BCCPetitionsInsights
