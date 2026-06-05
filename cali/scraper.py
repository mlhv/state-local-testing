"""
calEProcure event enrichment scraper.
Usage:
  python scraper.py probe   -- fetch one event and print extracted fields
  python scraper.py run     -- scrape all events from the XLS and output enriched CSV
"""

import json
import re
import sys
import time
import requests
import pandas as pd
from pathlib import Path

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
LIST_ENDPOINT = (
    "https://caleprocure.ca.gov/nlx3/psc/psfpd1"
    "/SUPPLIER/ERP/c/AUC_MANAGE_BIDS.AUC_RESP_INQ_AUC.GBL"
)
LIST_TEMPLATE_PATH = "nlx_list_body.txt"
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
    Handles the 278 IFLocation redirect that NLX uses to pin to a backend node.
    Re-establishes the session if it appears to have expired (empty results)."""
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

    # Pre-bid conference fields are children of the conferenceRow node
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


def load_template():
    if not Path(TEMPLATE_PATH).exists():
        sys.exit(f"ERROR: {TEMPLATE_PATH} not found — copy the IF-TargetContent payload from DevTools and replace the file ")
    return Path(TEMPLATE_PATH).read_text()


def _dept_from_href(href: str) -> str:
    """Extract dept code from a calEProcure event URL, e.g. /event/0250/..."""
    if not href or href == "#":
        return ""
    m = re.search(r"/event/([^/]+)/", href)
    return m.group(1) if m else ""


def discover_events(session) -> pd.DataFrame:
    """Fetch all open events from the NLX list API. Returns a DataFrame."""
    template_path = Path(__file__).parent / LIST_TEMPLATE_PATH
    if not template_path.exists():
        sys.exit(f"ERROR: {template_path} not found")
    body = template_path.read_text()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://caleprocure.ca.gov/pages/Events-BS3/event-search.aspx",
        "Origin": "https://caleprocure.ca.gov",
    }
    resp = session.post(LIST_ENDPOINT, data=body, headers=headers, timeout=30)

    if resp.status_code == 278:
        location = resp.json().get("IFLocation", "")
        if location.startswith("/"):
            location = "https://caleprocure.ca.gov" + location
        resp = session.post(location, data=body, headers=headers, timeout=30)

    resp.raise_for_status()
    results = resp.json().get("CaptureResults", {})
    rows = results.get("tbl", [{}])[0].get("Children", {}).get("tblBodyTr", [])
    if not rows:
        sys.exit("ERROR: List API returned 0 events — check session or portal status")

    records = []
    for row in rows:
        ch = row.get("Children", {})
        event_id   = (ch.get("tdEventId",   [{}])[0].get("Properties", {}).get("text")  or "").strip()
        event_name = (ch.get("tdEventName",  [{}])[0].get("Properties", {}).get("text")  or "").strip()
        dep_name   = (ch.get("tdDepName",    [{}])[0].get("Properties", {}).get("text")  or "").strip()
        end_date   = (ch.get("tdEndDate",    [{}])[0].get("Properties", {}).get("text")  or "").strip()
        status     = (ch.get("tdStatus",     [{}])[0].get("Properties", {}).get("text")  or "").strip()
        dept_href  = (ch.get("tdDeptCode",   [{}])[0].get("Properties", {}).get("href")  or "").strip()
        dept_code  = _dept_from_href(dept_href)
        records.append({
            "Event ID":        event_id,
            "Event Name":      event_name,
            "Department Name": dep_name,
            "End Date":        end_date,
            "Status":          status,
            "Department":      dept_code,
        })

    df = pd.DataFrame(records)
    print(f"Discovered {len(df)} events from list API.")
    return df


def probe():
    session = make_session()
    df = discover_events(session)
    body = load_template()
    row = df.iloc[0]
    event_id  = str(row["Event ID"])
    dept      = norm_dept(row["Department"])
    event_url = build_url(row["Department"], event_id)
    print(f"Probing: {event_url}\n")

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
    session = make_session()
    df = discover_events(session)
    body = load_template()
    total = len(df)
    enriched = []

    done_ids = set()
    if Path(OUTPUT_PATH).exists():
        existing = pd.read_csv(OUTPUT_PATH)
        done_ids = set(existing["Event ID"].astype(str))
        enriched = existing.to_dict("records")
        print(f"Resuming — {len(done_ids)} already done, {total - len(done_ids)} remaining")

    for i, row in df.iterrows():
        event_id = str(row["Event ID"])
        if event_id in done_ids:
            continue

        dept      = norm_dept(row["Department"])
        event_url = build_url(row["Department"], event_id)
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
            extra   = extract_event_data(results)
        except Exception as e:
            print(f"  ERROR: {e}")
            extra = EMPTY_EXTRA.copy()

        enriched.append({**row.to_dict(), **extra, "event_url": event_url})
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
