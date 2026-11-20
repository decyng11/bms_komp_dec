"""Powiadomienie „plan na jutro”: czysta logika (wybór okien, zdanie), wysyłka po cenach na jutro, raz na dobę, wyłączenie, błąd planu."""
import asyncio, sys
from datetime import date
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import tomorrowplan as TP, notify_cfg as N

D1 = date(2026, 11, 21)


def P(proposed, skip=False, **kw):
    return {"proposed": proposed, "skip": skip, "label": "x", **kw}


def sale_pair(start, stop, kwh=3.2, gain=2.1, day=1, suffix=""):
    ex = {"sale_kwh": kwh, "gain_pln": gain, "sale_day": day}
    return {f"bateria_sprzedaz_start{suffix}": P(start, **ex), f"bateria_sprzedaz_stop{suffix}": P(stop, **ex)}


def pure():
    props = {**sale_pair("18:00", "20:00"), "start_grid_charge": P("02:00"), "stop_grid_charge": P("05:00")}
    info = TP.summarize(props, 12.34)
    check("okno ładowania i sprzedaży wybrane", info["charges"] == [{"start": "02:00", "stop": "05:00"}] and len(info["sales"]) == 1, info)
    check("zysk z jednego okna sprzedaży", info["gain"] == 2.1 and info["pv_kwh"] == 12.34, info)
    msg = TP.message(info)
    check("zdanie: ładowanie, sprzedaż z kWh i zyskiem, PV", msg == "Plan na jutro: ładowanie z sieci 02:00–05:00; sprzedaż z baterii 18:00–20:00 (~3,2 kWh, zysk ~2,10 zł). Prognoza PV: 12,3 kWh.", msg)

    two = {**sale_pair("07:00", "08:00", 1.0, 0.5), **sale_pair("18:00", "20:00", 3.0, 2.0, suffix="_2")}
    i2 = TP.summarize(two, None)
    m2 = TP.message(i2)
    check("dwa okna sprzedaży: suma zysku, brak PV w zdaniu", i2["gain"] == 2.5 and "Razem ze sprzedaży ok. 2,50 zł" in m2 and "Prognoza PV" not in m2, m2)

    check("sprzedaż dzisiejsza (sale_day 0) nie wchodzi do planu na jutro", TP.summarize(sale_pair("18:00", "20:00", day=0), None)["sales"] == [])
    check("pominięta sprzedaż nie wchodzi", TP.summarize({**sale_pair("18:00", "20:00"), "bateria_sprzedaz_start": P("18:00", skip=True, sale_day=1)}, None)["sales"] == [])
    check("pominięte ładowanie nie wchodzi", TP.summarize({"start_grid_charge": P("02:00", skip=True), "stop_grid_charge": P("05:00")}, None)["charges"] == [])
    check("para bez końca nie wchodzi", TP.summarize({"start_grid_charge": P("02:00")}, None)["charges"] == [] and TP.summarize({"bateria_sprzedaz_start": P("18:00", sale_day=1)}, None)["sales"] == [])
    check("zła godzina odrzucona", TP.summarize({"start_grid_charge": P("25:00"), "stop_grid_charge": P("05:00")}, None)["charges"] == []
          and TP.summarize({"start_grid_charge": P("ab:cd"), "stop_grid_charge": P("05:00")}, None)["charges"] == [])
    empty = TP.message(TP.summarize({}, 8.0))
    check("pusty plan: mówi wprost, że nic nie zaplanowano", "bez ładowania z sieci i bez sprzedaży z baterii" in empty and "Prognoza PV: 8,0 kWh." in empty, empty)
    check("śmieci na wejściu nie wywalają", TP.summarize(None, "x")["sales"] == [] and TP.summarize("abc", float("nan"))["pv_kwh"] is None and TP.summarize([1], None)["charges"] == [])
    nogain = TP.message(TP.summarize({"bateria_sprzedaz_start": P("18:00", sale_day=1, sale_kwh=2.0), "bateria_sprzedaz_stop": P("19:00", sale_day=1, sale_kwh=2.0)}, None))
    check("brak zysku w propozycji: zdanie bez zysku", "~2,0 kWh" in nogain and "zysk" not in nogain, nogain)
    check("nan w zysku pomijany", TP.summarize(sale_pair("18:00", "19:00", gain=float("nan")), None)["gain"] is None)
    check("własna etykieta dnia", TP.message(TP.summarize({}, None), "pojutrze").startswith("Plan na pojutrze:"))


def pn(hass):
    return [c for c in hass.services.calls if c[0] == "persistent_notification" and c[1] == "create" and "plan na jutro" in c[2]["title"].lower()]


def mkrt(prices=24):
    hass, c, opt, rt = build()
    opt._read_rce_arrays = lambda: {D1.isoformat(): [0.4] * prices}
    opt.rce_expected_hours = lambda d: 24
    opt._read_pv_forecast_kwh = lambda *a, **k: 11.5
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    calls = {"n": 0}
    plan = {"proposals": {**sale_pair("18:00", "20:00"), "start_grid_charge": P("02:00"), "stop_grid_charge": P("05:00")}}

    async def fake_refresh(force=False):
        calls["n"] += 1
        return calls.get("plan", plan)
    rt.refresh_plan = fake_refresh
    return hass, c, opt, rt, calls


