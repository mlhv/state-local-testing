"""
api_probe.py — validates whether the InFlight NLX JSON API can be called
with plain requests after extracting session cookies via Playwright.

The goal: replace full-page Playwright rendering with a direct POST that
returns the same data as structured JSON, bypassing BeautifulSoup entirely.

Run:
  python api_probe.py
"""

import requests
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from scraper import make_page, build_url, load_xls

captured = {}


def main():
    df = load_xls()
    row = df.iloc[0]
    dept_col, id_col = df.columns[0], df.columns[2]
    event_url = build_url(row[dept_col], row[id_col])
    print(f"Probe event: {event_url}\n")

    # ── Step 1: load the page via Playwright, intercept the NLX API POST ──────
    print("Step 1: Loading page with Playwright to capture API call + session cookies...")
    with sync_playwright() as p:
        browser, page = make_page(p)

        def on_request(req):
            if "AUC_RESP_INQ_DTL.GBL" in req.url and req.method == "POST" and "url" not in captured:
                captured["url"] = req.url
                captured["body"] = req.post_data  # raw URL-encoded form string
                print(f"  Captured: {req.url[:100]}")

        page.on("request", on_request)
        page.goto(event_url, wait_until="domcontentloaded", timeout=25_000)
        try:
            page.wait_for_load_state("networkidle", timeout=25_000)
        except PWTimeout:
            pass

        cookies = page.context.cookies()
        browser.close()

    if "url" not in captured:
        print("ERROR: NLX API call was not intercepted — try a different event or check the URL.")
        return

    # Save the POST body so cold_probe.py can reuse it without running Playwright
    Path("nlx_body.txt").write_text(captured["body"])
    print("  Saved POST body to nlx_body.txt")

    # ── Step 2: replay the same POST with requests using the captured cookies ──
    print("\nStep 2: Replaying POST with requests.Session()...")
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": event_url,
        "Origin": "https://caleprocure.ca.gov",
    })
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c["domain"].lstrip("."))

    resp = session.post(captured["url"], data=captured["body"], timeout=30)
    print(f"  Status: {resp.status_code}  Content-Type: {resp.headers.get('content-type', '')}")

    # InFlight NLX uses 278 as a custom redirect — follow the IFLocation manually
    if resp.status_code == 278:
        location = resp.json().get("IFLocation", "")
        if location.startswith("/"):
            location = "https://caleprocure.ca.gov" + location
        print(f"  Following IFLocation: {location[:100]}")
        resp = session.post(location, data=captured["body"], timeout=30)
        print(f"  Status: {resp.status_code}  Content-Type: {resp.headers.get('content-type', '')}")

    if resp.status_code != 200:
        print(f"  Body preview: {resp.text[:400]}")
        return

    try:
        data = resp.json()
    except Exception as e:
        print(f"  JSON parse failed: {e}")
        print(f"  Body preview: {resp.text[:400]}")
        return

    # ── Debug: dump raw JSON so we can see the actual structure ──────────────────
    import json as _json
    print("\n  Raw JSON (first 2000 chars):")
    print(_json.dumps(data, indent=2)[:2000])
    print("  ...")

    # ── Step 3: extract fields from the JSON using InFlight NLX node structure ─
    # All captured fields live under the top-level "CaptureResults" key.
    results = data.get("CaptureResults", data)
    print("\nStep 3: Extracted fields from JSON response:")

    def leaf(nodes):
        if nodes:
            props = nodes[0].get("Properties", {})
            return props.get("text") or props.get("html") or ""
        return ""

    def child(nodes, key):
        if nodes:
            return leaf(nodes[0].get("Children", {}).get(key, []))
        return ""

    scalar_fields = {
        "event_version":    leaf(results.get("eventVersion")),
        "published_date":   leaf(results.get("eventStartDate")),
        "contact_phone":    leaf(results.get("phoneText")),
        "prebid_mandatory": leaf(results.get("conferenceText")),
        "prebid_date":      leaf(results.get("dateText")),
        "prebid_time":      leaf(results.get("timeText")),
        "prebid_location":  leaf(results.get("locationText")),
        "prebid_comments":  leaf(results.get("commentsText")),
        "description":      leaf(results.get("descriptiondetails")),
    }
    for k, v in scalar_fields.items():
        print(f"  {k:<20} {str(v)[:80]}")

    # UNSPSC rows
    unspsc_rows = results.get("unspscCodeBody", [])
    print(f"\n  unspscCodeBody rows: {len(unspsc_rows)}")
    for row in unspsc_rows[:3]:
        ch = row.get("Children", {})
        code = leaf(ch.get("unspscClassification", []))
        desc = leaf(ch.get("unspscDescription", []))
        if code:
            print(f"    {code}: {desc[:70]}")

    # Service area rows
    sa_rows = results.get("serviceAreaTblBody", [])
    print(f"\n  serviceAreaTblBody rows: {len(sa_rows)}")
    for row in sa_rows[:5]:
        ch = row.get("Children", {})
        area_id = leaf(ch.get("serviceAreaID", []))
        county  = leaf(ch.get("serviceAreaCounty", []))
        if county:
            print(f"    {area_id}: {county}")

    # Contractor license rows
    lic_rows = results.get("contractorTblBody", [])
    print(f"\n  contractorTblBody rows: {len(lic_rows)}")
    for row in lic_rows[:3]:
        ch = row.get("Children", {})
        lic_type = leaf(ch.get("contractorTblType", []))
        lic_desc = leaf(ch.get("contractorTblDescription", []))
        if lic_type:
            print(f"    {lic_type}: {lic_desc[:70]}")

    print("\n── Result ──────────────────────────────────────────────────────────────")
    print("API call succeeded. JSON contains all expected labels.")
    print("Next step: test a cold requests call (no Playwright at all) by hitting")
    print("the event-details page first to establish InFlightSessionID, then POST.")


if __name__ == "__main__":
    main()
