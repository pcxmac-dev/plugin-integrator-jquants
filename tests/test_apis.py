"""What the plugin attaches to (plugin API 2.2): J-Quants API V2 as JPX's pages describe it, the calls it says it makes
being the ones its source and its scan really send, what its client learned said without a request (and never its
key), and (LIMINAL_VENDOR_PAGES=1 only) every page it names still answering. Nothing else is sent; no ledger or real
key is touched."""
from __future__ import annotations

import gc
import os
from datetime import date

import pytest

from liminal_libs.config import load_settings
from liminal_libs.errors import Unauthorized
from liminal_libs.sources.apis import dead_links, problems, urls

import plugin_integrator_jquants as jquants
from plugin_integrator_jquants import probes
from plugin_integrator_jquants.apis import JQUANTS, NAME
from plugin_integrator_jquants.client import API, BARS, MASTER, JQuantsClient, JQuantsSource
from plugin_integrator_jquants.facts import NOTES

from .conftest import FakeResponse, FakeSession
from .test_jquants import _row

FAKE_KEY = "fake-key-for-the-tests-0123"


@pytest.fixture(autouse=True)
def fresh_notes():
    NOTES.clear()
    yield
    NOTES.clear()


def _source(*answers) -> tuple[JQuantsSource, FakeSession]:
    session = FakeSession(list(answers))
    return JQuantsSource(JQuantsClient(API, headers={"x-api-key": FAKE_KEY}, session=session, sleep=lambda s: None), True), session


def _sent(session: FakeSession) -> set[str]:
    return {"GET " + url.removeprefix(API) for url, _, _ in session.calls}


def test_it_declares_j_quants_soundly_with_every_section_and_what_it_does_with_each():
    assert jquants.PLUGIN.apis == (JQUANTS,) and problems(jquants.PLUGIN.apis) == [] and JQUANTS.name == NAME
    assert JQUANTS.base == API and JQUANTS.docs == "https://jpx-jquants.com/en/spec"  # the card's address is the client's
    assert JQUANTS.link("limits").endswith("/rate-limits") and JQUANTS.link("pricing") and JQUANTS.link("terms")
    assert len(JQUANTS.areas) == 10 and [a.name for a in JQUANTS.covered] == ["Equities", "Indices", "Derivatives",
                                                                                "Common specifications"]
    assert len(JQUANTS.calls) == 30 and len({c.name for c in JQUANTS.calls}) == 30
    assert {c.area for c in JQUANTS.calls} <= {a.name for a in JQUANTS.areas}
    assert all(c.name.startswith("GET /v2/") for c in JQUANTS.calls) and not any(c.writes or c.costs for c in JQUANTS.calls)
    assert "500 requests a minute" in JQUANTS.limits and "¥16,500" in JQUANTS.costs and "x-api-key" in JQUANTS.auth
    assert JQUANTS.verified == "2026-11-11" and all(u.startswith("https://") for u in urls(jquants.PLUGIN.apis))


def test_the_calls_it_says_it_makes_are_the_ones_its_source_and_its_scan_send():
    rows = {"data": [_row("2026-07-20", 3000.0)]}
    master = {"data": [{"Date": "2026-11-02", "Code": "72030", "CoName": "トヨタ自動車", "CoNameEn": "TOYOTA MOTOR CORPORATION",
                        "ProdCat": "011"}]}
    src, session = _source(FakeResponse(200, rows), FakeResponse(200, master), FakeResponse(200, master))
    next(src.bar_pages("7203.T", date(2026, 7, 14), date(2026, 7, 20), "day"))
    src.instrument("7203.T")
    src.listings("XTKS")
    served = FakeResponse(200, {"data": [{"Date": "2026-07-20"}]})
    scanner, scanned = _source(served, served, served, served)
    assert jquants.PLUGIN.scan(scanner, date(2026, 11, 2)).plan == {"JQUANTS_PLAN": "premium"}
    made = _sent(session) | _sent(scanned)
    assert made == {c.name for c in JQUANTS.used}
    assert made == {"GET " + p for p in (BARS, MASTER, *(path for _, path, _ in probes(date(2026, 11, 2))))}


def test_api_facts_say_what_its_client_learned_and_never_its_key():
    assert jquants.PLUGIN.api_facts() == {}  # nothing built here yet: nothing known, nothing asked
    built = jquants.PLUGIN.build(load_settings(env={"JQUANTS_API_KEY": FAKE_KEY}, env_file=None), 5)  # no request
    assert jquants.PLUGIN.api_facts()[NAME]["Requests"] == "0 so far (of 5 allowed)" and built.client.requests_made == 0
    del built
    gc.collect()
    assert jquants.PLUGIN.api_facts()[NAME]["Run began"].endswith("(ended)")
    # a run's client as J-Quants answers it (fakes, no ledger): a refused key is said, the key never is
    src, _ = _source(FakeResponse(403, {"message": "The incoming api key is invalid or expired."}))
    NOTES.note(NAME, src.client)
    with pytest.raises(Unauthorized):
        next(src.bar_pages("7203.T", date(2026, 7, 14), date(2026, 7, 20), "day"))
    said = jquants.PLUGIN.api_facts()[NAME]
    assert said["Requests"] == "1 so far" and "invalid or expired" in said["Refused by api.jquants.com"]
    # the plan its last scan showed is kept beside what the client learned
    plan = FakeResponse(403, {"message": "not in your plan"})
    served = FakeResponse(200, {"data": [{"Date": "2026-07-20"}]})
    jquants.PLUGIN.scan(_source(served, served, plan, plan)[0], date(2026, 11, 2))
    assert jquants.PLUGIN.api_facts()[NAME]["Plan its endpoints showed"].startswith("light (scan of ")
    assert FAKE_KEY not in str(jquants.PLUGIN.api_facts())


@pytest.mark.skipif(os.environ.get("LIMINAL_VENDOR_PAGES") != "1", reason="asks JPX's pages: set LIMINAL_VENDOR_PAGES=1")
def test_every_page_it_names_answers():
    assert dead_links(jquants.PLUGIN.apis) == []
