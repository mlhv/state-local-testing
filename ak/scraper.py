"""
Alaska IRIS VSS public solicitations scraper.
Usage:
  python scraper.py probe   -- discover open solicitations, pick first, print all fields
  python scraper.py run     -- discover open solicitations, enrich all new, write CSV
"""

import sys, time, uuid, random, datetime
import requests
import pandas as pd
from pathlib import Path

OUTPUT_PATH = "solicitations_enriched.csv"
DELAY_SECONDS = 0.5
BASE_URL = "https://iris-vss.alaska.gov/PRDVSS1X1/Advantage4"
PORTAL_URL = "https://iris-vss.alaska.gov/"
USER_DATA_DIR = Path.home() / ".ak_scraper_profile"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

LIST_FIELDS = [
    "doc_ref", "doc_type", "description", "department",
    "buyer_name", "buyer_email", "buyer_phone",
    "closing_dt", "publish_dt", "amended_dt", "status", "category_code",
]

SCRAPED_FIELDS = [
    "additional_instructions", "commodity_descriptions",
    "commodity_codes", "commodity_specs", "alaska_url", "scrape_status",
]

EMPTY_SCRAPED = {k: "" for k in SCRAPED_FIELDS}

# Static search page checksum (VIEW is stable for this page layout)
_SEARCH_VIEW_CHECKSUM = 3838637284

# Static viewState for the solicitations search page
_SEARCH_VIEWSTATE = {
    "vss.page.VVSSX10019.gridView1.group1.cardSearch": {"editable": True},
    "vss.page.VVSSX10019.gridView1.group1.cardSearch.search1": {"editable": True},
    "vss.page.VVSSX10019": {
        "closed": False, "hidden": False, "editable": False,
        "protected": False, "required": False,
    },
}


def _adv_headers(ctx: dict, action_code: str, action_type: str) -> dict:
    """Build Adv-* request headers and increment request_id in ctx."""
    ctx["request_id"] += 1
    return {
        "Accept":              "application/json, text/plain, */*",
        "Content-Type":        "application/json;charset=UTF-8",
        "Adv-Action-Code":     action_code,
        "Adv-Action-Type":     action_type,
        "Adv-Conversation-Id": ctx["conversation_id"],
        "Adv-Page-Id":         ctx["page_id"],
        "Adv-Request-Id":      str(ctx["request_id"]),
        "Adv-Session-Id":      ctx["session_id"],
        "Adv-Window-Id":       ctx["window_id"],
    }


def _update_ctx(ctx: dict, response_body: dict) -> None:
    """Update session tokens in ctx from an API response (mutates ctx)."""
    si = response_body.get("session_info", {})
    if si.get("session_id"):
        ctx["session_id"] = si["session_id"]
        ctx["page_id"]    = si["page_id"]
        ctx["csrf_token"] = si["csrf_token"]
    if response_body.get("checksum"):
        ctx["checksum"]  = response_body["checksum"]
    if response_body.get("viewState"):
        ctx["viewState"] = response_body["viewState"]


