"""The J-Quants plugin, run against the library installed beside it: its bars read from answers shaped
like the documented ones (V2: data lists, pagination_key, adjusted items, null days), the ticker
forms, a listing's record, the directory, the refusals, a rate-limit answer, its plans and scan, and
the app loading it from this package with its own version and keeping its facts."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from importlib.metadata import version

import pytest

from liminal_lib import composite, freshness
from liminal_lib.collector import history_floor
from liminal_lib.config import load_settings
from liminal_lib.errors import NotEntitled, RateLimited, SourceError, Unauthorized
from liminal_lib.freshness import Delay
from liminal_lib.sources import feed_profiles, is_archive, markets, provider, rate_window, registry, supports
from liminal_lib.sources.archive import ET, ms
from liminal_lib.sources.registry import FeedPlugin
from liminal_lib.symbols import resolve

import liminal_plugin_jquants as jquants
from liminal_plugin_jquants import PER_DAY, PER_RUN, TIER, plan_found, plan_of, probes
from liminal_plugin_jquants.client import (API, BARS, MASTER, TSE, JQuantsClient, JQuantsSource, jquants_code, read_bars,
                                           stored_ticker)

from .conftest import FakeResponse, FakeSession

KEYS = {"JQUANTS_API_KEY": "k"}


def _source(responses, has_key=True):
    session = FakeSession(responses)
    client = JQuantsClient(API, headers={"x-api-key": "K"} if has_key else {}, session=session, sleep=lambda s: None)
    return JQuantsSource(client, has_key=has_key), session


def _row(day: str, c: float, adj: float = 1.0, factor: float = 1.0, vo: float = 1000.0):
    """A daily row as the reference shows one: unadjusted prices, the server's adjusted items (the
    unadjusted times the product of every later factor), the day's own factor on an ex-date."""
    return {"Date": day, "Code": "72030", "O": c - 10, "H": c + 20, "L": c - 20, "C": c, "UL": "0", "LL": "0",
            "Vo": vo, "Va": vo * c, "AdjFactor": factor, "AdjO": round((c - 10) * adj, 1), "AdjH": round((c + 20) * adj, 1),
            "AdjL": round((c - 20) * adj, 1), "AdjC": round(c * adj, 1), "AdjVo": round(vo / adj, 1),
            "MktCap": 1083850.0, "ExRT": "1" if factor != 1.0 else None}


NULL_DAY = {"Date": "2020-10-01", "Code": "72030", "O": None, "H": None, "L": None, "C": None, "UL": "0", "LL": "0",
            "Vo": None, "Va": None, "AdjFactor": 1.0, "AdjO": None, "AdjH": None, "AdjL": None, "AdjC": None,
            "AdjVo": None, "MktCap": None, "ExRT": None}  # the arrowhead halt: a row, no trade


