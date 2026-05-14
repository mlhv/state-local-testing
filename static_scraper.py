"""
calEProcure event enrichment scraper.
Usage:
  python scraper.py probe   -- fetch one event page and dump its HTML for selector inspection
  python scraper.py run     -- scrape all events from the XLS and output enriched CSV
"""

import sys
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup
from pathlib import Path

XLS_PATH = "events.xls"       # path to your downloaded XLS
OUTPUT_PATH = "events_enriched.csv"
DELAY_SECONDS = 1.5           # be polite; ~13 min for 528 events

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

def build_url(dept_code, event_id):
    dept = str(int(dept_code)).zfill(4)
    return f"https://caleprocure.ca.gov/event/{dept}/{event_id}"

def parse_event_page(html):
    soup = BeautifulSoup(html, "html.parser")

    # --- Description ---
    # TODO: verify this selector after running `probe`
    description = ""
    desc_el = soup.select_one(".event-description, #event-description, [class*='description']")
    if desc_el:
        description = desc_el.get_text(separator=" ", strip=True)

    # --- UNSPSC codes ---
    # TODO: verify this selector after running `probe`
    unspsc_codes = []
    for el in soup.select("[class*='unspsc'], [id*='unspsc']"):
        text = el.get_text(strip=True)
        if text:
            unspsc_codes.append(text)

    return {
        "description": description,
        "unspsc_codes": "; ".join(unspsc_codes) if unspsc_codes else "",
    }

def probe():
    """Fetch one event page and dump relevant HTML sections for selector inspection."""
    df = pd.read_excel(XLS_PATH, header=0, engine="xlrd")  # row 1 (0-indexed) is the header in calEProcure XLS
    print("Columns found:", df.columns.tolist())
    print("First row:", df.iloc[0].to_dict())

    row = df.iloc[0]
    dept_col = df.columns[0]   # first column = department code
    id_col   = df.columns[2]   # third column = event ID

    url = build_url(row[dept_col], row[id_col])
    print(f"\nFetching: {url}\n")

    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Dump full text so you can grep for "UNSPSC", "description", etc.
    Path("probe_output.html").write_text(resp.text)
    print("Full HTML saved to probe_output.html")
    print("\n--- Page title ---")
    print(soup.title.string if soup.title else "(no title)")
    print("\n--- All class names on the page (unique) ---")
    classes = set()
    for tag in soup.find_all(True):
        for c in tag.get("class", []):
            classes.add(c)
    for c in sorted(classes):
        print(" ", c)

def run():
    df = pd.read_excel(XLS_PATH, header=0, engine="xlrd")
    dept_col = df.columns[0]
    id_col   = df.columns[2]

    enriched = []
    total = len(df)

    for i, row in df.iterrows():
        url = build_url(row[dept_col], row[id_col])
        print(f"[{i+1}/{total}] {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            extra = parse_event_page(resp.text)
        except Exception as e:
            print(f"  ERROR: {e}")
            extra = {"description": "", "unspsc_codes": ""}

        enriched.append({**row.to_dict(), **extra, "event_url": url})
        time.sleep(DELAY_SECONDS)

    out = pd.DataFrame(enriched)
    out.to_csv(OUTPUT_PATH, index=False)
    print(f"\nDone. Saved {len(out)} rows to {OUTPUT_PATH}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
