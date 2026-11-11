"""What the plugin attaches to (plugin API 2.2, liminal_libs.sources.apis): JPX's J-Quants API V2. Every address below was
read on J-Quants' own pages on 2026-11-11 (each reference page read as Markdown, `.md` appended, as its index llms.txt
offers; the plans and their prices from its home page; the rate limits, the V1 migration, the usage FAQ). Nothing is
asked to show it."""
from __future__ import annotations

from liminal_libs.sources.apis import Api, Area, Call, Link

VERIFIED = "2026-11-11"
NAME = "J-Quants API"
SPEC = "https://jpx-jquants.com/en/spec"

EQUITIES = "Equities"
INDICES = "Indices"
DERIVATIVES = "Derivatives"
FINANCIALS = "Financials"
MARKETS = "Market data"
EDINET = "EDINET filings"
MINUTES = "Add-on: minute bars and ticks"
TDNET = "Add-on: TDnet disclosures"
BULK = "Bulk download (CSV files)"
COMMON = "Common specifications"

JQUANTS = Api(
    name=NAME,
    maker="JPX Market Innovation & Research (Japan Exchange Group)",
    about=("JPX's data API for individual investors: the Tokyo Stock Exchange's listed issues and their daily bars "
           "(adjusted for splits), its indices, derivatives, companies' financial statements and dividends, and the "
           "market's statistics, as JSON pages, on a monthly plan (Free, Light, Standard, Premium) that sets how far "
           "back it serves and which of it."),
    kind="rest",
    base="https://api.jquants.com",
    version="V2, every path under /v2 (V1 and its token login were discontinued on 2026-06-01)",
    auth=("an account's API key in the x-api-key header of every request (made on the dashboard's API Keys screen; no "
          "expiry, reissued or deleted there)"),
    limits=("per account, a sliding minute: Free 5, Light 60, Standard 120, Premium 500 requests a minute; /fins/summary "
            "and /fins/details 60 a minute on every plan; the minute-bars add-on 60 and the TDnet add-on 100; a 429 "
            "comes without Retry-After and counts too (far over, about five minutes of refusals); no limit on "
            "concurrent connections. JPX's terms: private use by individuals only (no corporate use), and the data "
            "itself is never to be shared in a viewable form"),
    costs=("its plan, a month with tax: Free ¥0, Light ¥1,650, Standard ¥3,300, Premium ¥16,500; the add-ons: minute "
           "bars and ticks ¥5,500, TDnet disclosures ¥11,000; nothing a request"),
    links=(
        Link("Documentation and API reference (V2)", SPEC, "docs"),
        Link("Quick start", f"{SPEC}/quickstart", "guide"),
        Link("Plans and data periods", f"{SPEC}/data-spec", "docs"),
        Link("Rate limits", f"{SPEC}/rate-limits", "limits"),
        Link("Plans and prices", "https://jpx-jquants.com/en", "pricing"),
        Link("Migrating from V1 to V2", f"{SPEC}/migration-v1-v2", "guide"),
        Link("Release notes", f"{SPEC}/release", "changelog"),
        Link("Incidents and maintenance", "https://jpx-jquants.com/en/help/incident", "status"),
        Link("Dashboard (API keys)", "https://jpx-jquants.com/en/dashboard", "console"),
        Link("Terms and Conditions for J-Quants API Service", "https://jpx-jquants.com/en/termsofservice", "terms"),
        Link("Usage and license FAQ", "https://jpx-jquants.com/en/help/usage", "terms"),
        Link("J-Quants on GitHub (its client libraries)", "https://github.com/J-Quants", "sdk"),
        Link("Index for AI tools (llms.txt)", "https://jpx-jquants.com/llms.txt", "docs"),
    ),
    areas=(
        Area(EQUITIES, "the listed issue master, daily bars (unadjusted and adjusted), the morning session's bars "
                       "(Premium), valuation indicators, the earnings calendar, trading by type of investors",
             f"{SPEC}/eq-master",
             covered="the issue master (the directory of Tokyo listings, a listing's record) and the daily bars "
                     "(adjusted for splits; one request a listing's window)"),
        Area(INDICES, "TOPIX's daily bars (Light and up) and the other indices' (Standard and up)",
             f"{SPEC}/idx-bars-daily-topix",
             covered="the scan only: TOPIX served from Light, the other indices from Standard (it tells the plan)"),
        Area(DERIVATIVES, "futures and options daily bars (Premium), Nikkei 225 options (Standard and up)",
             f"{SPEC}/drv-bars-daily-fut",
             covered="the scan only: futures served on Premium (it tells the plan)"),
        Area(FINANCIALS, "financial summaries (EPS, forecasts), full statements (BS/PL/CF, Premium), cash dividends "
                         "(Premium), earnings announcement dates", f"{SPEC}/fin-summary"),
        Area(MARKETS, "the trading calendar, short-sale reports and ratios, margin trading outstanding, the breakdown "
                      "of trading (Premium)", f"{SPEC}/mkt-cal"),
        Area(EDINET, "major shareholders, cross-shareholdings and large volume holding reports from EDINET filings "
                     "(Standard and up)", f"{SPEC}/edinet-major-shareholders"),
        Area(MINUTES, "minute bars (API and CSV) and every trade (CSV only), two years, for ¥5,500 a month",
             f"{SPEC}/eq-bars-minute"),
        Area(TDNET, "TDnet company disclosures: the index, the files and a CSV of the index, five years, for ¥11,000 "
                    "a month", f"{SPEC}/td-list"),
        Area(BULK, "whole datasets as CSV files: the list of files and a download address for each", f"{SPEC}/bulk"),
        Area(COMMON, "pagination (pagination_key), response status codes, gzip compression, the data update schedule, "
                     "corrections", f"{SPEC}/response-status",
             covered="pages followed by pagination_key; a 403 for a key the server does not know ends the run, a 403 "
                     "for data off the plan is that request's; answers taken gzip-compressed"),
    ),
    calls=(
        Call("GET /v2/equities/master", "the listed issues of a date (all of today's without one): names, sectors, "
             "market segment, product category", EQUITIES, used="the directory of Tokyo listings, a listing's record",
             docs=f"{SPEC}/eq-master"),
        Call("GET /v2/equities/bars/daily", "an issue's (or a date's) daily bars: O, H, L, C, volume, value, the "
             "adjustment factor and the adjusted items", EQUITIES,
             used="the daily bars (the adjusted items); the scan's first probe (every plan)", docs=f"{SPEC}/eq-bars-daily"),
        Call("GET /v2/indices/bars/daily/topix", "TOPIX's daily bars", INDICES,
             used="the scan: served from Light, refused below it", docs=f"{SPEC}/idx-bars-daily-topix"),
        Call("GET /v2/indices/bars/daily", "an index's daily bars", INDICES,
             used="the scan: served from Standard", docs=f"{SPEC}/idx-bars-daily"),
        Call("GET /v2/derivatives/bars/daily/futures", "futures' daily bars of a date", DERIVATIVES,
             used="the scan: served on Premium", docs=f"{SPEC}/drv-bars-daily-fut"),
        Call("GET /v2/equities/bars/daily/am", "the morning session's bars (Premium)", EQUITIES,
             docs=f"{SPEC}/eq-bars-daily-am"),
        Call("GET /v2/equities/valuation", "valuation indicators: P/E, P/B, yields, market capitalization by day",
             EQUITIES, docs=f"{SPEC}/eq-valuation"),
        Call("GET /v2/equities/earnings-calendar", "the next earnings announcements (March and September fiscal years)",
             EQUITIES, docs=f"{SPEC}/eq-earnings-cal"),
        Call("GET /v2/equities/investor-types", "trading by type of investors, weekly (Light and up)", EQUITIES,
             docs=f"{SPEC}/eq-investor-types"),
        Call("GET /v2/derivatives/bars/daily/options", "options' daily bars (Premium)", DERIVATIVES,
             docs=f"{SPEC}/drv-bars-daily-opt"),
        Call("GET /v2/derivatives/bars/daily/options/225", "Nikkei 225 options' daily bars (Standard and up)", DERIVATIVES,
             docs=f"{SPEC}/drv-bars-daily-opt-225"),
        Call("GET /v2/fins/summary", "financial summaries of the disclosures (60 a minute on every plan)", FINANCIALS,
             docs=f"{SPEC}/fin-summary"),
        Call("GET /v2/fins/details", "balance sheets, income and cash flow statements (Premium; 60 a minute)",
             FINANCIALS, docs=f"{SPEC}/fin-details"),
        Call("GET /v2/fins/dividend", "cash dividends (Premium)", FINANCIALS, docs=f"{SPEC}/fin-dividend"),
        Call("GET /v2/fins/earnings-date", "earnings announcement dates as published", FINANCIALS,
             docs=f"{SPEC}/fin-earnings-date"),
        Call("GET /v2/markets/calendar", "the trading calendar: holidays and trading days", MARKETS, docs=f"{SPEC}/mkt-cal"),
        Call("GET /v2/markets/short-sale-report", "outstanding short positions reported", MARKETS,
             docs=f"{SPEC}/mkt-short-sale"),
        Call("GET /v2/markets/short-ratio", "short sale value and ratio by sector", MARKETS, docs=f"{SPEC}/mkt-short-ratio"),
        Call("GET /v2/markets/margin-interest", "margin trading outstanding, daily", MARKETS, docs=f"{SPEC}/mkt-margin-int"),
        Call("GET /v2/markets/margin-alert", "margin trading outstanding of issues published daily", MARKETS,
             docs=f"{SPEC}/mkt-margin-alert"),
        Call("GET /v2/markets/breakdown", "the breakdown of trading (Premium)", MARKETS, docs=f"{SPEC}/mkt-breakdown"),
        Call("GET /v2/edinet/major-shareholders", "major shareholders from the filings", EDINET,
             docs=f"{SPEC}/edinet-major-shareholders"),
        Call("GET /v2/edinet/cross-shareholdings", "cross-shareholdings from the annual reports", EDINET,
             docs=f"{SPEC}/edinet-cross-shareholdings"),
        Call("GET /v2/edinet/large-volume-shareholders", "large volume holding reports", EDINET,
             docs=f"{SPEC}/edinet-large-volume-shareholders"),
        Call("GET /v2/equities/bars/minute", "minute bars (the add-on)", MINUTES, docs=f"{SPEC}/eq-bars-minute"),
        Call("GET /v2/td/list", "the TDnet disclosures' index (the add-on)", TDNET, docs=f"{SPEC}/td-list"),
        Call("GET /v2/td/files", "a TDnet disclosure's files (the add-on)", TDNET, docs=f"{SPEC}/td-files"),
        Call("GET /v2/td/bulk", "the TDnet index as a CSV download (the add-on)", TDNET, docs=f"{SPEC}/td-bulk"),
        Call("GET /v2/bulk/list", "the downloadable CSV files", BULK, docs=f"{SPEC}/bulk-list"),
        Call("GET /v2/bulk/get", "a CSV file's download address", BULK, docs=f"{SPEC}/bulk-get"),
    ),
    verified=VERIFIED,
)

APIS = (JQUANTS,)
