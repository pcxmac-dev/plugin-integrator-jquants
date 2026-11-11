"""JPX's J-Quants (jpx-jquants.com) for Liminal: the Tokyo Stock Exchange's daily bars, adjusted for
splits, with an account's API key (the free plan: two years of history published twelve weeks late;
the paid plans five, ten and twenty years, the same evening), and its listed issues for the
directory. A live feed of one exchange abroad (the plugin's `exchanges`: XTKS), its
listings stored as 7203.T and asked for by J-Quants' code, 72030 (client.jquants_code).

A Liminal plugin released on its own, registered under the entry point group `liminal.providers` as
`jquants` (PLUGIN: one feed, an instance of `JQuantsPlugin` on the class contract, plugin API 2.0,
liminal-libs 1.3.0: liminal_libs.sources.plugin.FeedPlugin; what it declares its class attributes, its
plans' publication delays among them, what it does its methods); its version is this distribution's
(pyproject.toml), so the instance's version is left empty.

Confirmed against JPX's reference on 2026-11-02 (jpx-jquants.com/en/spec; the endpoints' details in
client.py): J-Quants API V2 is the API. V1, with the plan's token login (/v1/token/auth_user for a
refresh token good a week, /v1/token/auth_refresh for a day's id token) and its /v1/prices/daily_quotes
and /v1/listed/info, was discontinued on 2026-06-01, and accounts made since 2025-12-22 never had it:
so the key is one variable, JQUANTS_API_KEY (made on the dashboard's API Keys screen, no expiry, sent
in the x-api-key header), not a refresh token with a mail address and password to renew it (the plan's
JQUANTS_REFRESH_TOKEN, JQUANTS_MAIL and JQUANTS_PASSWORD have nothing to do now and are not declared).
Plans (spec/data-spec, spec/rate-limits, 2026-11-02): Free, 5 requests a minute, two years of history
published twelve weeks late; Light, 60 a minute, five years; Standard, 120 a minute, ten years;
Premium, 500 a minute, twenty years (unlimited on V1). Prices and listings from 2008-05-07. Requests
are counted per account (more keys give no more); there is no daily cap and no cap on concurrent
requests. A 429 comes without Retry-After (a sliding minute: the library's retries back off, and the
window kept here stays inside the plan's). JPX's terms: individual investors only.

The plan is JQUANTS_PLAN's (free, the default: never more than the user says or the scan finds). The
API has no account endpoint, but its scan (`capabilities`, four requests) tells the plans apart by the
endpoints each adds (TOPIX from Light, the other indices from Standard, futures on Premium) and answers
with the plan that shows, which the app applies where the user set none (Scanned.plan).

Plugin API 2.2 (liminal-libs 1.49.0; the user, 2026-11-11: "each plugin should reflect the the API its attached to, and
present links that provide documentation"): `apis`, what it talks to (apis.py: J-Quants API V2 with JPX's pages, its
plans' prices and limits, every section of its reference and the calls it makes among the rest), and `api_facts()`,
what its client learned while it ran and the plan its last scan showed (facts.py), asking nothing."""
from __future__ import annotations

import time
from dataclasses import replace
from datetime import date, timedelta

from liminal_libs.config import Tier
from liminal_libs.errors import NotEntitled, SourceError, Unauthorized
from liminal_libs.freshness import Delay
from liminal_libs.sources.registry import FeedPlugin, KeyVar, Scanned, limiter, machine_caps
from .apis import APIS
from .apis import NAME as API_NAME
from .client import API, BARS, MIC, JQuantsClient, JQuantsSource
from .facts import NOTES, when