def make_session():
    """
    Launch Chrome via patchright to bypass DataDome, intercept an Advantage4
    response to capture session tokens, return (requests.Session, ctx).

    ctx keys: session_id, page_id, csrf_token, window_id, conversation_id, request_id
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "ERROR: patchright required.\n"
            "Install: pip install patchright && patchright install chromium"
        )

    captured = {}

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chrome",
        )
        page = context.new_page()

        def on_response(response):
            if BASE_URL in response.url:
                try:
                    body = response.json()
                    si = body.get("session_info", {})
                    page_key = (body.get("page_metadata") or {}).get("key", "")
                    print(f"[DEBUG] Response page_key={page_key!r}, si keys={list(si.keys())}")
                    # Capture session_id/csrf_token from any response (they're stable)
                    if si.get("session_id"):
                        for k in ("session_id", "csrf_token"):
                            if k in si:
                                captured[k] = si[k]
                    # Only capture page_id from the VVSSX10019 solicitations search page
                    if "VVSSX10019" in page_key and si.get("page_id"):
                        captured["page_id"] = si["page_id"]
                        print(f"[DEBUG] Captured page_id from VVSSX10019: {si['page_id']}")
                except Exception as exc:
                    print(f"[DEBUG] on_response error ({response.url}): {exc}")

        page.on("response", on_response)

        # Warm up profile so DataDome sees Google cookies
        for warmup in ["https://www.google.com", "https://www.bing.com"]:
            try:
                page.goto(warmup, wait_until="domcontentloaded", timeout=15_000)
                time.sleep(2)
            except Exception:
                pass

        # Navigate to portal — DataDome check runs here
        page.goto(PORTAL_URL, wait_until="networkidle", timeout=60_000)
        time.sleep(2)

        # Click into Solicitations — this triggers navigation to VVSSX10019 search page
        # Use expect_response context manager to synchronously wait for VVSSX10019 response
        def _is_vss_x10019(resp):
            if BASE_URL not in resp.url:
                return False
            try:
                body = resp.json()
                page_key = (body.get("page_metadata") or {}).get("key", "")
                return "VVSSX10019" in page_key
            except Exception:
                return False

        try:
            with page.expect_response(_is_vss_x10019, timeout=60_000) as resp_info:
                page.click("text=Solicitations", timeout=10_000)
            # Force-process the response to extract session tokens
            vss_resp = resp_info.value
            try:
                vss_body = vss_resp.json()
                si = vss_body.get("session_info", {})
                if si.get("session_id"):
                    captured.update({k: si[k] for k in si})
                    print(f"[DEBUG] Captured via expect_response: {si}")
            except Exception as e:
                print(f"[DEBUG] expect_response body parse error: {e}")
        except Exception as e:
            print(f"[DEBUG] expect_response error: {e}")
            # fall back to networkidle
            try:
                page.wait_for_load_state("networkidle", timeout=30_000)
            except Exception:
                pass
            time.sleep(3)

        print(f"[DEBUG] Final captured keys: {list(captured.keys())}")
        if not all(k in captured for k in ("session_id", "page_id", "csrf_token")):
            context.close()
            sys.exit(
                "ERROR: Could not capture IRIS VSS session tokens.\n"
                "The portal may have blocked the session. Try again."
            )

        cookies = context.cookies()
        context.close()

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c["domain"])

    ctx = {
        "session_id":      captured["session_id"],
        "page_id":         captured["page_id"],
        "csrf_token":      captured["csrf_token"],
        "window_id":       str(uuid.uuid4()),
        "conversation_id": str(random.randint(10**18, 10**19 - 1)),
        "request_id":      0,
        "checksum":        {},
        "viewState":       {},
    }
    return session, ctx


def _raw_search(session: requests.Session, ctx: dict) -> list:
    """
    POST search action for open solicitations.
    Mutates ctx with updated session_info, checksum, viewState.
    Returns raw T1SO_SRCH_QRY row_data list (unprocessed dicts).
    """
    payload = {
        "action": {
            "key":                  "vss.page.VVSSX10019.gridView1.group1.cardSearch.searchActions.search",
            "actionCode":           "search",
            "actionType":           "searchAction",
            "applicationAction":    "search",
            "backgroundAction":     "userInitiated",
            "bypassPopupClose":     False,
            "customActionName":     None,
            "dataSource":           "T1SO_SRCH_QRY",
            "dsNameList":           "T1SO_SRCH_QRY",
            "hideActionButton":     False,
            "hotkey":               "SHIFT+E",
            "isCarouselNavigation": True,
            "isEntpriseSrchCreateAction": False,
            "isShiftKey":           False,
            "name":                 "search",
            "shouldIgnoreSysFeedback": False,
            "targetLocation":       "noDisplay",
            "viewName":             "gridView1",
        },
        "checksum": {
            "VIEW":    {"gridView1": _SEARCH_VIEW_CHECKSUM},
            "DS_DATA": {"T1SO_SRCH_QRY": "-1"},
        },
        "data": {
            "ds_query_data": {"T1SO_SRCH_QRY": {"SHOW_TXT": "3"}},
            "page_data": {},
        },
        "session_info": {
            "session_id": ctx["session_id"],
            "page_id":    ctx["page_id"],
            "csrf_token": ctx["csrf_token"],
        },
        "viewState": _SEARCH_VIEWSTATE,
    }
    headers = _adv_headers(ctx, "search", "searchAction")
    resp = session.post(BASE_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    import json as _json
    print(f"[DEBUG] _raw_search response status: {resp.status_code}")
    print(f"[DEBUG] _raw_search full response (first 3000 chars):\n{_json.dumps(body)[:3000]}")
    _update_ctx(ctx, body)
    ds = body["data"]["ds_data"]["T1SO_SRCH_QRY"]
    if ds.get("rows_total", 0) > ds.get("rows_per_page", 20):
        print(
            f"WARNING: {ds['rows_total']} open solicitations, "
            f"only {ds['rows_per_page']} returned. Pagination not implemented."
        )
    return ds.get("row_data", [])


def discover_solicitations(session: requests.Session, ctx: dict) -> list:
    """Returns list of dicts with LIST_FIELDS keys. Mutates ctx."""
    raw_rows = _raw_search(session, ctx)
    return [parse_list_row(r) for r in raw_rows]


def extract_commodity_lines(response: dict) -> dict:
    """Extract commodity line fields from T3SO_DOC_COMMLN row_data."""
    rows = (
        response.get("data", {})
        .get("ds_data", {})
        .get("T3SO_DOC_COMMLN", {})
        .get("row_data", [])
    )
    descriptions, codes, specs = [], [], []
    for row in rows:
        descriptions.append(row.get("EXT_DSCR", ""))
        codes.append(row.get("COMM_CD", ""))
        specs.append(row.get("COMM_SPECS", ""))
    return {
        "commodity_descriptions": "|".join(d for d in descriptions if d),
        "commodity_codes":        "|".join(c for c in codes if c),
        "commodity_specs":        "|".join(s for s in specs if s),
    }


def fetch_detail(session: requests.Session, search_ctx: dict, raw_row: dict) -> dict:
    """
    Fetch detail fields for one solicitation via a single docTransition POST.
    The response includes both T1SO_DOC_HDR (ADDL_INFO) and T3SO_DOC_COMMLN
    (commodity lines), so no additional tab-change calls are needed.

    raw_row is the original row dict from T1SO_SRCH_QRY.row_data (not parse_list_row output).
    search_ctx is used read-only; a local copy manages token rotation within this call.
    Returns dict with keys: additional_instructions, commodity_descriptions, commodity_codes, commodity_specs.
    """
    ctx = dict(search_ctx)  # local copy — don't mutate caller's context
    ctx["request_id"] = 0

    column_value = parse_column_value(raw_row.get("DOC_REF", ""))

    dt_payload = {
        "action": {
            "key": "vss.page.VVSSX10019.gridView1.group1.cardGrid.grid1.solNumTypCat.DOC_REF.DOC_REF_Detail",
            "actionType":           "transitionAction",
            "actionCode":           "docTransition",
            "columnValue":          column_value,
            "layoutName":           "stdNoNav_Hdr3_Main101",
            "dsNameList":           "T1SO_SRCH_QRY",
            "isCarouselNavigation": True,
        },
        "checksum": {
            "VIEW":       search_ctx.get("checksum", {}).get("VIEW", {}),
            "DS_DATA":    {"T1SO_SRCH_QRY": "-1"},
            "DATASOURCE": search_ctx.get("checksum", {}).get("DATASOURCE", {}),
        },
        "viewState": search_ctx.get("viewState", {}),
        "data": {
            "ds_data": {
                "T1SO_SRCH_QRY": {
                    "row_data": [{**raw_row, "ADV_ROW_SEL": True}],
                    "current_row_id": raw_row.get("ADV_ROW_ID", ""),
                }
            },
            "page_data": {},
        },
        "session_info": {
            "session_id": search_ctx["session_id"],
            "page_id":    search_ctx["page_id"],
            "csrf_token": search_ctx["csrf_token"],
        },
    }
    time.sleep(DELAY_SECONDS)
    dt_resp = session.post(
        BASE_URL, json=dt_payload,
        headers=_adv_headers(ctx, "docTransition", "transitionAction"),
        timeout=30,
    )
    dt_resp.raise_for_status()
    dt_body = dt_resp.json()

    return {**extract_instructions(dt_body), **extract_commodity_lines(dt_body)}


def load_done_ids(output_path: str) -> set:
    if not Path(output_path).exists():
        return set()
    df = pd.read_csv(output_path, dtype=str)
    if "scrape_status" not in df.columns or "doc_ref" not in df.columns:
        return set()
    return set(df.loc[df["scrape_status"] == "success", "doc_ref"].astype(str))


def extract_instructions(response: dict) -> dict:
    """Extract ADDL_INFO from a navSolicitation tab-change response."""
    rows = (
        response.get("data", {})
        .get("ds_data", {})
        .get("T1SO_DOC_HDR", {})
        .get("row_data", [])
    )
    addl_info = rows[0].get("ADDL_INFO", "") if rows else ""
    return {"additional_instructions": addl_info}


def parse_list_row(row: dict) -> dict:
    """Extract list fields from a single T1SO_SRCH_QRY row_data entry."""
    return {
        "doc_ref":       parse_doc_ref(row.get("DOC_REF", "")),
        "doc_type":      row.get("DOC_CD_CONCAT", ""),
        "description":   row.get("DOC_DSCR", ""),
        "department":    row.get("DEPT_NM", ""),
        "buyer_name":    row.get("BUYR_NM", ""),
        "buyer_email":   row.get("BUYR_EMAIL_AD", ""),
        "buyer_phone":   row.get("BUYR_PH_NO", ""),
        "closing_dt":    ms_to_iso(row.get("SO_CLSNG_DT_TM", "")),
        "publish_dt":    ms_to_iso(row.get("PUB_DT", "")),
        "amended_dt":    ms_to_iso(row.get("AMND_DT", "")),
        "status":        row.get("SO_STA", ""),
        "category_code": row.get("SO_CAT_CD", ""),
    }


def parse_doc_ref(raw: str) -> str:
    """Extract 'RFQ-09-260000015-2' from '[RFQ,09,260000015,2][RFQ-09-260000015-2]'."""
    first_close = raw.index("]")
    second_open = raw.index("[", first_close)
    second_close = raw.index("]", second_open)
    return raw[second_open + 1:second_close]


def parse_column_value(raw: str) -> str:
    """Extract 'RFQ,09,260000015,2' from '[RFQ,09,260000015,2][...]' for docTransition."""
    first_open = raw.index("[")
    first_close = raw.index("]", first_open)
    return raw[first_open + 1:first_close]


def ms_to_iso(ms) -> str:
    """Convert millisecond epoch to ISO 8601 UTC string. Returns '' for falsy input."""
    if not ms:
        return ""
    try:
        return datetime.datetime.fromtimestamp(int(ms) / 1000, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ""


def probe():
    session, ctx = make_session()
    print("Discovering open solicitations...")
    raw_rows = _raw_search(session, ctx)
    done_ids = load_done_ids(OUTPUT_PATH)

    new_raw = [
        r for r in raw_rows
        if parse_doc_ref(r.get("DOC_REF", "")) not in done_ids
    ]
    if not new_raw:
        print("No new open solicitations to probe.")
        return

    raw_row = new_raw[0]
    doc_ref = parse_doc_ref(raw_row.get("DOC_REF", ""))
    print(f"\nProbing: {doc_ref} — {raw_row.get('DOC_DSCR', '')}")

    try:
        detail = fetch_detail(session, ctx, raw_row)
    except Exception as e:
        sys.exit(f"ERROR fetching detail: {e}")

    list_fields = parse_list_row(raw_row)
    print("\n=== List Fields ===")
    for k, v in list_fields.items():
        print(f"  {k}: {v}")
    print("\n=== Detail Fields ===")
    for k, v in detail.items():
        val = v[:300] + "..." if isinstance(v, str) and len(v) > 300 else v
        print(f"  {k}: {val}")


def run():
    session, ctx = make_session()
    print("Discovering open solicitations...")
    raw_rows = _raw_search(session, ctx)
    done_ids = load_done_ids(OUTPUT_PATH)

    to_scrape = [
        r for r in raw_rows
        if parse_doc_ref(r.get("DOC_REF", "")) not in done_ids
    ]
    total_new = len(to_scrape)
    print(f"Open: {len(raw_rows)}. Already done: {len(done_ids)}. To scrape: {total_new}")

    if total_new == 0:
        print("Nothing to do.")
        return

    enriched = []
    if Path(OUTPUT_PATH).exists():
        all_rows = pd.read_csv(OUTPUT_PATH, dtype=str).to_dict("records")
        enriched = [r for r in all_rows if r.get("scrape_status") == "success"]

    success_count = 0
    error_count = 0

    for i, raw_row in enumerate(to_scrape, 1):
        doc_ref = parse_doc_ref(raw_row.get("DOC_REF", ""))
        list_fields = parse_list_row(raw_row)
        col_val = parse_column_value(raw_row.get("DOC_REF", ""))
        alaska_url = f"{BASE_URL}?action=docTransition&columnValue={col_val}"

        print(f"[{i}/{total_new}] {doc_ref}")
        try:
            detail = fetch_detail(session, ctx, raw_row)
            detail["alaska_url"] = alaska_url
            detail["scrape_status"] = "success"
            success_count += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            detail = EMPTY_SCRAPED.copy()
            detail["alaska_url"] = alaska_url
            detail["scrape_status"] = "error"
            error_count += 1

        enriched.append({**list_fields, **detail})
        pd.DataFrame(enriched).to_csv(OUTPUT_PATH, index=False)
        time.sleep(DELAY_SECONDS)

    print(f"\nDone. {success_count} succeeded, {error_count} errored. Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