def test_a_tokyo_listings_days_are_asked_by_its_code_and_read_from_the_adjusted_items():
    # Toyota's 5-for-1 split, ex-date 2021-09-28 (AdjFactor 0.2): the earlier days' adjusted items are a fifth
    page1 = {"data": [_row("2021-09-24", 10000.0, adj=0.2, vo=500.0), NULL_DAY], "pagination_key": "p.2"}
    page2 = {"data": [_row("2021-09-28", 2000.0, factor=0.2), _row("2021-09-29", 2050.0)]}
    src, session = _source([FakeResponse(200, page1), FakeResponse(200, page2)])
    bars = next(src.bar_pages("7203.T", date(2020, 9, 1), date(2021, 9, 30), "day"))
    assert [c[0] for c in session.calls] == [API + BARS] * 2  # one request, then its second page
    assert session.calls[0][1] == {"code": "72030", "from": "2020-09-01", "to": "2021-09-30"}
    assert session.calls[1][1] == {"code": "72030", "from": "2020-09-01", "to": "2021-09-30", "pagination_key": "p.2"}
    assert session.calls[0][2]["x-api-key"] == "K" and "Authorization" not in session.calls[0][2]
    assert [b["t"] for b in bars] == [ms(datetime(2021, 9, d, tzinfo=ET)) for d in (24, 28, 29)]  # the null day has no bar
    assert bars[0] == {"t": ms(datetime(2021, 9, 24, tzinfo=ET)), "o": 1998.0, "h": 2004.0, "l": 1996.0, "c": 2000.0,
                       "v": 2500.0, "vw": None, "n": None}  # a fifth of the prices, five times the shares
    assert (bars[1]["c"], bars[1]["v"]) == (2000.0, 1000.0) and bars[2]["c"] == 2050.0  # the split day is in new shares
    src, session = _source([FakeResponse(200, page2)])
    newest = next(src.bar_pages("72030", date(2021, 9, 1), date(2021, 9, 30), "day", descending=True, limit=1))
    assert [b["t"] for b in newest] == [ms(datetime(2021, 9, 29, tzinfo=ET))]
    # exact times: a day's bar is its midnight US/Eastern, and the dates asked are those days'
    src, session = _source([FakeResponse(200, page2)])
    bars = next(src.bar_pages("7203.T", datetime(2021, 9, 28, 0, 0, tzinfo=ET), datetime(2021, 9, 29, 0, 0, tzinfo=ET), "day"))
    assert [b["c"] for b in bars] == [2000.0]
    assert (session.calls[0][1]["from"], session.calls[0][1]["to"]) == ("2021-09-28", "2021-09-28")
    assert read_bars([{"Date": "bad"}, {"Date": "2021-09-29", "C": 5.0, "Vo": 2.0}]) == [
        {"t": ms(datetime(2021, 9, 29, tzinfo=ET)), "o": 5.0, "h": 5.0, "l": 5.0, "c": 5.0, "v": 2.0, "vw": None, "n": None}]
    twice = read_bars([_row("2021-09-29", 2050.0), _row("2021-09-29", 2060.0)])  # pages taken while the data changed
    assert [b["c"] for b in twice] == [2060.0]


def test_the_ticker_forms_are_j_quants_codes_and_back():
    assert jquants_code("7203.T") == "72030" and jquants_code("7203") == "72030" and jquants_code("72030") == "72030"
    assert jquants_code(" 7203.t ") == "72030"
    assert jquants_code("186A.T") == "186A0" and jquants_code("25935.T") == "25935"  # letters; a preferred share's class
    assert jquants_code("AAPL") is None and jquants_code("2330.TW") is None and jquants_code("BRK.B") is None
    assert jquants_code("7203.SS") is None and jquants_code("720301") is None
    assert stored_ticker("72030") == "7203.T" and stored_ticker("25935") == "25935.T" and stored_ticker("186A0") == "186A.T"
    assert stored_ticker("7203") == "7203.T"
    assert resolve("TSE:7203").ticker == "7203.T" and resolve("7203::XTKS").ticker == "7203.T"  # the library's forms


MASTER_ROWS = [
    {"Date": "2026-11-02", "Code": "72030", "CoName": "トヨタ自動車", "CoNameEn": "TOYOTA MOTOR CORPORATION", "S17": "7",
     "S17Nm": "自動車・輸送機", "S33": "3700", "S33Nm": "輸送用機器", "ScaleCat": "TOPIX Core30", "Mkt": "0111",
     "MktNm": "プライム", "Mrgn": "1", "MrgnNm": "信用", "ProdCat": "011"},
    {"Date": "2026-11-02", "Code": "13060", "CoName": "ＮＥＸＴ ＦＵＮＤＳ ＴＯＰＩＸ連動型上場投信", "CoNameEn": "NEXT FUNDS TOPIX ETF",
     "S17": "99", "S17Nm": "その他", "S33": "9999", "S33Nm": "その他", "ScaleCat": "-", "Mkt": "0109", "MktNm": "その他",
     "Mrgn": "1", "MrgnNm": "信用", "ProdCat": "014"},
    {"Date": "2026-11-02", "Code": "25935", "CoName": "伊藤園 第1種優先株式", "CoNameEn": "ITO EN Class 1 preferred", "S17": "1",
     "S17Nm": "食品", "S33": "3050", "S33Nm": "食料品", "ScaleCat": "-", "Mkt": "0111", "MktNm": "プライム", "Mrgn": "1",
     "MrgnNm": "信用", "ProdCat": "011"},
    {"Date": "2026-11-02", "Code": "186A0", "CoName": "アストロスケールホールディングス", "CoNameEn": "", "S17": "6",
     "S17Nm": "機械", "S33": "3600", "S33Nm": "機械", "ScaleCat": "TOPIX Small 2", "Mkt": "0113", "MktNm": "グロース",
     "Mrgn": "3", "MrgnNm": "その他", "ProdCat": "011"},
]


