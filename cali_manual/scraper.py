"""
calEProcure event enrichment scraper (manual XLS input version).
Usage:
  python scraper.py probe   -- fetch one event and print extracted fields
  python scraper.py run     -- scrape all events from events.xls and output enriched CSV

Input: place a manually exported events.xls from calEProcure in this directory before running.
       Copy nlx_body.txt from ../cali/nlx_body.txt if not already present.
       Expected columns: dept code at position 0, event ID at position 2.
"""

import json
import re
import sys
import time
import requests
import pandas as pd
from pathlib import Path

XLS_PATH = "events.xls"
OUTPUT_PATH = "events_enriched.csv"
TEMPLATE_PATH = "nlx_body.txt"
DELAY_SECONDS = 0.5
NLX_BASE = (
    "https://caleprocure.ca.gov/nlx3/psc/psfpd1_newwin"
    "/SUPPLIER/ERP/c/AUC_MANAGE_BIDS.AUC_RESP_INQ_DTL.GBL"
)
FIXED_PARAMS = {
    "Page":         "AUC_RESP_INQ_DTL",
    "Action":       "U",
    "AUC_ROUND":    "1",
    "BIDDER_ID":    "BID0000001",
    "BIDDER_LOC":   "1",
    "BIDDER_SETID": "STATE",
    "BIDDER_TYPE":  "B",
}
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
EMPTY_EXTRA = {k: "" for k in [
    "description", "unspsc_codes", "contractor_licenses", "counties",
    "service_area_ids", "event_version", "published_date", "contact_phone",
    "prebid_mandatory", "prebid_date", "prebid_time", "prebid_location", "prebid_comments",
    "Buyer Name", "Buyer Email", "Format", "Type",
]}


def build_url(dept_code, event_id):
    try:
        dept = str(int(dept_code)).zfill(4)
    except (ValueError, TypeError):
        dept = str(dept_code).strip()
    return f"https://caleprocure.ca.gov/event/{dept}/{event_id}"


def norm_dept(dept_code):
    try:
        return str(int(dept_code)).zfill(4)
    except (ValueError, TypeError):
        return str(dept_code).strip()


def make_session():
    """Establish a requests.Session with an InFlightSessionID cookie via a plain GET."""
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    session.get(
        "https://caleprocure.ca.gov/pages/Events-BS3/event-search.aspx",
        timeout=20,
    )
    return session


def fetch_results(session, body, event_id, dept, event_url):
    """POST to the InFlight NLX API and return the CaptureResults dict.
    Handles the 278 IFLocation redirect that NLX uses to pin to a backend node."""
    params = {**FIXED_PARAMS, "AUC_ID": event_id, "BUSINESS_UNIT": dept}
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": event_url,
        "Origin": "https://caleprocure.ca.gov",
    }
    resp = session.post(NLX_BASE, params=params, data=body, headers=headers, timeout=30)

    if resp.status_code == 278:
        location = resp.json().get("IFLocation", "")
        if location.startswith("/"):
            location = "https://caleprocure.ca.gov" + location
        resp = session.post(location, data=body, headers=headers, timeout=30)

    resp.raise_for_status()
    return resp.json().get("CaptureResults", {})


def leaf(nodes):
    """Extract the text/html value from an InFlight NLX node list."""
    if nodes:
        props = nodes[0].get("Properties", {})
        return (props.get("text") or props.get("html") or "").replace("\xa0", " ").strip()
    return ""


def extract_event_data(results):
    unspsc_pairs = []
    for row in results.get("unspscCodeBody", []):
        ch = row.get("Children", {})
        code = leaf(ch.get("unspscClassification", []))
        desc = leaf(ch.get("unspscDescription", []))
        if code and code != "\xa0":
            unspsc_pairs.append(f"{code}: {desc}" if desc else code)

    contractor_licenses = []
    for row in results.get("contractorTblBody", []):
        ch = row.get("Children", {})
        lic_type = leaf(ch.get("contractorTblType", []))
        lic_desc = leaf(ch.get("contractorTblDescription", []))
        if lic_type and lic_type != "\xa0":
            contractor_licenses.append(f"{lic_type}: {lic_desc}" if lic_desc else lic_type)

    counties = []
    service_area_ids = []
    for row in results.get("serviceAreaTblBody", []):
        ch = row.get("Children", {})
        county  = leaf(ch.get("serviceAreaCounty", []))
        area_id = leaf(ch.get("serviceAreaID", []))
        if county and county != "\xa0":
            counties.append(county)
            service_area_ids.append(area_id)

    conf_children = {}
    conf_row = results.get("conferenceRow", [])
    if conf_row:
        conf_children = conf_row[0].get("Children", {})

    buyer_name  = leaf(results.get("contactName", []))
    buyer_email = leaf(results.get("emailAnchor", []))
    fmt         = leaf(results.get("format1",     []))
    event_type  = leaf(results.get("format2",     []))

    return {
        "description":         leaf(results.get("descriptiondetails", [])),
        "unspsc_codes":        "; ".join(unspsc_pairs),
        "contractor_licenses": "; ".join(contractor_licenses),
        "counties":            "; ".join(counties),
        "service_area_ids":    "; ".join(service_area_ids),
        "event_version":       leaf(results.get("eventVersion", [])),
        "published_date":      leaf(results.get("eventStartDate", [])),
        "contact_phone":       leaf(results.get("phoneText", [])),
        "prebid_mandatory":    leaf(conf_children.get("conferenceText", [])),
        "prebid_date":         leaf(conf_children.get("dateText", [])),
        "prebid_time":         leaf(conf_children.get("timeText", [])),
        "prebid_location":     leaf(conf_children.get("locationText", [])),
        "prebid_comments":     leaf(conf_children.get("commentsText", [])),
        "Buyer Name":          buyer_name,
        "Buyer Email":         buyer_email,
        "Format":              fmt,
        "Type":                event_type,
    }


