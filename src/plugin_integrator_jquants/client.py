"""J-Quants' client and source (api.jquants.com, API V2): the Tokyo Stock Exchange's daily bars and
its listed issues, with an account's API key on the library's client.

Confirmed against JPX's current reference on 2026-11-02 (jpx-jquants.com/en/spec, each page read as
Markdown with `.md` appended): the base URL is https://api.jquants.com with every path under /v2 and
the key in the x-api-key header of each request. The plan's V1 paths (/v1/token/auth_user,
/v1/token/auth_refresh, /v1/prices/daily_quotes, /v1/listed/info) and the token login were
discontinued on 2026-06-01 (accounts made since 2025-12-22 never had them; spec/migration-v1-v2), so
this plugin speaks V2 only:
- GET /v2/equities/bars/daily?code=&from=&to= (either code or date is required; dates as YYYY-MM-DD or
  YYYYMMDD; the code 5 characters, 72030, or 4, 7203, the common stock) answers {"data": [rows],
  "pagination_key": "..."}, the key only while more pages follow (a page is about 5 MB). A row: Date,
  Code, O, H, L, C (unadjusted, yen), UL, LL, Vo (shares; units for ETFs and REITs), Va, AdjFactor
  (0.5 on a two-for-one split's ex-date), AdjO, AdjH, AdjL, AdjC, AdjVo (the server's adjustment for
  every later split, reverse split and rights issue, rounded to one decimal; dividends are not
  adjusted), MktCap, ExRT, and on the Premium plan the morning and afternoon session items (MO ...
  AAdjVo; the keys are absent on the other plans). A day without a trade (a halt, no execution)
  keeps its row with the four prices, Vo and Va all null, never 0. Published around 16:30 Tokyo.
- GET /v2/equities/master?code=&date= (both optional: without them every issue listed today) answers
  rows of Date, Code, CoName, CoNameEn, S17, S17Nm, S33, S33Nm, ScaleCat, Mkt, MktNm, Mrgn, MrgnNm,
  ProdCat (011 domestic stocks, preferred shares among them; 012 preferred equity investment
  certificates; 013 REITs; 014 ETFs; 021 foreign stocks; 022 foreign REITs; 023 foreign ETFs; 024
  depositary receipts). Listing and delisting dates are not given. No match: an empty data list.
- Errors (spec/response-status): 400 bad parameters; 403 for a key the server does not know ("The
  incoming api key is invalid or expired.") and for data or endpoints outside the plan; 429 over the
  plan's requests a minute (a sliding minute, no Retry-After; about five minutes of refusals when
  far over it, the refused requests counted too); 500. An error body carries a "message" (not always).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Iterator

from liminal_libs.errors import NotEntitled, SourceError, Unauthorized
from liminal_libs.models import Exchange, Instrument, Stock, country, exchange_name, listing_ticker, suffix_mic
from liminal_libs.sources.archive import ET, Archive as _Archive, bounds as _bounds, ms as _ms
from liminal_libs.sources.http import PublicClient

API = "https://api.jquants.com"  # every path under /v2 (V1 was discontinued on 2026-06-01)
BARS = "/v2/equities/bars/daily"
MASTER = "/v2/equities/master"
MIC = "XTKS"  # the one exchange J-Quants covers: issues listed on the Tokyo Stock Exchange
TSE = Exchange("jquants", 1, exchange_name(MIC) or "Tokyo Stock Exchange", country("JP"), mic=MIC, acronym="TSE",
               type="exchange")
KEY_REFUSED = "api key is invalid or expired"  # the 403's message for a key the server does not know
# J-Quants' product categories (spec/eq-master/product-category) as the directory's listing types
KINDS = {"011": "CS", "012": "PFD", "013": "CS", "014": "ETF", "021": "CS", "022": "CS", "023": "ETF", "024": "ADRC"}
# A Tokyo code: four characters, a digit first (7203; 186A: letters since 2024), with J-Quants' fifth
# character (72030: 0 for the common stock; 25935: another class of the same issue)
_CODE = re.compile(r"^\d[0-9A-Z]{3}\d?$")


def jquants_code(ticker: str) -> str | None:
    """J-Quants' five-character code of a stored Tokyo listing: 72030 for 7203.T (the four-character
    code with the common stock's trailing 0, the only form the four-character query also means),
    25935 for 25935.T (a share class of its own, stored with its fifth character), a bare code (7203,
    72030) the same way; None for a name that is no Tokyo listing (AAPL, 2330.TW, BRK.B)."""
    t = ticker.strip().upper()
    base, dot, tail = t.rpartition(".")
    if base and dot:
        if suffix_mic(tail) != MIC:
            return None
        t = base
    if not _CODE.match(t):
        return None
    return t if len(t) == 5 else t + "0"


def stored_ticker(code: str) -> str:
    """The stored name of a J-Quants code (models.listing_ticker): 7203.T for 72030 (the common
    stock's trailing 0 taken off), 25935.T for a code whose fifth character is not 0."""
    c = str(code).strip().upper()
    if len(c) == 5 and c.endswith("0"):
        c = c[:4]
    return listing_ticker(c, MIC)


PRICES = (("o", "AdjO", "O"), ("h", "AdjH", "H"), ("l", "AdjL", "L"), ("c", "AdjC", "C"))


def read_bars(rows: list[dict]) -> list[dict]:
    """J-Quants' daily rows (any order, pages together) as the library's day bars, oldest first: the
    server's adjusted prices and volume (AdjO, AdjH, AdjL, AdjC, AdjVo: every later split, reverse
    split and rights issue applied to each day, the way the Tiingo plugin applies Tiingo's split
    factors; dividends adjusted by neither), each stamped at midnight US/Eastern of its Tokyo trading
    date (the library's rule for a listing abroad). A day without a trade (its prices null) has no
    bar; a row without the adjusted items is read unadjusted; a date given twice (pages taken while
    the data changed) keeps the later row."""
    by_day: dict[int, dict] = {}
    for r in rows:
        try:
            d = date.fromisoformat(str(r.get("Date") or "")[:10])
        except ValueError:
            continue
        p = {}
        for k, adj, raw in PRICES:
            v = r.get(adj)
            v = r.get(raw) if v is None else v
            p[k] = float(v) if v is not None else None
        if p["c"] is None:
            continue  # no execution that day: the four prices, Vo and Va are null together
        for k in ("o", "h", "l"):
            if p[k] is None:
                p[k] = p["c"]
        v = r.get("AdjVo")
        v = r.get("Vo") if v is None else v
        t = _ms(datetime(d.year, d.month, d.day, tzinfo=ET))
        by_day[t] = {"t": t, **p, "v": float(v) if v is not None else None, "vw": None, "n": None}
    return [by_day[t] for t in sorted(by_day)]


class JQuantsClient(PublicClient):
    """The library's client (its window, caps, retries; a redirect elsewhere not followed) with
    J-Quants' ways: the key in every request's x-api-key header (given at build), its pages followed
    (rows), and its refusal of a key read as one. J-Quants answers 403 where the library expects 401
    for a key it does not know, so that 403 ends the run and the feed's fetching as a refused key does
    (Unauthorized; nothing more is sent to the host this run, as the library keeps a 401), while a 403
    for data or an endpoint outside the plan stays the NotEntitled of that one request."""

    def get(self, path_or_url: str, params: dict | None = None) -> dict:
        try:
            return super().get(path_or_url, params)
        except NotEntitled as e:
            if e.status == 403 and KEY_REFUSED in (e.message or "").lower():
                refused = Unauthorized(403, f"{e.message} (JQUANTS_API_KEY: a key made on jpx-jquants.com's dashboard, "
                                            "set on the Plugins view)")
                self._refused[self._host] = refused  # every request would be refused alike: none more this run
                raise refused from None
            raise

    def rows(self, path: str, params: dict | None = None) -> list[dict]:
        """Every row of an answer, its pages followed (pagination_key: one more request each). An
        answer without a data list (a message in a 200, another shape) is an error of this request,
        never an empty answer: an empty answer reads as no data, and the span would count as done."""
        params = dict(params or {})
        out: list[dict] = []
        while True:
            answer = self.get(path, dict(params))  # its own copy each page: the request records what was sent
            data = answer.get("data") if isinstance(answer, dict) else None
            if not isinstance(data, list):
                raise SourceError(0, f"unexpected J-Quants answer at {path}: {str(answer)[:120]}")
            out += [r for r in data if isinstance(r, dict)]
            key = answer.get("pagination_key")
            if not key:
                return out
            params["pagination_key"] = str(key)


class JQuantsSource(_Archive):
    """The Tokyo Stock Exchange's daily bars from J-Quants, one request a window of one issue's days
    (from, to: the plan's whole history fits one page), and its listed issues: the directory of the
    exchange, and a listing's record (its names; J-Quants gives no listing date). Live: each Tokyo
    day's bars come as JPX publishes them (the same evening; twelve weeks later on the free plan,
    which the library knows by the plan's name)."""

    name = "jquants"
    assets = ("stock",)
    archival = False  # a live feed: new days keep coming

    def __init__(self, client: PublicClient, has_key: bool):
        super().__init__(client)
        self.has_key = has_key

    def serves(self, asset: str) -> bool:
        return asset == "stock" and self.has_key

    def resolutions(self, asset: str) -> tuple[str, ...]:
        return ("day",) if self.serves(asset) else ()

    def covers(self, ticker: str) -> bool:
        return jquants_code(ticker) is not None

    def exchanges(self) -> list[Exchange]:
        return [TSE]

    def _need_key(self) -> None:
        if not self.has_key:
            raise NotEntitled(401, "JQUANTS_API_KEY not set; nothing sent")

    @staticmethod
    def _code(ticker: str) -> str:
        code = jquants_code(ticker)
        if code is None:
            raise NotEntitled(0, f"{ticker} is not a Tokyo Stock Exchange listing (7203.T): J-Quants has no bars for it")
        return code

    def instrument(self, ticker: str, resolve_exchange: bool = True) -> Instrument:
        """A listing's record from the issue master (one request): its English name (its Japanese one
        when there is no other), the exchange, and J-Quants' row as the details; no listing date
        (J-Quants gives none). An issue not listed today is an error (404), not a record."""
        self._need_key()
        code = self._code(ticker)
        rows = self.client.rows(MASTER, {"code": code})
        row = next((r for r in rows if str(r.get("Code") or "").strip().upper() == code), rows[0] if rows else None)
        if row is None:
            raise SourceError(404, f"J-Quants lists no issue {code} ({ticker}) today")
        name = (row.get("CoNameEn") or row.get("CoName") or "").strip() or None
        return Stock(ticker=stored_ticker(code), name=name, primary_exchange=TSE, currency="JPY", list_date=None,
                     details=row)

    def listings(self, exchange: str) -> list[dict]:
        """Every issue listed on the Tokyo Stock Exchange today (one request, a page of about 4,000
        rows), under their stored names (7203.T), typed by J-Quants' product category (KINDS). Any
        other exchange is not this feed's."""
        mic = exchange.strip().upper()
        if mic != MIC:
            raise NotImplementedError(f"jquants lists the Tokyo Stock Exchange ({MIC}) only, not {mic}")
        self._need_key()
        out = []
        for r in self.client.rows(MASTER):
            code = str(r.get("Code") or "").strip().upper()
            if not _CODE.match(code):
                continue
            name = (r.get("CoNameEn") or r.get("CoName") or "").strip() or None
            out.append({"ticker": stored_ticker(code), "name": name, "exchange": MIC,
                        "type": KINDS.get(str(r.get("ProdCat") or ""), "CS"), "figi": None, "kind": "stock"})
        return out

    @staticmethod
    def _dates(start, end) -> tuple[date, date]:
        """The Tokyo trading dates to ask for, from dates (whole days, the end inclusive) or exact
        times (their US/Eastern dates: a day bar's stamp is midnight US/Eastern of its Tokyo date)."""
        first = start.astimezone(ET).date() if isinstance(start, datetime) else start
        last = (end - timedelta(milliseconds=1)).astimezone(ET).date() if isinstance(end, datetime) else end
        return first, last

    def bar_pages(self, ticker, start, end, timespan, multiplier=1, descending=False, asset="stock",
                  limit: int | None = None) -> Iterator[list[dict]]:
        self._need_key()
        if timespan != "day":
            raise NotEntitled(0, "J-Quants serves daily bars here")
        code = self._code(ticker)
        first, last = self._dates(start, end)
        a, b = _bounds(start, end, ET)
        rows = self.client.rows(BARS, {"code": code, "from": first.isoformat(), "to": last.isoformat()})
        bars = [x for x in read_bars(rows) if a <= x["t"] < b]
        bars.sort(key=lambda x: -x["t"] if descending else x["t"])
        yield bars[:limit] if limit else bars