NAME = "jquants"
KEY = "JQUANTS_API_KEY"  # an account's key from jpx-jquants.com's dashboard, a user environment variable
PLAN = "JQUANTS_PLAN"
START = date(2008, 5, 7)  # J-Quants' first day of prices and listings (spec/data-spec)
DELAY_WEEKS = 12  # the free plan publishes a day this much later (freshness.PLAN_DELAYS["jquants-free"])
# Each plan (spec/data-spec and spec/rate-limits, 2026-11-02): (its tier, named as the library's
# PLAN_DELAYS knows it; requests a run; requests a day; the window the limiter keeps, a little inside
# the plan's requests a minute, 62 seconds for the server's sliding minute). The free plan's history
# runs from two years and twelve weeks ago to twelve weeks ago, so its floor is set in days; the
# others' in years. No daily cap is published: the caps here keep a run short on an hourly sync.
PLANS = {
    "free": (Tier("jquants-free", requests_per_minute=5, history_years=None, history_start=START,
                  history_days=2 * 365 + 7 * DELAY_WEEKS), 100, 1_000, (5, 62.0)),
    "light": (Tier("jquants-light", requests_per_minute=60, history_years=5, history_start=START), 600, 6_000, (57, 62.0)),
    "standard": (Tier("jquants-standard", requests_per_minute=120, history_years=10, history_start=START),
                 1_200, 12_000, (114, 62.0)),
    "premium": (Tier("jquants-premium", requests_per_minute=500, history_years=20, history_start=START),
                3_000, 30_000, (475, 62.0)),
}
TIER, PER_RUN, PER_DAY = PLANS["free"][:3]
PLAN_NOTE = ("J-Quants' API has no account endpoint, so a key's plan is not told directly. Its scan tells the plans "
             "apart by the endpoints each adds (TOPIX from Light, the other indices from Standard, futures on "
             "Premium) and sets JQUANTS_PLAN where you set none; set it yourself to be sure")

# the scan's probes: a busy issue's week (Toyota, listed throughout), then the endpoint each paid plan adds
PROBE_CODE = "72030"
BARS_PROBE = "stock daily bars (every plan)"
LIGHT = "TOPIX daily bars (Light and up)"
STANDARD = "the other indices' daily bars (Standard and up)"
PREMIUM = "futures' daily bars (Premium)"


def api_key(settings) -> str | None:
    """The J-Quants key among the settings' plugin variables (Settings.env), spaces around it taken
    off (one pasted with a line break would make every request fail), or None."""
    return (settings.env.get(KEY) or "").strip() or None


def plan_of(settings) -> str:
    """JQUANTS_PLAN's plan (an unknown value: free, the lowest limits, never more)."""
    name = (settings.env.get(PLAN) or "free").strip().lower()
    return name if name in PLANS else "free"


def probes(today: date) -> list[tuple[str, str, dict]]:
    """(what, path, params) of the scan: a week of a busy issue's days ending fifteen weeks back (a
    weekday; inside every plan's window: the free plan's ends twelve weeks ago), then the endpoint
    each paid plan adds (spec/data-spec), the same week (the futures' endpoint takes one date)."""
    end = today - timedelta(weeks=15)
    while end.weekday() >= 5:
        end -= timedelta(days=1)
    week = {"from": (end - timedelta(days=6)).isoformat(), "to": end.isoformat()}
    return [
        (BARS_PROBE, BARS, {"code": PROBE_CODE, **week}),
        (LIGHT, "/v2/indices/bars/daily/topix", dict(week)),
        (STANDARD, "/v2/indices/bars/daily", {"code": "0000", **week}),  # 0000: TOPIX's code at that endpoint
        (PREMIUM, "/v2/derivatives/bars/daily/futures", {"date": end.isoformat()}),
    ]


def plan_found(served: dict[str, bool]) -> str | None:
    """The plan the scan's answers show, or None when they do not settle it. Each probe is served
    (True) or refused by the plan (False, a 403); from the top: futures served, Premium; else the
    indices, Standard; else TOPIX, Light; else the bars served and TOPIX refused, Free. A probe that
    failed otherwise (a timeout, a server error) is neither, and nothing is taken from it."""
    if served.get(PREMIUM):
        return "premium"
    if served.get(STANDARD):
        return "standard"
    if served.get(LIGHT):
        return "light"
    if served.get(BARS_PROBE) and served.get(LIGHT) is False:
        return "free"
    return None


