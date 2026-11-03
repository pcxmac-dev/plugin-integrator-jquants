# Changelog

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
liminal-lib 1.2.0.
