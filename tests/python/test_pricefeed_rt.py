"""Własne ceny z PSE w runtime: pobranie (zamockowane), uczenie z prawdziwych cen zakupu, sensor z cenami na jutro."""
import asyncio, sys, math
from common import *   # noqa
import common
from datetime import date, timedelta
from homeassistant.util import dt as dt_util
from custom_components.bms_komp_dec.const import CONF_PRICE_BUY_ENTITY
from custom_components.bms_komp_dec import pricefeed as pf


async def run():
    at(2026, 11, 23, 14, 5)
    hass, c, opt, rt = build(); S = hass.states
    today, tom = date(2026, 11, 23), date(2026, 11, 24)
    shape = lambda i: [round(0.3 + 0.2 * math.sin(i + h / 3.0), 4) for h in range(24)]
    served = {(today - timedelta(days=i)): shape(i) for i in range(-1, 15)}
    calls = []

    async def fake(d):
        calls.append(d)
        return served.get(d)
    rt._pricefeed_fetch_day = fake
    # prawdziwe ceny zakupu z ostatnich dób = 1,23 × RCE + opłata strefowa
    rt.insights.buy_history = lambda t, n=14: {(today - timedelta(days=i)).isoformat():
        [round(1.23 * shape(i)[h] + (0.40 if 6 <= h < 22 else 0.15), 4) for h in range(24)] for i in range(1, 15)}
    now = dt_util.now()

    S.set("switch.bms_price_feed", "off")
    await rt.pricefeed_tick(now)
    check("wyłączone: nic nie pobiera", not calls and rt.pricefeed_payload()["enabled"] is False and rt.pricefeed_payload()["now"] is None)

    S.set("switch.bms_price_feed", "on")
    for k in range(8):
        rt.pricefeed_state()["fetched_ts"] = 0.0
        await rt.pricefeed_tick(now)
    pl = rt.pricefeed_payload()
    check("pobrano dziś, jutro i historię", today in calls and tom in calls and len(set(calls)) >= 15, sorted(set(calls))[:3])
    check("dopasowanie z prawdziwych cen: mnożnik 1,23, jakość „dobre”", pl["fit"] and abs(pl["fit"]["a"] - 1.23) < 0.01 and pl["fit"]["quality"] == "dobre", pl["fit"])
    check("sensor: 24 ceny na dziś i na jutro, jutro dostępne", len(pl["prices_today"]) == 24 and len(pl["prices_tomorrow"]) == 24 and pl["tomorrow_available"], (len(pl["prices_today"]), len(pl["prices_tomorrow"])))
    exp = 1.23 * shape(-1)[10] + 0.40
    got = [x["price"] for x in pl["prices_tomorrow"]][10]
    check("cena jutro 10:00 = 1,23 × RCE + 0,40", abs(got - exp) < 0.02, (got, exp))
    check("stan sensora = cena bieżącej godziny", pl["now"] is not None and abs(pl["now"] - [x["price"] for x in pl["prices_today"]][14]) < 1e-9, pl["now"])
    check("znaczniki czasu z przesunięciem strefy", pl["prices_tomorrow"][0]["start"].startswith("2026-11-24T00:00:00+01:00"), pl["prices_tomorrow"][0])

    # czytnik cen planera rozumie atrybuty sensora (po wskazaniu go jako cenę zakupu)
    S.set(rt.PRICEFEED_ENTITY, pl["now"], {"prices_today": pl["prices_today"], "prices_tomorrow": pl["prices_tomorrow"]})
    cfg = dict(const.SCHEDULER_DEFAULTS); cfg[CONF_PRICE_BUY_ENTITY] = rt.PRICEFEED_ENTITY
    sch = scheduler.ScheduleOptimizer(hass, c, cfg)
    rt.optimizer = sch
    a, b = sch.buy_hourly_for(today), sch.buy_hourly_for(tom)
    check("planer czyta 24 ceny na dziś i jutro z sensora", a and b and sum(v is not None for v in a) == 24 and sum(v is not None for v in b) == 24, (a, b))
    check("…i są to te same ceny", abs(b[10] - got) < 1e-3, (b[10], got))

    # gdy własny sensor jest źródłem zakupu, uczenie się zatrzymuje (nie uczymy się z własnej prognozy)
    fit_before = dict(rt.pricefeed_state()["fit"])
    rt.insights.buy_history = lambda t, n=14: {(today - timedelta(days=i)).isoformat(): [9.9] * 24 for i in range(1, 15)}
    rt.pricefeed_state()["fetched_ts"] = 0.0
    await rt.pricefeed_tick(now)
    check("źródło zakupu = własny sensor → dopasowanie zamrożone", rt.pricefeed_state()["fit"] == fit_before)

    # awaria sieci: błąd zapisany, ceny z poprzedniego pobrania zostają
    async def boom(d):
        raise OSError("brak sieci")
    rt._pricefeed_fetch_day = boom
    rt.pricefeed_state()["fetched_ts"] = 0.0
    before = rt.pricefeed_payload()["prices_tomorrow"]
    await rt.pricefeed_tick(now)
    pl2 = rt.pricefeed_payload()
    check("awaria sieci: komunikat i stare ceny zostają", "brak sieci" in (pl2["error"] or "") and pl2["prices_tomorrow"] == before and "PSE" in (pl2["note"] or ""), pl2["note"])


def main():
    asyncio.run(run())
    print(f"PRICEFEED-RT PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)
main()
