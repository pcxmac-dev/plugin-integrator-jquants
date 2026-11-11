# Changelog

## 0.3.0 (2026-11-11)

Its API on its page (plugin API 2.2, liminal-libs 1.49.0; the user: "each plugin should reflect the the API its attached
to, and present links that provide documentation, the plugin interface should more or less contain what it already has,
BUT, it should also expose more of what the API is about"). `JQuantsPlugin.apis` declares what it talks to, read from
J-Quants' own pages on 2026-11-11 (`apis.py`): **J-Quants API V2**, with its documentation and reference, quick start,
plans and data periods, rate limits, plans' prices, the V1 migration, release notes, incidents, the dashboard, the terms
and the usage FAQ, its GitHub; every section of its reference in ten parts (equities, indices, derivatives, financials,
market data, EDINET filings, the two add-ons, bulk download, the common specifications), each said used or not; all 30
of its calls, the five it makes (the issue master and daily bars, and the scan's TOPIX, indices and futures probes)
among them. The card says JPX's terms (private use by individuals only; the data itself never shared in a viewable
form) and its prices (Free ¥0 to Premium ¥16,500 a month).

`api_facts()` says what its client learned while it ran and what its last scan showed, asking nothing: the requests
made, the last answer's clock, a key the server refused (never the key), the plan its endpoints showed (`facts.py`: the
client held weakly, its last words kept when it goes). Tests: the contract at 2.2, the card's calls the ones its source
and its scan send, the facts, and every page it names answering (only with `LIMINAL_VENDOR_PAGES=1`). On liminal-libs
1.49.0 or later; every behaviour, limit and string as in 0.2.0.

## 0.2.0 (2026-11-03)

Renamed `plugin-integrator-jquants` (the package `plugin_integrator_jquants`; it was `liminal-plugin-jquants`) on 2026-11-03: the naming by system (plugins are `plugin-<app>-<name>`), on liminal-libs 1.4.0 (`liminal_libs`, the library renamed with it).

The plugin is a class on plugin API 2.0 (the class contract, liminal-libs 1.3.0; the user: "all the plugins under
liminal should basically follow inheritance/oop paradigm"): `PLUGIN` is an instance of `JQuantsPlugin`, a
`FeedPlugin`, what it declares its class attributes (its key, `JQUANTS_PLAN` and its choices, its exchange, its
plans ...) and what it does its methods (`view`, `rate`, `build`, `has_keys`, `markets`, `scan`). It declares each
plan's publication delay itself (`delays`: `jquants-free` end of day twelve weeks late, `jquants-light`, `-standard`
and `-premium` end of day; the library's rows stay). Every fact, limit and string is as in 1.0.0. Its version is the
release's, 0.2.0, as every Liminal plugin's on `release/0.2.0`; requires liminal-libs 1.3.0.

## 1.0.0 (2026-11-02)

The first release: the Tokyo Stock Exchange's daily bars from JPX's J-Quants API (V2, `https://api.jquants.com`,
confirmed against jpx-jquants.com/en/spec on 2026-11-02; V1's token login and `/v1` paths were discontinued on
2026-06-01), with an account's API key (`JQUANTS_API_KEY`, the `x-api-key` header). One feed, `jquants`, a live
feed of one exchange abroad (plugin API 1.12, `Provider.exchanges`: XTKS), its listings stored as `7203.T` and
asked for by J-Quants' five-character code (`72030`); the bars are the server's adjusted prices and volume
(`AdjO` ... `AdjVo`: every later split, reverse split and rights issue, not dividends), one request a window
(`/v2/equities/bars/daily?code=&from=&to=`, its pages followed), each day stamped at midnight US/Eastern of its
Tokyo date; the listed issues (`/v2/equities/master`) for the directory and a listing's record. Plans by
`JQUANTS_PLAN` (free, light, standard, premium: 5, 60, 120 and 500 requests a minute; two years twelve weeks
late, five, ten and twenty years), the free plan's delay known to the library by the tier's name
(`jquants-free`); the capability scan tells the plans apart by the endpoints each adds (TOPIX from Light, the
other indices from Standard, futures on Premium) and sets `JQUANTS_PLAN` where you set none. A refused key (a
403 saying so) ends the run as a refused key does; a 429 is a rate limit, never an empty answer. Requires
liminal-libs 1.2.0.
