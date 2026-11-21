"""Narzędzia w runtime: licznik „co EMS zrobił”, porady, test zaniku sieci, ocena rozbudowy, powiadomienie o słonecznym dniu."""
import asyncio, json, sys
from datetime import date, timedelta
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import notify_cfg as N, deeds as D


async def deeds_part():
    hass, c, opt, rt = build()
    at(2026, 11, 20, 10, 0)
    rt.log.add("guard", "Zabezpieczenie: wstrzymano ładowanie z sieci", "warn")
    rt.log.add("schedule", "Plan zapisany", "info")
    s = rt.deeds_summary()
    json.dumps(s, allow_nan=False)
    check("deeds: summary to słownik z JSON-em", isinstance(s, dict), s)
    check("deeds: state['deeds'] jest słownikiem", isinstance(rt.state["deeds"], dict))
    rt.log.on_entry = lambda e: 1 / 0
    rt.log.add("system", "x", "info")
    check("deeds: wyjątek w hooku nie psuje dziennika", True)


async def advice_part():
    hass, c, opt, rt = build()
    at(2026, 11, 20, 10, 0)
    a = rt.advice()
    json.dumps(a, allow_nan=False)
    check("advice: lista", isinstance(a, list), a)


async def outage_part():
    hass, c, opt, rt = build()
    at(2026, 11, 20, 10, 0)
    r = rt.grid_outage_test()
    check("zanik sieci: bez danych → ok False z komunikatem", r["ok"] is False and r.get("error"), r)
    rt._load_ema = 500.0
    hass.states.set("sensor.bms_battery_soc", 60)
    r = rt.grid_outage_test()
    json.dumps(r, allow_nan=False)
    check("zanik sieci: z danymi lub czytelny błąd", (r["ok"] and r["scenarios"]) or r.get("error"), r)


async def expand_part():
    hass, c, opt, rt = build()
    at(2026, 11, 20, 10, 0)
    r = rt.expand_estimate({"batt_kwh": 5})
    check("rozbudowa: za mało danych → ok False", r["ok"] is False and "Za mało" in r["error"], r)
    for i in range(1, 61):
        k = (date(2026, 11, 20) - timedelta(days=i)).isoformat()
        rt.ledger.days[k] = {"revenue": 1.0, "cost": 4.0, "export_kwh": 3.0, "import_kwh": 6.0, "neg_export_kwh": 0.0}
        rt.stats.days[k] = {"pv": 8.0, "exp": 3.0, "load": 10.0, "imp": 6.0}
    r = rt.expand_estimate({"batt_kwh": 5, "batt_cost_per_kwh": 2000})
    json.dumps(r, allow_nan=False)
    check("rozbudowa: wynik baterii z cenami średnimi", r["ok"] and r["battery"] is not None and r["avg_buy"] == 0.667, r)
    r = rt.expand_estimate({"pv_kwp": 3, "pv_now_kwp": 6, "pv_cost_per_kwp": 4000})
    check("rozbudowa: wynik paneli", r["ok"] and r["pv"] is not None, r)
    r = rt.expand_estimate({})
    check("rozbudowa: brak parametrów → ok False", r["ok"] is False and r.get("error"), r)
    r = rt.expand_estimate({"batt_kwh": "abc", "days": "zzz"})
    check("rozbudowa: śmieci w parametrach bez wyjątku", isinstance(r, dict), r)


async def sunny_part():
    hass, c, opt, rt = build()
    now = at(2026, 11, 20, 18, 0)
    for i, v in enumerate([20, 18, 15, 14, 16, 10, 9]):         # od 14 dni wstecz: dobre dni, potem 2 słabe
        pass
    today = date(2026, 11, 20)
    for i in range(0, 14):
        rt.insights.counters[(today - timedelta(days=i)).isoformat()] = {"pv": 3.0 if i < 2 else 20.0}
    opt._read_pv_forecast_kwh = lambda *a, **k: 19.0
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    await rt.monitor._sunny_day(now)
    inb = [i for i in rt.state.get("inbox", []) if i.get("kind") == "sunny_day"]
    check("słoneczny dzień: jedno powiadomienie", len(inb) == 1, inb)
    await rt.monitor._sunny_day(at(2026, 11, 20, 19, 0))
    inb = [i for i in rt.state.get("inbox", []) if i.get("kind") == "sunny_day"]
    check("słoneczny dzień: bez powtórki tego samego dnia", len(inb) == 1, len(inb))
    hass, c, opt, rt = build()
    for i in range(0, 14):
        rt.insights.counters[(today - timedelta(days=i)).isoformat()] = {"pv": 3.0 if i < 2 else 20.0}
    opt._read_pv_forecast_kwh = lambda *a, **k: 19.0
    await rt.monitor._sunny_day(at(2026, 11, 20, 12, 0))
    check("słoneczny dzień: przed 17:00 cisza", not [i for i in rt.state.get("inbox", []) if i.get("kind") == "sunny_day"])
    check("katalog: sunny_day, priorytet 3, odstęp na liście", N.PRIORITY["sunny_day"] == 3 and N.CATALOG["sunny_day"][5] in N.COOLDOWNS)


async def main():
    await deeds_part()
    await advice_part()
    await outage_part()
    await expand_part()
    await sunny_part()

asyncio.run(main())
print(f"TOOLS_RUNTIME PASS={common.PASS} FAIL={common.FAIL}")
