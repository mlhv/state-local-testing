"""
calEProcure event enrichment scraper (Playwright version).
Usage:
  python scraper.py probe   -- fetch one event page and print extracted fields
  python scraper.py run     -- scrape all events from the XLS and output enriched CSV
"""

import sys
import time
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

XLS_PATH = "events.xls"
OUTPUT_PATH = "events_enriched.csv"
PAGE_TIMEOUT_MS = 25_000
DELAY_SECONDS = 1.5

def make_page(p):
    """Launch a browser context that looks like a real user to avoid 403s."""
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        viewport={"width": 1280, "height": 800},
    )
    # Remove the navigator.webdriver flag that identifies Playwright
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = ctx.new_page()
    return browser, page

def build_url(dept_code, event_id):
    dept = str(int(dept_code)).zfill(4)
    return f"https://caleprocure.ca.gov/event/{dept}/{event_id}"

def get_rendered_html(page, url):
    """Navigate and wait for InFlight NLX to finish injecting data."""
    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    try:
        # networkidle = no network requests for 500ms — data injection is done by then
        page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)
    except PWTimeout:
        pass  # partial render — still try to parse what we have
    return page.content()

def extract_event_data(html):
    soup = BeautifulSoup(html, "html.parser")

    # Description
    desc_el = soup.find(attrs={"data-if-label": "descriptiondetails"})
    description = desc_el.get_text(separator="\n", strip=True) if desc_el else ""

    # InFlight NLX renders UNSPSC into data-if-label="unspscCodeBody" rows.
    # The first row uses that label directly; additional rows get data-if-cloned-from.
    unspsc_pairs = []
    unspsc_rows = (
        soup.find_all("tr", attrs={"data-if-label": "unspscCodeBody"}) +
        soup.find_all("tr", attrs={"data-if-cloned-from": "unspscCodeBody"})
    )
    for row in unspsc_rows:
        code_el = row.find("td", attrs={"data-if-label": "unspscClassification"})
        desc_el = row.find("td", attrs={"data-if-label": "unspscDescription"})
        code = code_el.get_text(strip=True) if code_el else ""
        desc = desc_el.get_text(strip=True) if desc_el else ""
        if code and code != "\xa0":
            unspsc_pairs.append(f"{code}: {desc}" if desc else code)

    return {
        "description": description,
        "unspsc_codes": "; ".join(unspsc_pairs),
    }

def load_xls():
    df = pd.read_excel(XLS_PATH, header=0, engine="xlrd")
    print(f"Loaded {len(df)} rows. Columns: {df.columns.tolist()}")
    return df

def probe():
    df = load_xls()
    row = df.iloc[0]
    dept_col, id_col = df.columns[0], df.columns[2]
    url = build_url(row[dept_col], row[id_col])
    print(f"Probing: {url}\n")

    with sync_playwright() as p:
        browser, page = make_page(p)
        html = get_rendered_html(page, url)
        browser.close()

    # Save rendered HTML for inspection if needed
    Path("probe_rendered.html").write_text(html)
    print("Rendered HTML saved to probe_rendered.html")

    data = extract_event_data(html)

    print("\n=== Description ===")
    print(data["description"] or "(empty — check probe_rendered.html for the actual DOM)")
    print("\n=== UNSPSC Codes ===")
    print(data["unspsc_codes"] or "(none found)")

def run():
    df = load_xls()
    dept_col, id_col = df.columns[0], df.columns[2]
    total = len(df)
    enriched = []

    done_ids = set()
    if Path(OUTPUT_PATH).exists():
        existing = pd.read_csv(OUTPUT_PATH)
        done_ids = set(existing[id_col].astype(str))
        enriched = existing.to_dict("records")
        print(f"Resuming — {len(done_ids)} already done, {total - len(done_ids)} remaining")

    with sync_playwright() as p:
        browser, pg = make_page(p)

        for i, row in df.iterrows():
            event_id = str(row[id_col])
            if event_id in done_ids:
                continue

            url = build_url(row[dept_col], event_id)
            print(f"[{i+1}/{total}] {url}")

            try:
                html = get_rendered_html(pg, url)
                extra = extract_event_data(html)
            except Exception as e:
                print(f"  ERROR: {e}")
                extra = {"description": "", "unspsc_codes": ""}

            enriched.append({**row.to_dict(), **extra, "event_url": url})
            pd.DataFrame(enriched).to_csv(OUTPUT_PATH, index=False)
            time.sleep(DELAY_SECONDS)

        browser.close()

    print(f"\nDone. {len(enriched)} rows saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