class JQuantsPlugin(FeedPlugin):
    """The feed as a class (plugin API 2.2): what it declares its class attributes (its key, its plans and
    their publication delays, its exchange, what it attaches to), what it does its methods (`view`:
    JQUANTS_PLAN's plan; `rate`: the plan's window; `build`: its source on a keyed client; `has_keys`,
    `markets`; `scan`: the plan the endpoints show; `api_facts`), the rest the contract's defaults."""

    api = "2.2"  # the contract it needs (the class contract: exchanges, a listing abroad comes to it and to no US feed; delays; 2.2: apis)
    name = NAME
    title = "J-Quants"
    assets = frozenset({"stock"})
    order = 120
    about = "Tokyo Stock Exchange daily bars from JPX's J-Quants API (an account's key; free: two years, twelve weeks late)"
    keys = (KeyVar(KEY, label="API key", hint="the key made on jpx-jquants.com's dashboard (API Keys), on a Free, Light, "
                                               "Standard or Premium plan"),)
    signup = "jpx-jquants.com: a free account's API key (the dashboard's API Keys screen)"
    exchanges = frozenset({MIC})  # the Tokyo Stock Exchange's listings (7203.T), and nothing else
    kind = "official"
    archival = False
    tier = TIER
    per_run, per_day = PER_RUN, PER_DAY
    limits = ("Free: 5 requests a minute, two years of history published twelve weeks late; Light: 60 a minute, five "
              "years; Standard: 120 a minute, ten years; Premium: 500 a minute, twenty years (counted per account; no "
              "daily cap published)")
    plan_vars = (PLAN,)
    plan_choices = {PLAN: tuple(PLANS)}
    plan_note = PLAN_NOTE
    provides = {"stock": ("day",)}
    per_request = {"day": None}  # one request: the days asked for, the plan's whole history
    missing_keys_note = "key not set: JPX's J-Quants needs JQUANTS_API_KEY (a free account at jpx-jquants.com)"
    bulk_resolution = "day"
    # when each plan's data is published (the library's freshness.PLAN_DELAYS rows for jquants-free, -light,
    # -standard and -premium, declared here too): end of day, the free plan's twelve weeks late (DELAY_WEEKS)
    delays = {"jquants-free": {"stock": Delay("eod", timedelta(weeks=DELAY_WEEKS))},
              "jquants-light": {"stock": Delay("eod")}, "jquants-standard": {"stock": Delay("eod")},
              "jquants-premium": {"stock": Delay("eod")}}
    # what it attaches to (plugin API 2.2): J-Quants API V2, with JPX's pages (apis.py)
    apis = APIS

    def view(self, base):
        """The settings as this feed sees them: its plan's tier (history, requests a minute) and caps."""
        tier, per_run, per_day, _ = PLANS[plan_of(base)]
        return replace(base, tier=tier, max_requests_per_run=per_run, max_requests_per_day=per_day, origin=base)

    def rate(self, settings):
        return PLANS[plan_of(settings)][3]

    def has_keys(self, settings):
        return bool(api_key(settings))

    def markets(self, settings):
        return {"stock": "jpx"}

    def build(self, settings, request_budget):
        key = api_key(settings)
        client = JQuantsClient(API, headers={"x-api-key": key} if key else {}, request_budget=request_budget,
                               rate_limiter=limiter(self.name, settings, key))
        NOTES.note(API_NAME, client)  # held weakly: api_facts reads what it learned (never its key)
        return JQuantsSource(machine_caps(client, self.name, settings, key), has_key=bool(key))

    def api_facts(self):
        """What its client learned of J-Quants while it ran (the requests made, the last answer's clock, a key the
        server refused) and the plan its last scan showed, from what this process already holds: nothing is asked
        (facts.py). The key itself is never said."""
        return NOTES.facts(a.name for a in self.apis)

    def scan(self, source, today: date | None = None) -> Scanned:
        """Each probe once, in order: served (rows in a 200), refused by the plan (a 403: below it), or
        failed otherwise (nothing told). A refused key (Unauthorized) ends the scan at once, every request
        being refused alike, and no plan is told; a plan is never taken on less than its endpoint answering."""
        out, served = [], {}
        for what, path, params in probes(today or date.today()):
            try:
                answer = source.client.get(path, params)
            except Unauthorized as e:
                out.append((what, False, str(e)[:200]))
                break
            except NotEntitled as e:
                out.append((what, False, f"not on this plan ({str(e)[:120]})"))
                served[what] = False
                continue
            except SourceError as e:
                out.append((what, False, str(e)[:200]))
                continue
            rows = answer.get("data") if isinstance(answer, dict) else None
            if not isinstance(rows, list):
                out.append((what, False, f"answered without rows ({str(answer)[:120]}): nothing told"))
                continue
            served[what] = True
            out.append((what, True, f"{len(rows):,} rows to {params.get('to') or params.get('date')}"))
        plan = plan_found(served)
        NOTES.keep(API_NAME, {"Plan its endpoints showed": f"{plan or 'not settled'} (scan of {when(time.time())})"})
        return Scanned(tuple(out), {PLAN: plan} if plan else {})


PLUGIN = JQuantsPlugin()
