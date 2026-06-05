import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from scraper import discover_events, extract_event_data, EMPTY_EXTRA

FIXTURES = Path(__file__).parent / "fixtures"


def _mock_list_session():
    """Session mock whose POST returns the list response fixture."""
    data = json.loads((FIXTURES / "list_response.json").read_text())
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data
    session = MagicMock()
    session.post.return_value = resp
    return session


# ── discover_events ───────────────────────────────────────────────────────────

def test_discover_events_returns_dataframe():
    df = discover_events(_mock_list_session())
    assert isinstance(df, pd.DataFrame)


def test_discover_events_row_count():
    df = discover_events(_mock_list_session())
    assert len(df) == 346


def test_discover_events_required_columns():
    df = discover_events(_mock_list_session())
    for col in ["Event ID", "Event Name", "Department Name", "End Date", "Status", "Department"]:
        assert col in df.columns, f"Missing column: {col}"


def test_discover_events_first_row_values():
    df = discover_events(_mock_list_session())
    row = df.iloc[0]
    assert row["Event ID"] == "0000039283"
    assert row["Event Name"] == "RFQ-R1-0626-01, UTV"
    assert row["Department Name"] == "Department of Fish & Wildlife"
    assert row["End Date"] == "05/06/2026 14:00 PDT"
    assert row["Status"] == "Posted"


def test_discover_events_exits_on_empty_response():
    data = {"CaptureResults": {"tbl": [{"Children": {"tblBodyTr": []}}]}}
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data
    session = MagicMock()
    session.post.return_value = resp
    with pytest.raises(SystemExit):
        discover_events(session)


# ── dept code extraction ──────────────────────────────────────────────────────

def test_dept_code_numeric():
    from scraper import _dept_from_href
    assert _dept_from_href("https://caleprocure.ca.gov/event/0250/0000038854") == "0250"


def test_dept_code_alphanumeric():
    from scraper import _dept_from_href
    assert _dept_from_href("https://caleprocure.ca.gov/event/SS100/0000012345") == "SS100"


def test_dept_code_empty_href():
    from scraper import _dept_from_href
    assert _dept_from_href("") == ""


def test_dept_code_hash_href():
    from scraper import _dept_from_href
    assert _dept_from_href("#") == ""


# ── extract_event_data new fields ─────────────────────────────────────────────

def _detail_results():
    """Minimal CaptureResults with the four new fields plus stubs for existing ones."""
    return {
        "contactName":        [{"Properties": {"text": "Roderick Bustos"}}],
        "emailAnchor":        [{"Properties": {"text": "roderick.bustos@jud.ca.gov"}}],
        "format1":            [{"Properties": {"text": "Sell Event"}}],
        "format2":            [{"Properties": {"text": "RFx"}}],
        "descriptiondetails": [],
        "unspscCodeBody":     [],
        "contractorTblBody":  [],
        "serviceAreaTblBody": [],
        "conferenceRow":      [],
        "eventVersion":       [],
        "eventStartDate":     [],
        "phoneText":          [],
    }


def test_extract_buyer_name():
    assert extract_event_data(_detail_results())["Buyer Name"] == "Roderick Bustos"


def test_extract_buyer_email():
    assert extract_event_data(_detail_results())["Buyer Email"] == "roderick.bustos@jud.ca.gov"


def test_extract_format():
    assert extract_event_data(_detail_results())["Format"] == "Sell Event"


def test_extract_type():
    assert extract_event_data(_detail_results())["Type"] == "RFx"


def test_empty_extra_has_new_keys():
    for key in ["Buyer Name", "Buyer Email", "Format", "Type"]:
        assert key in EMPTY_EXTRA, f"EMPTY_EXTRA missing key: {key}"
