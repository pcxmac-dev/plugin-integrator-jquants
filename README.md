# liminal-plugin-jquants

JPX's J-Quants for [Liminal](https://github.com/pcxmac-dev/liminal-app): the Tokyo Stock Exchange's daily
bars (open, high, low, close, volume, adjusted by JPX for splits, reverse splits and rights issues; not for
dividends) and its listed issues, from the J-Quants API (V2, `https://api.jquants.com`) with an account's API
key. One feed, `jquants`: a live feed of one exchange abroad, its listings stored under the library's names
(`7203.T` for Toyota on XTKS; `TSE:7203` and `7203::XTKS` mean the same) and asked for by J-Quants' own code
(`72030`). Daily bars only, each stamped at midnight New York of its Tokyo date like every stock's.

The free plan serves two years of history published twelve weeks late (the library knows the delay by the
plan's name and keeps asking for a day until it is published); Light, Standard and Premium serve five, ten and
twenty years the same evening. J-Quants is for individual investors only (JPX's terms): no commercial,
academic or institutional use.

A Liminal provider plugin released on its own. The app finds it through the entry point group
`liminal.providers` and lists it on the Plugins view and in `liminal plugins` as
`package: liminal-plugin-jquants`, with this package's version.

## Install

Into the app's environment, from the app's folder:

```powershell
.venv\Scripts\python.exe -m pip install "liminal-plugin-jquants @ git+https://github.com/pcxmac-dev/liminal-plugin-jquants@v0.2.0"
```

or with the app's plugins (`pip install -e ".[plugins]"` in liminal-app). The app loads it on its next start.

## The key and the plan

- `JQUANTS_API_KEY`: the key made on jpx-jquants.com's dashboard (API Keys) after registering and choosing a
  plan, the free one included. Save it from the Plugins view or with the app's `tools/set-key.ps1`; it is read
  from your user environment variables only, never written to a file, and sent to api.jquants.com alone, in the
  `x-api-key` header. (J-Quants V1's refresh token, mail address and password login was discontinued on
  2026-06-01: V2 keys do not expire.)
- `JQUANTS_PLAN`: `free` (the default), `light`, `standard` or `premium`: the requests a minute kept (5, 60, 120,
  500, a little inside) and how far back history is asked for. The API has no account endpoint, but the
  plugin's capability scan tells the plans apart by the endpoints each adds (TOPIX from Light, the other
  indices from Standard, futures on Premium) and sets the plan where you set none; set it yourself to be sure.

## Compatibility

It is written for plugin API 2.0, the class contract (`PLUGIN`, an instance of `JQuantsPlugin`, a `FeedPlugin`:
the exchanges a feed carries, `exchanges`, and its plans' publication delays, `delays`; liminal-lib 1.3.0 or
later). An app offering 2.0 or a later 2.x loads it; an app of another major leaves it out and says why on the
Plugins view.

## Develop

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install "liminal-lib @ git+https://github.com/pcxmac-dev/liminal-lib@main"
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
```

Tests never send requests (a fake session answers with bodies shaped like the documented ones) and never read
your keys.