async def runtime_part():
    hass, c, opt, rt, calls = mkrt()
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 16, 0))
    check("przed 16:30: cisza i bez przeliczania planu", not pn(hass) and calls["n"] == 0)
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 16, 30))
    m = pn(hass)
    check("o 16:30 z pełnymi cenami: jedno powiadomienie", len(m) == 1, m)
    check("tytuł z datą jutra", "21.11" in m[0][2]["title"], m[0][2]["title"])
    check("treść: ładowanie, sprzedaż, PV", "02:00–05:00" in m[0][2]["message"] and "18:00–20:00" in m[0][2]["message"] and "11,5 kWh" in m[0][2]["message"], m[0][2]["message"])
    check("plan przeliczony raz na świeżo", calls["n"] == 1, calls)
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 17, 0))
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 20, 0))
    check("kolejne ticki tego dnia: bez powtórki i bez przeliczeń", len(pn(hass)) == 1 and calls["n"] == 1, (len(pn(hass)), calls))
    check("wpis w skrzynce panelu (dzwonek)", any(i.get("kind") == "plan_tomorrow" for i in rt.state.get("inbox", [])), rt.state.get("inbox"))
    check("domyślnie nie idzie na telefon (tylko HA/skrzynka)", not [x for x in hass.services.calls if x[0] == "notify"], [x[:2] for x in hass.services.calls if x[0] == "notify"])
    await rt.monitor._plan_tomorrow(at(2026, 11, 21, 16, 40))
    check("następnego dnia — bez nowych cen na kolejny dzień — cisza", len(pn(hass)) == 1)

    # niepełne ceny na jutro
    hass, c, opt, rt, calls = mkrt(prices=20)
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 17, 0))
    check("niepełne ceny: cisza i bez przeliczania", not pn(hass) and calls["n"] == 0)
    opt._read_rce_arrays = lambda: {D1.isoformat(): [0.4] * 24}
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 17, 10))
    check("po uzupełnieniu cen: powiadomienie", len(pn(hass)) == 1)

    # po 23:00 już nie
    hass, c, opt, rt, calls = mkrt()
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 23, 5))
    check("po 23:00: cisza", not pn(hass))

    # wyłączone w konfiguratorze
    hass, c, opt, rt, calls = mkrt()
    rt.state["notify_cfg"] = N.effective({"kinds": {"plan_tomorrow": {"on": False}}})
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 17, 0))
    check("wyłączone: cisza, bez przeliczeń, bez znacznika „wysłano”", not pn(hass) and calls["n"] == 0 and "plan_tomorrow" not in (rt.state.get("notify_once") or {}))
    rt.state["notify_cfg"] = N.effective({"kinds": {"plan_tomorrow": {"on": True}}})
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 17, 5))
    inb = [i for i in rt.state.get("inbox", []) if i.get("kind") == "plan_tomorrow"]
    check("po włączeniu tego samego dnia: wysyła (poziom domyślny „ważne”: tylko skrzynka, bez powiadomienia HA)", len(inb) == 1 and not pn(hass), (inb, pn(hass)))

    # plan z błędem: ponawianie co 10 minut, nie co tick
    hass, c, opt, rt, calls = mkrt()
    calls["plan"] = {"error": "brak SOC", "proposals": {}}
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 17, 0))
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 17, 3))
    check("błąd planu: bez powiadomienia, jedna próba w ciągu 10 min", not pn(hass) and calls["n"] == 1, calls)
    calls["plan"] = {"proposals": {**sale_pair("19:00", "20:00")}}
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 17, 12))
    check("po 10 min plan działa: powiadomienie", len(pn(hass)) == 1 and "19:00–20:00" in pn(hass)[0][2]["message"] and calls["n"] == 2, (len(pn(hass)), calls))
    calls["plan"] = None
    hass, c, opt, rt, calls = mkrt()
    calls["plan"] = None
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 17, 0))
    check("brak planu (None): bez wyjątku i bez powiadomienia", not pn(hass))

    # pusty plan to też informacja
    hass, c, opt, rt, calls = mkrt()
    calls["plan"] = {"proposals": {"start_grid_charge": P("02:00", skip=True)}}
    await rt.monitor._plan_tomorrow(at(2026, 11, 20, 17, 0))
    check("plan bez okien: komunikat „bez ładowania i bez sprzedaży”", len(pn(hass)) == 1 and "bez ładowania z sieci i bez sprzedaży" in pn(hass)[0][2]["message"], pn(hass))

    # katalog
    check("katalog: rodzaj, grupa, priorytet info, odstęp raz na dobę, domyślnie bez telefonu",
          N.CATALOG["plan_tomorrow"][0] == "Ceny i plan" and N.PRIORITY["plan_tomorrow"] == 3 and N.CATALOG["plan_tomorrow"][5] == 1440 and N.CATALOG["plan_tomorrow"][4] is False)
    check("odstęp rodzaju jest na liście do wyboru", N.CATALOG["plan_tomorrow"][5] in N.COOLDOWNS)
    check("domyślnie włączone", N.effective({})["kinds"]["plan_tomorrow"]["on"] is True)


async def main():
    pure()
    await runtime_part()


asyncio.run(main())
print(f"TOMORROWPLAN PASS={common.PASS} FAIL={common.FAIL}")
