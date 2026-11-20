"""Zapasowa prognoza PV z ostatnich dni: czysta funkcja, plan, karta, lista problemów, przełącznik, brak wpływu na statystyki trafności."""
import asyncio, json, sys
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import pvfallback as PF, issues as ISS, tariff as tar, insights as INS

TODAY = date(2026, 11, 20)


def day(f, n=24):
    return [f(h) if f(h) is not None else None for h in range(n)]


def sunny(h):
    return 0.5 if 9 <= h < 15 else 0.0


def pure():
    days = {(TODAY - timedelta(days=i)).isoformat(): day(sunny) for i in range(1, 6)}
    fb = PF.profile(days, TODAY)
    check("profil: 5 dób, mediana × 0,8", fb and fb["days"] == 5 and abs(fb["hourly"][10] - 0.4) < 1e-9 and fb["hourly"][3] == 0.0, fb)
    check("profil: suma = suma godzin, surowa przed ostrożnością", fb and abs(fb["kwh"] - 2.4) < 0.01 and abs(fb["raw_kwh"] - 3.0) < 0.01, fb)
    check("profil: 24 godziny", len(fb["hourly"]) == 24)

    # mediana odporna na jeden skrajny dzień
    d2 = dict(days)
    d2[(TODAY - timedelta(days=1)).isoformat()] = day(lambda h: 5.0 if 9 <= h < 15 else 0.0)
    fb2 = PF.profile(d2, TODAY)
    check("profil: jeden skrajny dzień nie zmienia mediany", abs(fb2["hourly"][10] - 0.4) < 1e-9, fb2["hourly"][10])

    check("za mało dób (1) → None", PF.profile({(TODAY - timedelta(days=1)).isoformat(): day(sunny)}, TODAY) is None)
    check("dziś nie wchodzi do profilu", PF.profile({TODAY.isoformat(): day(sunny), (TODAY - timedelta(days=1)).isoformat(): day(sunny)}, TODAY) is None)
    old = {(TODAY - timedelta(days=i)).isoformat(): day(sunny) for i in range(11, 16)}
    check("doby starsze niż 10 dni nie wchodzą", PF.profile(old, TODAY) is None)
    dead = {(TODAY - timedelta(days=i)).isoformat(): day(lambda h: 0.0) for i in range(1, 6)}
    check("doby bez produkcji nie wchodzą", PF.profile(dead, TODAY) is None)
    sparse = {(TODAY - timedelta(days=i)).isoformat(): day(lambda h: 0.5 if h in (11, 12) else None) for i in range(1, 6)}
    check("doby z pomiarem w < 6 godzinach nie wchodzą", PF.profile(sparse, TODAY) is None)
    bad = {"zła": day(sunny), (TODAY - timedelta(days=1)).isoformat(): [0.5] * 5, (TODAY - timedelta(days=2)).isoformat(): "x", 7: [], (TODAY - timedelta(days=3)).isoformat(): [float("nan")] * 24}
    check("śmieci w danych: brak wyjątku, None", PF.profile(bad, TODAY) is None)
    check("nie-słownik → None", PF.profile(None, TODAY) is None and PF.profile([1], TODAY) is None)
    mixed = {(TODAY - timedelta(days=i)).isoformat(): day(lambda h: -1.0 if h == 5 else sunny(h)) for i in range(1, 4)}
    fb3 = PF.profile(mixed, TODAY)
    check("ujemna wartość traktowana jak brak pomiaru", fb3 and fb3["hourly"][5] == 0.0, fb3)
    check("ostrożność ograniczona do 0–1", PF.profile(days, TODAY, caution=5)["caution"] == 1.0 and PF.profile(days, TODAY, caution=-1)["caution"] == 0.0)
    check("podpis po polsku", PF.label(fb) == "szacunek z ostatnich 5 dni × 0,8", PF.label(fb))


def seed_hist(rt, n=5, f=sunny):
    for i in range(1, n + 1):
        d = (TODAY - timedelta(days=i)).isoformat()
        for h in range(24):
            b = INS._blank_bucket()
            b[INS.PV] = float(f(h))
            rt.insights.hours[f"{d}T{h:02d}"] = b