def test_a_listings_record_and_the_directory_come_from_the_issue_master():
    src, session = _source([FakeResponse(200, {"data": MASTER_ROWS[:1]}), FakeResponse(200, {"data": MASTER_ROWS}),
                            FakeResponse(200, {"data": []})])
    inst = src.instrument("7203.T")
    assert session.calls[0][0] == API + MASTER and session.calls[0][1] == {"code": "72030"}
    assert inst.ticker == "7203.T" and inst.name == "TOYOTA MOTOR CORPORATION" and inst.currency == "JPY" and inst.active
    assert inst.list_date is None and inst.details is MASTER_ROWS[0] and inst.kind == "stock"
    assert inst.primary_exchange.mic == "XTKS" and inst.primary_exchange.name == "Tokyo Stock Exchange"
    assert inst.primary_exchange.country.code == "JP" and inst.primary_exchange.timezone == "Asia/Tokyo"
    rows = src.listings("xtks")
    assert session.calls[1][1] == {} and len(session.calls) == 2  # one page of every issue listed today
    assert rows == [
        {"ticker": "7203.T", "name": "TOYOTA MOTOR CORPORATION", "exchange": "XTKS", "type": "CS", "figi": None, "kind": "stock"},
        {"ticker": "1306.T", "name": "NEXT FUNDS TOPIX ETF", "exchange": "XTKS", "type": "ETF", "figi": None, "kind": "stock"},
        {"ticker": "25935.T", "name": "ITO EN Class 1 preferred", "exchange": "XTKS", "type": "CS", "figi": None, "kind": "stock"},
        {"ticker": "186A.T", "name": "アストロスケールホールディングス", "exchange": "XTKS", "type": "CS", "figi": None, "kind": "stock"}]
    with pytest.raises(SourceError, match="lists no issue 99990"):
        src.instrument("9999.T")  # not listed today: an empty data list
    with pytest.raises(NotImplementedError):
        src.listings("XTAI")
    assert src.exchanges() == [TSE] and TSE.source == "jquants" and TSE.acronym == "TSE"
    assert src.covers("7203.T") and src.covers("186A") and not src.covers("AAPL")


def test_the_refusals_without_a_key_for_other_frames_other_markets_and_a_refused_key():
    keyless, session = _source([], has_key=False)
    assert not keyless.serves("stock") and keyless.resolutions("stock") == ()
    with pytest.raises(NotEntitled):
        next(keyless.bar_pages("7203.T", date(2026, 1, 5), date(2026, 1, 5), "day"))
    with pytest.raises(NotEntitled):
        keyless.instrument("7203.T")
    with pytest.raises(NotEntitled):
        keyless.listings("XTKS")
    assert session.calls == []
    src, session = _source([FakeResponse(200, {"data": []})])
    assert src.serves("stock") and src.resolutions("stock") == ("day",) and not src.serves("fx")
    with pytest.raises(NotEntitled):
        next(src.bar_pages("7203.T", date(2026, 1, 5), date(2026, 1, 5), "minute"))
    with pytest.raises(NotEntitled, match="not a Tokyo Stock Exchange listing"):
        next(src.bar_pages("AAPL", date(2026, 1, 5), date(2026, 1, 5), "day"))
    assert session.calls == []  # nothing sent for either
    assert next(src.bar_pages("7203.T", date(2026, 1, 5), date(2026, 1, 5), "day")) == []  # no match: no bars
    # a key the server does not know: a 403 saying so (V2 sends no 401) ends the run as a refused key
    src, session = _source([FakeResponse(403, {"message": "The incoming api key is invalid or expired."})])
    with pytest.raises(Unauthorized, match="JQUANTS_API_KEY"):
        next(src.bar_pages("7203.T", date(2026, 1, 5), date(2026, 1, 9), "day"))
    with pytest.raises(Unauthorized, match="nothing sent"):
        src.instrument("7203.T")
    assert len(session.calls) == 1  # the second request was not sent
    # a 403 for data outside the plan is that request's refusal only
    src, session = _source([FakeResponse(403, {"message": "This data is not included in your subscription plan."}),
                            FakeResponse(200, {"data": []})])
    with pytest.raises(NotEntitled):
        next(src.bar_pages("7203.T", date(2010, 1, 5), date(2010, 1, 9), "day"))
    assert next(src.bar_pages("7203.T", date(2026, 1, 5), date(2026, 1, 5), "day")) == [] and len(session.calls) == 2


