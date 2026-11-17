"""SEC EDGAR Form 4 내부자 매매 수집 (무료, User-Agent 필수)."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

# SEC 요구사항: 연락 가능한 식별 UA
_EDGAR_UA = "coin-dashboard yadunghouse@gmail.com"
_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{document}"

# 장내 매수/매도 코드만 수집 — 수여(A)·세금(F) 등 잡음 제외
_OPEN_MARKET_CODES = ("P", "S")


def normalize_primary_document(document: str) -> str:
    """`xslF345X05/form4.xml` 같은 렌더러 경로에서 raw XML 파일명만 남긴다."""
    return document.rsplit("/", 1)[-1]


def parse_submissions(payload: dict, since: str) -> list[dict]:
    """submissions API 응답에서 since 이후 접수된 Form 4 목록을 추출한다 (4/A 제외)."""
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    documents = recent.get("primaryDocument", [])

    filings = []
    for form, accession, filed_at, document in zip(forms, accessions, dates, documents):
        if form != "4" or filed_at < since:
            continue
        filings.append({
            "accession_no": accession,
            "filed_at": filed_at,
            "primary_document": document,
        })
    return filings


def parse_submissions_13f(payload: dict, since: str) -> list[dict]:
    """submissions 응답에서 since 이후 13F 원본·수정본을 추출한다."""
    recent = payload.get("filings", {}).get("recent", {})
    filings = []
    for form, accession, filed_at, document, report_date in zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("filingDate", []),
        recent.get("primaryDocument", []),
        recent.get("reportDate", []),
    ):
        if form not in ("13F-HR", "13F-HR/A") or filed_at < since or not report_date:
            continue
        filings.append({
            "accession_no": accession,
            "filed_at": filed_at,
            "primary_document": document,
            "report_date": report_date,
        })
    return filings


def parse_filing_index(payload: dict) -> str:
    """filing index에서 information table XML 문서명을 찾는다.

    index.json의 type은 문서 종류가 아니라 아이콘명(text.gif)이고 파일명도 기관마다 제각각
    (46994.xml, *_holding.xml 등)이다. 13F 공시 루트의 XML은 표지(primary_doc.xml)와
    정보테이블 둘뿐이므로, primary_doc.xml이 아닌 유일한 XML을 정보테이블로 본다.
    """
    items = payload.get("directory", {}).get("item", [])
    candidates = [
        item["name"] for item in items
        if item.get("name", "").lower().endswith(".xml") and item["name"] != "primary_doc.xml"
    ]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(f"13F information table 문서를 찾을 수 없습니다 (후보: {candidates})")


def _child_text(element: ET.Element, name: str) -> str:
    child = element.find(f"{{*}}{name}")
    return (child.text or "").strip() if child is not None else ""


def parse_infotable_xml(xml_text: str) -> list[dict]:
    """13F information table XML의 원본 행을 순서대로 파싱한다."""
    root = ET.fromstring(xml_text)
    rows = []
    for row in root.findall(".//{*}infoTable"):
        amount = row.find("{*}shrsOrPrnAmt")
        shares_text = _child_text(amount, "sshPrnamt") if amount is not None else ""
        value_text = _child_text(row, "value")
        put_call = _child_text(row, "putCall") or None
        rows.append({
            "issuer_name": _child_text(row, "nameOfIssuer"),
            "cusip": _child_text(row, "cusip"),
            "shares": float(shares_text) if shares_text else None,
            # 2023-01-03 이후 제출분은 달러 단위이므로 배율을 적용하지 않는다.
            "value_usd": float(value_text) if value_text else None,
            "put_call": put_call,
        })
    if not rows:
        raise ValueError("13F information table에 보유 행이 없습니다")
    return rows


def parse_form4_xml(xml_text: str) -> dict:
    """Form 4 XML에서 보고자와 장내(P/S) 거래를 추출한다. 매도 value는 음수."""
    root = ET.fromstring(xml_text)

    insider_name = (root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or "").strip()
    relationship = root.find(".//reportingOwner/reportingOwnerRelationship")
    insider_title = None
    if relationship is not None:
        officer_title = (relationship.findtext("officerTitle") or "").strip()
        if officer_title:
            insider_title = officer_title
        elif (relationship.findtext("isDirector") or "").strip() in ("1", "true"):
            insider_title = "Director"
        elif (relationship.findtext("isTenPercentOwner") or "").strip() in ("1", "true"):
            insider_title = "10% Owner"

    transactions = []
    for tx in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
        code = (tx.findtext("transactionCoding/transactionCode") or "").strip()
        if code not in _OPEN_MARKET_CODES:
            continue
        tx_date = (tx.findtext("transactionDate/value") or "").strip()
        shares_text = tx.findtext("transactionAmounts/transactionShares/value")
        price_text = tx.findtext("transactionAmounts/transactionPricePerShare/value")
        shares = float(shares_text) if shares_text else None
        price = float(price_text) if price_text else None
        value = None
        if shares is not None and price is not None:
            value = shares * price
            if code == "S":
                value = -value
        transactions.append({
            "date": tx_date,
            "code": code,
            "shares": shares,
            "price": price,
            "value": value,
        })

    return {
        "insider_name": insider_name,
        "insider_title": insider_title,
        "transactions": transactions,
    }


async def fetch_cik_map() -> dict[str, int]:
    """티커 → CIK 매핑을 조회한다."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _EDGAR_UA}) as client:
        resp = await client.get(_TICKER_MAP_URL)
        resp.raise_for_status()
    return {entry["ticker"].upper(): int(entry["cik_str"]) for entry in resp.json().values()}