async def env(now=(2026, 11, 20, 12, 0), solcast=True):
    hass, c, sched = await mk(now, 60)
    rt = rtm.BmsRuntime(hass, c, sched)
    c.runtime = rt
    if not solcast:
        for eid in ("sensor.solcast_pv_forecast_forecast_today", "sensor.solcast_pv_forecast_forecast_tomorrow"):
            hass.states.set(eid, "unavailable", {})
    return hass, c, sched, rt


async def runtime_part():
    tar.set_profile(tar.make_profile({"tariff_mode": "zone"}, prices_fn=lambda d: None, eff_fn=lambda: 0.9, source=""))

    # ---------- jest prawdziwa prognoza: zapasowa się nie wtrąca
    hass, c, sched, rt = await env()
    seed_hist(rt)
    check("prawdziwa prognoza: zapasowa nieużywana", not sched.pv_fallback_used(0) and not sched.pv_fallback_used(1))
    check("prawdziwa prognoza: godziny z Solcast", sched._read_pv_hourly(0, fallback=True)[10] == 0.6, sched._read_pv_hourly(0, fallback=True))
    check("prawdziwa prognoza: źródło bez „zapasowa”", "zapasowa" not in str(sched.pv_source()), sched.pv_source())

    # ---------- brak prognozy, jest historia
    hass, c, sched, rt = await env(solcast=False)
    seed_hist(rt)
    check("brak prognozy: _read_pv_hourly bez fallback → None (statystyki trafności nie uczą się z szacunku)", sched._read_pv_hourly(0) is None and sched.pv_raw_today()[1] is None and sched.pv_raw_today()[0] is None)
    fbh = sched._read_pv_hourly(0, fallback=True)
    check("brak prognozy: z fallback → zapasowy profil 0,4 kWh/h w południe", fbh is not None and abs(fbh[10] - 0.4) < 1e-6 and fbh[2] == 0.0, fbh)
    check("brak prognozy: suma dobowa z zapasowej", abs(sched._read_pv_forecast_kwh("pv_forecast_today", "", fallback=True) - 2.4) < 0.01
          and sched._read_pv_forecast_kwh("pv_forecast_today", "") is None)
    check("pv_fallback_used dla dziś i jutra", sched.pv_fallback_used(0) and sched.pv_fallback_used(1))
    pv0, sun0 = sched._pv_day(0)
    check("plan: _pv_day dostaje zapasowe godziny (dzień przycięty do wschód–zachód)", pv0 is not None and sum(v or 0 for v in pv0) > 1.5, pv0)
    ctx = sched._build_context(at(2026, 11, 20, 12, 0), 60.0)
    check("plan: w kontekście PV jutro > 0 (nie „słońca nie będzie”)", ctx["pv_kwh"][1] and abs(ctx["pv_kwh"][1] - 2.4) < 0.01, ctx["pv_kwh"])
    asm = sched._assumptions(ctx)
    check("plan: założenia oznaczają zapasowe źródło", asm["pv_fallback"] is True and str(asm["pv_source"]).startswith("zapasowa: szacunek z ostatnich 5 dni"), asm)
    check("plan: współczynnik korekty nie jest nakładany na zapasową", abs(ctx["pv_kwh"][0] - 2.4) < 0.01)

    # ---------- karta
    pay = sched.pv_card_payload()
    check("karta: godziny dziś i jutro z zapasowej", pay["pv_hourly_today"] and pay["pv_hourly_tomorrow"] and abs(pay["pv_hourly_today"][10] - 0.4) < 1e-6, pay.get("pv_hourly_today"))
    check("karta: znacznik pv_fallback z liczbą dni i podpisem", pay["pv_fallback"]["days"] == 5 and pay["pv_fallback"]["offsets"] == [0, 1] and "szacunek" in pay["pv_fallback"]["label"], pay.get("pv_fallback"))
    check("karta: źródło prognozy podpisane jako zapasowa", str(pay["pv_forecast_source"]).startswith("zapasowa"), pay["pv_forecast_source"])
    check("karta: dzienne sumy dziś/jutro z oznaczeniem szacunku", pay["pv_daily"][0]["kwh"] == 2.4 and pay["pv_daily"][0].get("est") and pay["pv_daily"][1].get("est"), pay["pv_daily"][:2])
    check("karta: godziny po korekcie = surowe zapasowe (bez podwójnej korekty)", pay["pv_hourly_today_adj"] == pay["pv_hourly_today"], pay.get("pv_hourly_today_adj"))
    check("karta: dzienna suma po korekcie bez zmian (współczynnik 1)", pay["pv_daily"][0]["kwh"] == 2.4 and pay["pv_daily"][0].get("factor") in (None, 1.0), pay["pv_daily"][0])
    raw = sched.pv_card_payload_raw()
    check("surowa prognoza (do statystyk) nie zawiera zapasowej", not raw.get("pv_fallback") and not raw["pv_hourly_today"], raw.get("pv_hourly_today"))
    from custom_components.bms_komp_dec.sensor import BmsRuntimeSensor
    check("atrybut pv_fallback jest nierejestrowany w historii", "pv_fallback" in BmsRuntimeSensor._unrecorded_attributes)
    json.dumps(pay, allow_nan=False)

    # ---------- lista problemów
    got = ISS.collect(rt, at(2026, 11, 20, 12, 0))
    it = next((i for i in got if i["id"] == "pv_today"), None)
    check("lista: brak prognozy, ale jest szacunek → informacja, nie ostrzeżenie", it and it["level"] == "info" and "szacunku" in it["title"] and "5 dni" in it["detail"], it)
    check("lista: szczegół z liczbą kWh po polsku", it and "2,4 kWh" in it["detail"], it)
    got = ISS.collect(rt, at(2026, 11, 20, 19, 0))
    check("lista: jutro po 18:00 też informacja", any(i["id"] == "pv_tomorrow" and i["level"] == "info" for i in got), got)

    # ---------- przełącznik wyłącza zapasową → jak dawniej
    hass.states.set("switch.bms_pv_fallback_forecast", "off")
    sched._pvfb_cache = None
    check("przełącznik off: brak zapasowej", sched.pv_fallback() is None and sched._read_pv_hourly(0, fallback=True) is None and not sched.pv_fallback_used(0))
    got = ISS.collect(rt, at(2026, 11, 20, 12, 0))
    it = next((i for i in got if i["id"] == "pv_today"), None)
    check("przełącznik off: znów ostrzeżenie „jakby słońca nie było”", it and it["level"] == "warn" and "jakby słońca nie było" in it["detail"], it)
    pay = sched.pv_card_payload()
    check("przełącznik off: karta bez zapasowej", not pay.get("pv_fallback") and not pay["pv_hourly_today"], pay.get("pv_fallback"))

    # ---------- za mało historii
    hass, c, sched, rt = await env(solcast=False)
    seed_hist(rt, n=1)
    check("jedna doba historii: brak zapasowej, ostrzeżenie jak dawniej", sched.pv_fallback() is None
          and any(i["id"] == "pv_today" and i["level"] == "warn" for i in ISS.collect(rt, at(2026, 11, 20, 12, 0))))
    hass, c, sched, rt = await env(solcast=False)
    check("zero historii: brak zapasowej i brak wyjątków", sched.pv_fallback() is None and sched.pv_card_payload()["pv_hourly_today"] is None)

    # ---------- tylko jutro bez prognozy (dziś jest): zapasowa tylko na jutro, dziś bez zmian
    hass, c, sched, rt = await env()
    seed_hist(rt)
    hass.states.set("sensor.solcast_pv_forecast_forecast_tomorrow", "unavailable", {})
    check("dziś prawdziwa, jutro zapasowa", not sched.pv_fallback_used(0) and sched.pv_fallback_used(1))
    pay = sched.pv_card_payload()
    check("karta: zapasowa tylko na jutro", pay["pv_fallback"]["offsets"] == [1] and pay["pv_daily"][1].get("est") and not pay["pv_daily"][0].get("est"), pay.get("pv_fallback"))

    # ---------- pamięć podręczna: dane z historii zmieniają się najwyżej co 10 minut
    hass, c, sched, rt = await env(solcast=False)
    seed_hist(rt)
    a = sched.pv_fallback()
    seed_hist(rt, f=lambda h: 1.0 if 9 <= h < 15 else 0.0)
    b = sched.pv_fallback()
    check("cache: ten sam wynik w obrębie 10 min", a is b)
    sched._pvfb_cache = None
    check("cache wyczyszczony → nowe dane", abs(sched.pv_fallback()["hourly"][10] - 0.8) < 1e-6)


async def main():
    pure()
    await runtime_part()


asyncio.run(main())
print(f"PVFALLBACK PASS={common.PASS} FAIL={common.FAIL}")