def test_a_rate_limit_and_an_answer_without_rows_are_errors_never_empty_bars():
    too_many = [FakeResponse(429, {"message": "Too Many Requests"}) for _ in range(5)]  # no Retry-After (the reference)
    src, session = _source(too_many)
    with pytest.raises(RateLimited) as e:
        next(src.bar_pages("7203.T", date(2026, 1, 5), date(2026, 1, 9), "day"))
    assert e.value.status == 429 and e.value.retry_after is None and len(session.calls) == 5  # the library's retries
    src, _ = _source([FakeResponse(200, {"message": "This API requires at least 1 parameter as follows; date, code"})])
    with pytest.raises(SourceError, match="unexpected J-Quants answer"):
        next(src.bar_pages("7203.T", date(2026, 1, 5), date(2026, 1, 9), "day"))
    src, _ = _source([FakeResponse(200, [])])
    with pytest.raises(SourceError):
        src.listings("XTKS")
    src, _ = _source([FakeResponse(500, {"message": "Internal Server Error"}) for _ in range(5)])
    with pytest.raises(SourceError) as e:
        src.instrument("7203.T")
    assert e.value.status == 500


def test_its_plans_are_your_choice_or_its_scans_and_kept_inside_what_jpx_publishes():
    for env, plan in (({}, "free"), ({"JQUANTS_PLAN": "Light"}, "light"), ({"JQUANTS_PLAN": "standard"}, "standard"),
                      ({"JQUANTS_PLAN": "premium"}, "premium"), ({"JQUANTS_PLAN": "gold"}, "free")):
        assert plan_of(load_settings(env={**KEYS, **env}, env_file=None)) == plan  # unknown: never more than free
    published = {"free": 5, "light": 60, "standard": 120, "premium": 500}  # requests a minute (spec/rate-limits)
    for name, (tier, per_run, per_day, (n, seconds)) in jquants.PLANS.items():
        assert tier.requests_per_minute == published[name] and n <= published[name] and seconds >= 60.0
        assert n * 60 / seconds <= published[name] * 0.97 and per_run <= per_day
        assert tier.name == f"jquants-{name}" and tier.name in freshness.PLAN_DELAYS  # the library knows each by name
    assert jquants.PLANS["free"][:3] == (TIER, PER_RUN, PER_DAY) and jquants.PLANS["free"][3] == (5, 62.0)
    today = date(2026, 11, 2)
    assert history_floor(TIER, today) == today - timedelta(days=2 * 365 + 84)  # two years, and the twelve weeks' delay
    assert history_floor(jquants.PLANS["light"][0], today) == date(2021, 11, 3)
    assert history_floor(jquants.PLANS["premium"][0], today) == date(2008, 5, 7)  # twenty years: before its first day
    delay = freshness.plan_delay(TIER, "stock")
    assert delay.kind == "eod" and delay.lag == timedelta(weeks=12)  # the free plan's publication, twelve weeks late
    assert freshness.plan_delay(jquants.PLANS["light"][0], "stock").lag == timedelta(0)
    assert jquants.api_key(load_settings(env={"JQUANTS_API_KEY": " k\n"}, env_file=None)) == "k"
    assert "no account endpoint" in jquants.PLAN_NOTE


def _scanner(*answers):
    session = FakeSession(list(answers))
    return JQuantsSource(JQuantsClient(API, headers={"x-api-key": "K"}, session=session, sleep=lambda s: None), True), session