async def fetch_ticker_title_map() -> dict[str, str]:
    """티커 → EDGAR 공식 회사명 매핑을 조회한다."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _EDGAR_UA}) as client:
        resp = await client.get(_TICKER_MAP_URL)
        resp.raise_for_status()
    return {entry["ticker"].upper(): entry["title"] for entry in resp.json().values()}


async def fetch_recent_form4_filings(cik: int, since: str) -> list[dict]:
    """종목의 since 이후 Form 4 공시 목록을 조회한다."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _EDGAR_UA}) as client:
        resp = await client.get(_SUBMISSIONS_URL.format(cik=cik))
        resp.raise_for_status()
    return parse_submissions(resp.json(), since)


async def fetch_recent_13f_filings(cik: int, since: str) -> tuple[str, list[dict]]:
    """기관명과 since 이후 13F 공시 목록을 조회한다."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _EDGAR_UA}) as client:
        resp = await client.get(_SUBMISSIONS_URL.format(cik=cik))
        resp.raise_for_status()
    payload = resp.json()
    return payload.get("name", ""), parse_submissions_13f(payload, since)


async def fetch_filing_index(cik: int, accession_no: str) -> str:
    """13F filing index를 조회해 information table 문서명을 반환한다."""
    url = _ARCHIVE_URL.format(
        cik=cik,
        acc_nodash=accession_no.replace("-", ""),
        document="index.json",
    )
    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": _EDGAR_UA}) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return parse_filing_index(resp.json())


async def fetch_infotable(cik: int, accession_no: str, document: str) -> list[dict]:
    """13F information table XML을 내려받아 파싱한다."""
    url = _ARCHIVE_URL.format(
        cik=cik,
        acc_nodash=accession_no.replace("-", ""),
        document=document,
    )
    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": _EDGAR_UA}) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return parse_infotable_xml(resp.text)


async def fetch_form4(cik: int, accession_no: str, primary_document: str) -> dict:
    """Form 4 원문 XML을 받아 파싱한다."""
    url = _ARCHIVE_URL.format(
        cik=cik,
        acc_nodash=accession_no.replace("-", ""),
        document=normalize_primary_document(primary_document),
    )
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _EDGAR_UA}) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return parse_form4_xml(resp.text)
