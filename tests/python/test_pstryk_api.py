"""Dokładne ceny z API Pstryka: adres i nagłówki, parser (strefa lokalna, doba niepełna), runtime (token, pierwszeństwo nad PSE)."""
import asyncio, sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from common import *   # noqa
import common
from homeassistant.util import dt as dt_util
from custom_components.bms_komp_dec import pstrykapi as P

TZ = ZoneInfo("Europe/Warsaw")
d = date(2026, 11, 23)

def frames(day, prices, drop=()):
    out = []
    for h in range(24):
        if h in drop:
            continue
        t = datetime(day.year, day.month, day.day, h, tzinfo=TZ).astimezone(timezone.utc)
        out.append({"start": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": "x", "price_gross": prices[h], "price_net": prices[h] / 1.23})
    return out

pr = [round(0.5 + 0.01 * h, 4) for h in range(24)]
check("adres: godzinowa rozdzielczość i okno doby w UTC", "resolution=hour" in P.day_url(d, TZ) and "window_start=2026-11-22T23%3A00%3A00Z" in P.day_url(d, TZ) and "window_end=2026-11-23T23%3A00%3A00Z" in P.day_url(d, TZ), P.day_url(d, TZ))
check("nagłówek: klucz bez prefiksu, a w drugiej próbie Bearer", P.headers(" k1 ")["Authorization"] == "k1" and P.headers("k1", True)["Authorization"] == "Bearer k1")
a = P.parse_day({"frames": frames(d, pr)}, d, TZ)
check("parser: 24 ceny w lokalnych godzinach co do grosza", a == pr, a)
check("parser: lista bez obiektu też", P.parse_day(frames(d, pr), d, TZ) == pr)
check("parser: doba niepełna (jutro przed publikacją) → None", P.parse_day({"frames": frames(d, pr, drop=range(10))}, d, TZ) is None)
check("parser: brak price_gross → None, bez zgadywania", P.parse_day({"frames": [{"start": f["start"], "price_net": 1.0} for f in frames(d, pr)]}, d, TZ) is None)
check("parser: śmieci", P.parse_day("x", d, TZ) is None and P.parse_day({"frames": [1, None]}, d, TZ) is None)
sp = date(2026, 3, 29)   # zmiana czasu: doba ma 23 godziny
chk = P.parse_day({"frames": [{"start": datetime(2026, 3, 29, h, tzinfo=TZ).astimezone(timezone.utc).isoformat(), "price_gross": 1.0} for h in range(24) if h != 2]}, sp, TZ)
check("zmiana czasu (23 h): doba nadal przyjęta", chk is not None and chk[2] is None and chk[3] == 1.0)

async def run():
    at(2026, 11, 23, 14, 5)
    hass, c, opt, rt = build(); S = hass.states
    tom = d + timedelta(days=1)
    calls = []
    served = {d: pr, tom: [round(x + 0.1, 4) for x in pr]}
    async def fake(day):
        calls.append(day); return served.get(day)
    rt._pstryk_fetch_day = fake
    async def pse(day): return None
    rt._pricefeed_fetch_day = pse
    rt.insights.buy_history = lambda t, n=14: {}
    S.set("switch.bms_price_feed", "on")
    now = dt_util.now()
    await rt.pricefeed_tick(now)
    check("bez klucza: Pstryk nie jest pytany", not calls and rt.pricefeed_payload()["token_set"] is False)
    check("ustawienie klucza", rt.pstryk_token_set("sekret") is True and rt.pricefeed_state()["token"] == "sekret")
    await rt.pricefeed_tick(now)
    pl = rt.pricefeed_payload()
    check("pobrano dziś i jutro z Pstryka", d in calls and tom in calls, calls)
    check("ceny dokładnie jak w Pstryku (dziś i jutro)", [x["price"] for x in pl["prices_today"]] == pr and [x["price"] for x in pl["prices_tomorrow"]] == served[tom], pl["prices_today"][:2])
    check("flagi: dokładne dziś i jutro, klucz ustawiony", pl["exact_today"] and pl["exact_tomorrow"] and pl["token_set"] and "Pstryka" in (pl["note"] or ""), pl["note"])
    check("klucz nie wycieka w payloadzie", "sekret" not in repr(pl))
    check("cena bieżąca = godzina 14", abs(pl["now"] - pr[14]) < 1e-9, pl["now"])
    # jutro jeszcze nieopublikowane: z kluczem NIE wyliczamy ceny z PSE
    rce_tom = [0.4] * 24
    rt.pricefeed_state()["rce"] = {d.isoformat(): [0.4] * 24, tom.isoformat(): rce_tom}
    rt.pricefeed_state()["fit"] = {"a": 1.23, "b": [0.2] * 24, "bw": None, "rmse": 0.0, "quality": "idealne", "days": 9, "pairs": 200}
    rt.pricefeed_state()["pstryk"] = {d.isoformat(): pr}
    pl = rt.pricefeed_payload()
    check("z kluczem: jutro bez ceny od Pstryka = brak cen (bez modelu z PSE)", pl["prices_tomorrow"] == [] and not pl["tomorrow_available"] and len(pl["prices_today"]) == 24, (len(pl["prices_tomorrow"]), pl["tomorrow_available"]))
    # błąd Pstryka → komunikat, bez wymyślania cen
    async def boom(day): raise RuntimeError("Pstryk odrzucił klucz API")
    rt._pstryk_fetch_day = boom; rt.pricefeed_state()["pstryk_ts"] = 0.0; rt.pricefeed_state()["pstryk"] = {}
    await rt.pricefeed_tick(now)
    pl = rt.pricefeed_payload()
    check("błąd: komunikat i brak cen", "odrzucił" in (pl["note"] or "") and not pl["exact_today"] and pl["prices_today"] == [], pl["note"])
    check("usunięcie klucza czyści dane", rt.pstryk_token_set("") is False and "token" not in rt.pricefeed_state() and not rt.pricefeed_payload()["token_set"])
    print(f"PSTRYK-API PASS={common.PASS} FAIL={common.FAIL}")
asyncio.run(run())
sys.exit(1 if common.FAIL else 0)