def test_its_scan_tells_the_plans_apart_by_the_endpoints_each_adds():
    asked = probes(date(2026, 11, 2))  # fifteen weeks back: Monday 2026-07-20, the week before it
    assert [(p, sorted(q)) for _, p, q in asked] == [
        ("/v2/equities/bars/daily", ["code", "from", "to"]), ("/v2/indices/bars/daily/topix", ["from", "to"]),
        ("/v2/indices/bars/daily", ["code", "from", "to"]), ("/v2/derivatives/bars/daily/futures", ["date"])]
    assert asked[0][2] == {"code": "72030", "from": "2026-07-14", "to": "2026-07-20"} and asked[3][2] == {"date": "2026-07-20"}
    served, plan = FakeResponse(200, {"data": [{"Date": "2026-07-20"}]}), FakeResponse(403, {"message": "not in your plan"})
    src, session = _scanner(served, plan, plan, plan)
    out = jquants.PLUGIN.scan(src, date(2026, 11, 2))
    assert out.plan == {"JQUANTS_PLAN": "free"} and [ok for _, ok, _ in out.results] == [True, False, False, False]
    assert len(session.calls) == 4 and session.calls[1][0].endswith("/v2/indices/bars/daily/topix")
    assert jquants.PLUGIN.scan(_scanner(served, served, plan, plan)[0], date(2026, 11, 2)).plan == {"JQUANTS_PLAN": "light"}
    assert jquants.PLUGIN.scan(_scanner(served, served, served, plan)[0], date(2026, 11, 2)).plan == {"JQUANTS_PLAN": "standard"}
    assert jquants.PLUGIN.scan(_scanner(served, served, served, served)[0], date(2026, 11, 2)).plan == {"JQUANTS_PLAN": "premium"}
    # a probe that failed otherwise tells nothing: no plan is taken on less than its endpoint answering
    broken = [FakeResponse(500, {"message": "Internal Server Error"}) for _ in range(5)]
    out = jquants.PLUGIN.scan(_scanner(served, *broken, plan, plan)[0], date(2026, 11, 2))
    assert out.plan == {} and [ok for _, ok, _ in out.results] == [True, False, False, False]
    assert plan_found({jquants.BARS_PROBE: True}) is None and plan_found({jquants.PREMIUM: True}) == "premium"
    # a refused key ends the scan at once
    src, session = _scanner(FakeResponse(403, {"message": "The incoming api key is invalid or expired."}))
    out = jquants.PLUGIN.scan(src, date(2026, 11, 2))
    assert out.plan == {} and len(out.results) == 1 and not out.results[0][1] and len(session.calls) == 1
    registry.reload()
    p = provider("jquants")
    assert p.has_scan and p.scan.__func__ is jquants.JQuantsPlugin.scan and p.plan_vars == ("JQUANTS_PLAN",)
    assert p.plan_choices == {"JQUANTS_PLAN": ("free", "light", "standard", "premium")}
    found = p.run_scan(_scanner(served, served, plan, plan)[0], load_settings(env=KEYS, env_file=None))
    assert found.plan == {"JQUANTS_PLAN": "light"} and found.results[-1][0] == "its server's rate limit"


def test_the_app_loads_it_from_this_package_with_its_own_version():
    registry.reload()
    assert jquants.PLUGIN.name == "jquants" and not hasattr(jquants, "PLUGINS")
    p = provider("jquants")
    assert p is not None, dict(registry.errors())
    assert p.origin in {"package: liminal-plugin-jquants (liminal_plugin_jquants)",
                        "plugins/liminal-plugin-jquants (liminal_plugin_jquants)"}  # its package, or its checkout in the workspace's plugin directory
    assert p.version == version("liminal-plugin-jquants") and p.api == "2.0"
    assert registry.api_refusal(p.api) is None and jquants.PLUGIN.version == ""
    assert not [why for where, why in registry.errors() if "jquants" in where or "jquants" in why]
    row = {r["name"]: r for r in registry.menu()}["jquants"]
    assert (row["version"], row["api"]) == (version("liminal-plugin-jquants"), "2.0")
    assert [k["name"] for k in row["keys"]] == ["JQUANTS_API_KEY"] and row["keys"][0]["secret"]
    assert row["planChoices"] == [{"name": "JQUANTS_PLAN", "choices": ["free", "light", "standard", "premium"]}]
    assert registry.plugin_feeds("jquants") == ["jquants"]


