from unittest.mock import AsyncMock, Mock, patch

import pytest

from dashboard.backend.collectors.edgar import (
    fetch_filing_index,
    fetch_infotable,
    fetch_ticker_title_map,
    parse_filing_index,
    parse_infotable_xml,
    parse_submissions_13f,
)


INFOTABLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer><cusip>037833100</cusip><value>123456</value>
    <shrsOrPrnAmt><sshPrnamt>1000</sshPrnamt></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>MICROSOFT CORP</nameOfIssuer><cusip>594918104</cusip><value>789</value>
    <shrsOrPrnAmt><sshPrnamt>20</sshPrnamt></shrsOrPrnAmt><putCall>Call</putCall>
  </infoTable>
  <infoTable>
    <nameOfIssuer>TESLA INC</nameOfIssuer><cusip>88160R101</cusip><value>456</value>
    <shrsOrPrnAmt><sshPrnamt>30</sshPrnamt></shrsOrPrnAmt><putCall>Put</putCall>
  </infoTable>
</informationTable>"""


def test_parse_submissions_13f_filters_form_date_and_requires_report_date():
    payload = {
        "filings": {"recent": {
            "form": ["13F-HR", "13F-HR/A", "13F-NT", "13F-HR"],
            "accessionNumber": ["a", "b", "c", "d"],
            "filingDate": ["2026-08-01", "2026-08-02", "2026-08-03", "2025-01-01"],
            "primaryDocument": ["a.xml", "b.xml", "c.xml", "d.xml"],
            "reportDate": ["2026-06-30", "2026-06-30", "2026-06-30", ""],
        }}
    }

    assert parse_submissions_13f(payload, "2026-01-01") == [
        {"accession_no": "a", "filed_at": "2026-08-01", "primary_document": "a.xml", "report_date": "2026-06-30"},
        {"accession_no": "b", "filed_at": "2026-08-02", "primary_document": "b.xml", "report_date": "2026-06-30"},
    ]


def test_parse_filing_index_prefers_information_table_then_filename_fallback():
    assert parse_filing_index({"directory": {"item": [
        {"name": "first-infotable.xml", "type": "XML"},
        {"name": "official.xml", "type": "INFORMATION TABLE"},
    ]}}) == "official.xml"
    assert parse_filing_index({"directory": {"item": [
        {"name": "primary.xml", "type": "XML"},
        {"name": "xslForm13F_X02/infotable.xml", "type": "XML"},
    ]}}) == "xslForm13F_X02/infotable.xml"


def test_parse_filing_index_raises_when_document_is_missing():
    with pytest.raises(ValueError):
        parse_filing_index({"directory": {"item": []}})


def test_parse_infotable_xml_keeps_source_value_and_put_call():
    rows = parse_infotable_xml(INFOTABLE_XML)

    assert rows == [
        {"issuer_name": "APPLE INC", "cusip": "037833100", "shares": 1000.0, "value_usd": 123456.0, "put_call": None},
        {"issuer_name": "MICROSOFT CORP", "cusip": "594918104", "shares": 20.0, "value_usd": 789.0, "put_call": "Call"},
        {"issuer_name": "TESLA INC", "cusip": "88160R101", "shares": 30.0, "value_usd": 456.0, "put_call": "Put"},
    ]


def test_parse_infotable_xml_raises_for_empty_document():
    with pytest.raises(ValueError):
        parse_infotable_xml("<informationTable />")


@pytest.mark.asyncio
async def test_fetch_helpers_use_sixty_second_timeout():
    response = Mock()
    response.json.return_value = {"directory": {"item": [{"name": "table.xml", "type": "INFORMATION TABLE"}]}}
    response.text = INFOTABLE_XML
    client = AsyncMock()
    client.get.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client

    with patch("dashboard.backend.collectors.edgar.httpx.AsyncClient", return_value=context) as factory:
        assert await fetch_filing_index(1067983, "0000000000-26-000001") == "table.xml"
        assert len(await fetch_infotable(1067983, "0000000000-26-000001", "table.xml")) == 3

    assert factory.call_count == 2
    assert all(call.kwargs["timeout"] == 60 for call in factory.call_args_list)


@pytest.mark.asyncio
async def test_fetch_ticker_title_map_returns_uppercase_tickers():
    response = Mock()
    response.json.return_value = {"0": {"ticker": "aapl", "title": "Apple Inc."}}
    client = AsyncMock()
    client.get.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client

    with patch("dashboard.backend.collectors.edgar.httpx.AsyncClient", return_value=context):
        assert await fetch_ticker_title_map() == {"AAPL": "Apple Inc."}
