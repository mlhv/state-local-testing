import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import scraper
import datetime


class TestParseDocRef:
    def test_extracts_human_readable_form(self):
        raw = "[RFQ,09,260000015,2][RFQ-09-260000015-2]"
        assert scraper.parse_doc_ref(raw) == "RFQ-09-260000015-2"

    def test_different_doc_type(self):
        raw = "[IFB,01,100000001,0][IFB-01-100000001-0]"
        assert scraper.parse_doc_ref(raw) == "IFB-01-100000001-0"


class TestParseColumnValue:
    def test_extracts_comma_separated_form(self):
        raw = "[RFQ,09,260000015,2][RFQ-09-260000015-2]"
        assert scraper.parse_column_value(raw) == "RFQ,09,260000015,2"


class TestMsToIso:
    def test_converts_ms_timestamp(self):
        # 1780524000000 ms = 2026-06-03T22:00:00Z
        result = scraper.ms_to_iso(1780524000000)
        assert result == "2026-06-03T22:00:00Z"

    def test_empty_string_returns_empty(self):
        assert scraper.ms_to_iso("") == ""

    def test_empty_list_default_returns_empty(self):
        assert scraper.ms_to_iso(None) == ""
