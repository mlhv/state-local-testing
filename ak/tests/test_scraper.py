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


import tempfile, os
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

class TestLoadDoneIds:
    def test_returns_empty_set_when_no_file(self, tmp_path):
        result = scraper.load_done_ids(str(tmp_path / "missing.csv"))
        assert result == set()

    def test_returns_success_doc_refs_only(self, tmp_path):
        csv = tmp_path / "out.csv"
        csv.write_text(
            "doc_ref,scrape_status\n"
            "RFQ-09-260000015-2,success\n"
            "RFQ-09-260000016-0,error\n"
            "IFB-01-100000001-0,success\n"
        )
        result = scraper.load_done_ids(str(csv))
        assert result == {"RFQ-09-260000015-2", "IFB-01-100000001-0"}

    def test_returns_empty_set_for_missing_columns(self, tmp_path):
        csv = tmp_path / "out.csv"
        csv.write_text("col_a,col_b\nfoo,bar\n")
        result = scraper.load_done_ids(str(csv))
        assert result == set()


class TestParseListRow:
    def setup_method(self):
        with open(FIXTURES / "sample_list_response.json") as f:
            resp = json.load(f)
        self.raw_row = resp["data"]["ds_data"]["T1SO_SRCH_QRY"]["row_data"][0]

    def test_doc_ref(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["doc_ref"] == "RFQ-09-260000015-2"

    def test_doc_type(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["doc_type"] == "Request for Quotes (RFQ)"

    def test_description(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["description"] == "H21 400Hz GPU"

    def test_department(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["department"] == "Department of Military and Veterans' Affairs"

    def test_buyer_fields(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["buyer_name"] == "DAVID BAKER"
        assert row["buyer_email"] == "david.baker@alaska.gov"
        assert row["buyer_phone"] == "907-428-7220"

    def test_timestamps_converted_to_iso(self):
        row = scraper.parse_list_row(self.raw_row)
        # 1780524000000 ms = 2026-06-03T22:00:00Z (2 PM AKDT = UTC-8)
        assert row["closing_dt"] == "2026-06-03T22:00:00Z"
        # 1779436800000 ms — verify with actual conversion
        assert row["publish_dt"] == scraper.ms_to_iso(1779436800000)

    def test_status_and_category(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["status"] == "M"
        assert row["category_code"] == "145"


class TestExtractCommodityLines:
    def setup_method(self):
        with open(FIXTURES / "sample_commodity_response.json") as f:
            self.resp = json.load(f)

    def test_extracts_ext_dscr_as_descriptions(self):
        result = scraper.extract_commodity_lines(self.resp)
        assert result["commodity_descriptions"] == (
            "400Hz Dual Output Ground Power Unit|Installation and Commissioning"
        )

    def test_extracts_comm_cd_as_codes(self):
        result = scraper.extract_commodity_lines(self.resp)
        assert result["commodity_codes"] == "43211507|72150000"

    def test_extracts_comm_specs(self):
        result = scraper.extract_commodity_lines(self.resp)
        assert "90kVA per output" in result["commodity_specs"]

    def test_empty_specs_not_included_in_pipe_join(self):
        result = scraper.extract_commodity_lines(self.resp)
        # Second row has empty COMM_SPECS — should not produce trailing pipe
        assert not result["commodity_specs"].endswith("|")

    def test_empty_when_no_rows(self):
        resp = {"data": {"ds_data": {"T3SO_DOC_COMMLN": {"row_data": []}}}}
        result = scraper.extract_commodity_lines(resp)
        assert result == {
            "commodity_descriptions": "",
            "commodity_codes": "",
            "commodity_specs": "",
        }

    def test_empty_when_key_missing(self):
        result = scraper.extract_commodity_lines({})
        assert result["commodity_descriptions"] == ""


class TestExtractInstructions:
    def setup_method(self):
        with open(FIXTURES / "sample_inst_response.json") as f:
            self.resp = json.load(f)

    def test_extracts_addl_info(self):
        result = scraper.extract_instructions(self.resp)
        assert "400Hz dual output solid-state Ground Power Unit" in result["additional_instructions"]

    def test_empty_string_when_no_rows(self):
        resp = {"data": {"ds_data": {"T1SO_DOC_HDR": {"row_data": []}}}}
        result = scraper.extract_instructions(resp)
        assert result["additional_instructions"] == ""