def test_it_keeps_its_facts(monkeypatch):
    registry.reload()
    s = load_settings(env=KEYS, env_file=None)
    view = s.for_source("jquants")
    assert (view.tier, view.max_requests_per_run, view.max_requests_per_day) == (TIER, PER_RUN, PER_DAY)
    assert rate_window("jquants", s) == (5, 62.0)
    light = load_settings(env={**KEYS, "JQUANTS_PLAN": "light"}, env_file=None)
    assert light.for_source("jquants").tier.name == "jquants-light" and rate_window("jquants", light) == (57, 62.0)
    assert light.for_source("jquants").max_requests_per_day == 6_000
    assert not is_archive("jquants") and markets("jquants", s) == {"stock": "jpx"}
    assert supports("jquants", resolve("7203.T")) and supports("jquants", resolve("TSE:7203"))
    assert not supports("jquants", resolve("AAPL")) and not supports("jquants", resolve("2330.TW"))
    assert not supports("jquants", resolve("EURUSD")) and not supports("jquants", resolve("I:VIX"))
    assert composite.feed_kind("jquants", "stock") == "official"
    p = provider("jquants")
    assert p.exchanges == {"XTKS"} and p.kind == "official" and not p.archival and p.bulk_resolution == "day"
    assert p.keys_set(s) and not p.keys_set(load_settings(env={}, env_file=None))
    assert p.request_bars("day") is None and p.resolutions_for(TIER, "stock") == ("day",)
    assert feed_profiles(s)["jquants"].assets == frozenset({"stock"}) and feed_profiles(s)["jquants"].venues == {"stock": "jpx"}
    assert feed_profiles(load_settings(env={}, env_file=None))["jquants"].assets == frozenset()  # no key: serves nothing
    assert history_floor(view.tier, date(2026, 11, 2)) == date(2024, 8, 10)
    held = []
    monkeypatch.setattr(jquants, "limiter", lambda name, st, key: held.append(("window", name, key)))
    monkeypatch.setattr(jquants, "machine_caps", lambda client, name, st, key: held.append(("day", name, key)) or client)
    source = jquants.PLUGIN.build(s, 5)
    assert held == [("window", "jquants", "k"), ("day", "jquants", "k")] and source.name == "jquants" and source.has_key
    assert source.client.request_budget == 5 and source.client._headers["x-api-key"] == "k"
    assert not jquants.PLUGIN.build(load_settings(env={}, env_file=None), 5).has_key


def test_it_is_a_class_on_plugin_api_2_0():
    """The plugin is an instance of its class (plugin API 2.0, liminal-lib 1.3.0): what it declares its class
    attributes, what it does its methods; the registry loads it as that class."""
    assert isinstance(jquants.PLUGIN, jquants.JQuantsPlugin) and isinstance(jquants.PLUGIN, FeedPlugin)
    assert jquants.PLUGIN.api == "2.0" and not jquants.PLUGIN.is_record
    p = registry.reload()["jquants"]
    assert type(p) is jquants.JQuantsPlugin and p.api == "2.0" and p.name == "jquants"
    # the hooks it gives, the rest the contract's defaults
    assert p.gives("build") and p.gives("view") and p.gives("rate") and p.gives("has_keys") and p.gives("markets")
    assert p.gives("scan") and p.has_scan and not p.gives("carries") and not p.has_settings
    # it declares each plan's publication delay itself, the library's rows for them still in place
    assert p.delays == {"jquants-free": {"stock": Delay("eod", timedelta(weeks=12))}, "jquants-light": {"stock": Delay("eod")},
                        "jquants-standard": {"stock": Delay("eod")}, "jquants-premium": {"stock": Delay("eod")}}
    assert all(p.delays[tier] == freshness.PLAN_DELAYS[tier] for tier in p.delays)