def load_xls():
    if not Path(XLS_PATH).exists():
        sys.exit(f"ERROR: {XLS_PATH} not found — export from calEProcure and place here")
    try:
        df = pd.read_excel(XLS_PATH, header=0, engine="xlrd")
    except Exception:
        # Portal exports HTML disguised as .xls — parse as HTML table instead
        tables = pd.read_html(XLS_PATH, header=0)
        if not tables:
            sys.exit("ERROR: no tables found in events.xls")
        df = tables[0]
    print(f"Loaded {len(df)} rows. Columns: {df.columns.tolist()}")
    return df


def load_template():
    if not Path(TEMPLATE_PATH).exists():
        sys.exit(f"ERROR: {TEMPLATE_PATH} not found — copy from ../cali/nlx_body.txt")
    return Path(TEMPLATE_PATH).read_text()


def probe():
    df = load_xls()
    body = load_template()
    dept_col, id_col = df.columns[0], df.columns[2]
    row = df.iloc[0]
    event_id  = str(row[id_col])
    dept      = norm_dept(row[dept_col])
    event_url = build_url(row[dept_col], event_id)
    print(f"Probing: {event_url}\n")

    session = make_session()
    results = fetch_results(session, body, event_id, dept, event_url)

    if not dept:
        script_nodes = results.get("strCurrScript", [])
        if script_nodes:
            html = script_nodes[0].get("Properties", {}).get("html", "")
            m = re.search(r"BUSINESS_UNIT=([^&'\"]+)", html)
            if m:
                dept = m.group(1)
                event_url = build_url(dept, event_id)
                print(f"(dept extracted from strCurrScript: {dept})")

    Path("probe_response.json").write_text(json.dumps(results, indent=2))
    print("Raw JSON saved to probe_response.json\n")

    data = extract_event_data(results)

    print("=== Description ===")
    print(data["description"] or "(empty — check probe_response.json)")
    print("\n=== UNSPSC Codes ===")
    print(data["unspsc_codes"] or "(none)")
    print("\n=== Contractor License Types ===")
    print(data["contractor_licenses"] or "(none)")
    print("\n=== Counties (Service Area) ===")
    print(data["counties"] or "(none)")
    print("\n=== Event Details ===")
    print(f"Buyer Name:        {data['Buyer Name']}")
    print(f"Buyer Email:       {data['Buyer Email']}")
    print(f"Format:            {data['Format']}")
    print(f"Type:              {data['Type']}")
    print(f"Version:           {data['event_version']}")
    print(f"Published Date:    {data['published_date']}")
    print(f"Contact Phone:     {data['contact_phone']}")
    print(f"Pre-Bid Mandatory: {data['prebid_mandatory']}")
    print(f"Pre-Bid Date:      {data['prebid_date']}")
    print(f"Pre-Bid Time:      {data['prebid_time']}")
    print(f"Pre-Bid Location:  {data['prebid_location']}")
    print(f"Pre-Bid Comments:  {data['prebid_comments']}")


def run():
    df = load_xls()
    body = load_template()
    dept_col, id_col = df.columns[0], df.columns[2]
    total = len(df)
    enriched = []

    done_ids = set()
    if Path(OUTPUT_PATH).exists():
        existing = pd.read_csv(OUTPUT_PATH)
        if "scrape_status" not in existing.columns:
            existing["scrape_status"] = existing["event_version"].apply(
                lambda v: "success" if pd.notna(v) and v != "" else "error"
            )
        done_ids = set(existing.loc[existing["scrape_status"] == "success", id_col].astype(str))
        enriched = existing.to_dict("records")
        new_count = len(set(df[id_col].astype(str)) - done_ids)
        print(f"Resuming — {len(done_ids)} successfully done, {new_count} remaining")

    session = make_session()

    for i, row in df.iterrows():
        event_id = str(row[id_col])
        if event_id in done_ids:
            continue

        dept      = norm_dept(row[dept_col])
        event_url = build_url(row[dept_col], event_id)
        print(f"[{i+1}/{total}] {event_url}")

        try:
            results = fetch_results(session, body, event_id, dept, event_url)
            if not dept:
                script_nodes = results.get("strCurrScript", [])
                if script_nodes:
                    html = script_nodes[0].get("Properties", {}).get("html", "")
                    m = re.search(r"BUSINESS_UNIT=([^&'\"]+)", html)
                    if m:
                        dept = m.group(1)
                        event_url = build_url(dept, event_id)
            extra         = extract_event_data(results)
            scrape_status = "success"
        except Exception as e:
            print(f"  ERROR: {e}")
            extra         = EMPTY_EXTRA.copy()
            scrape_status = "error"

        record = row.to_dict()
        if dept and not record.get(dept_col):
            record[dept_col] = dept
        enriched.append({**record, **extra, "scrape_status": scrape_status, "event_url": event_url})
        pd.DataFrame(enriched).to_csv(OUTPUT_PATH, index=False)
        time.sleep(DELAY_SECONDS)

    print(f"\nDone. {len(enriched)} rows saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
