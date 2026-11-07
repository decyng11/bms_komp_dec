"""0.8.8: sprzedaż z baterii — przyczyny odrzucenia z liczbami (najkrótsze okno, nie pierwsze) i obniżona moc sprzedaży do zapasu energii."""
import asyncio, sys
import common
sys.path.insert(0, ".")
from common import *   # noqa
from datetime import date, timedelta


def mk(soc=90, now=(2026, 10, 28, 16), load=8.0, price=None):
    hass, c, opt0, rt = build(); S = hass.states
    c.data = {"load_forecast": {"tomorrow_forecast": load}, "energy_battery_charge_today": 0.0, "energy_pv_today": 20.0}
    sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS))
    at(*now)
    d0, d1 = date(*now[:3]), date(*now[:3]) + timedelta(days=1)
    pr = price or (lambda h: 300 + (400 if 18 <= h < 21 else 0))
    S.set("sensor.rce_pse_cena", 0.6, {"prices": arr(d0, pr) + arr(d1, lambda h: 300)})
    def solc(d, f): return {"detailedHourly": [{"period_start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "pv_estimate": f(h)} for h in range(24)]}
    S.set("sensor.solcast_pv_forecast_forecast_today", 20, solc(d0, lambda h: 3.0 if 9 <= h < 15 else 0.0))
    S.set("sensor.solcast_pv_forecast_forecast_tomorrow", 18, solc(d1, lambda h: 3.0 if 9 <= h < 15 else 0.0))
    S.set(c.config["soc"], soc)
    return hass, c, sched, rt


async def main():
    # ---------- 1. obniżona moc: bateria 90%, dom zużywa 8 kWh/dobę, pełna moc zostawiłaby dom bez energii
    hass, c, sched, rt = mk()
    out = await sched.suggest(); P = out["proposals"]
    p2, e2 = P["bateria_sprzedaz_start_2"], P["bateria_sprzedaz_stop_2"]
    check("fit: sprzedaż zaproponowana (nie odrzucona)", not p2["skip"] and p2["proposed"] == "18:00" and e2["proposed"] == "19:00", (p2["proposed"], e2["proposed"], p2["reason"]))
    check("fit: uzasadnienie mówi o obniżonej mocy i kWh", "Moc sprzedaży obniżona do" in p2["reason"] and "kWh" in p2["reason"], p2["reason"])
    sw = out["assumptions"]["sale_windows"]
    check("fit: assumptions.sale_windows ma okno z mocą 0,5–5 kW", len(sw) == 1 and 500 <= sw[0]["power_w"] < 5000, sw)
    check("fit: pozostałe okna bez wpisu o mocy", all(w["day"] == 0 for w in sw))
    soc_c = out["curve"]["soc"]; fl = out["curve"]["floor"]
    check("fit: SOC w planie nie schodzi poniżej progu nocnego", min(soc_c) >= 19.5, min(soc_c))
    p_w = sw[0]["power_w"]
    check("fit: sprzedaż ~ moc × 1 h (kWh w opisie zgodne z mocą)", f"~{p_w / 1000.0:.1f} kWh" in p2["reason"] or f"{p_w / 1000.0:.1f} kW" in p2["reason"], p2["reason"])

    # ---------- 2. przełącznik wyłączony: okno odpada i podaje liczby
    hass, c, sched, rt = mk()
    hass.states.set("switch.bms_sale_power_fit", "off")
    out = await sched.suggest(); P = out["proposals"]
    r = P["bateria_sprzedaz_start_2"]["reason"]
    check("bez fit: sprzedaż pominięta", P["bateria_sprzedaz_start_2"]["skip"], r)
    check("bez fit: przyczyna z kWh i niedoborem", "brakuje ~" in r and "kWh" in r and "przed świtem" in r, r)
    check("bez fit: brak komunikatu o obniżonej mocy", "obniżona" not in r, r)
    check("bez fit: assumptions.sale_windows puste", out["assumptions"]["sale_windows"] == [], out["assumptions"]["sale_windows"])

    # ---------- 3. kilka prób: raportowane jest najkrótsze okno + lista dłuższych
    hass, c, sched, rt = mk(soc=95, load=12.0)
    hass.states.set("switch.bms_sale_power_fit", "off")
    out = await sched.suggest(); P = out["proposals"]
    r = P["bateria_sprzedaz_start_2"]["reason"]
    check("próby: skip", P["bateria_sprzedaz_start_2"]["skip"], r)
    check("próby: opis najkrótszego okna (1 h) na początku", r.startswith("Pomiń — okno 1 h:"), r)
    check("próby: dłuższe okna wymienione", "dłuższe okna też odpadły" in r and " 2 h:" in r, r)

    # ---------- 4. płaskie ceny — komunikat nadal czytelny
    hass, c, sched, rt = mk(price=lambda h: 300)
    out = await sched.suggest(); P = out["proposals"]
    r = P["bateria_sprzedaz_start_2"]["reason"]
    check("płaskie ceny: skip z przyczyną cenową", P["bateria_sprzedaz_start_2"]["skip"] and ("średniej dnia" in r or "nieopłacalna" in r), r)

    # ---------- 5. wykonanie na falowniku: moc z planu obcina moc sprzedaży tylko w oknie
    hass, c, sched, rt = mk()
    out = await sched.suggest()
    plan = {"assumptions": out["assumptions"]}
    rt._remember_sale_power(plan)
    mem = rt.state.get("sale_power_plan") or {}
    check("runtime: okno zapamiętane pod kluczem data|godzina", "2026-10-28|18" in mem, mem)
    check("runtime: w oknie moc z planu", rt.planned_sale_power_w(at(2026, 10, 28, 18, 5)) == mem["2026-10-28|18"]["power_w"], rt.planned_sale_power_w(at(2026, 10, 28, 18, 5)))
    check("runtime: przed oknem brak ograniczenia", rt.planned_sale_power_w(at(2026, 10, 28, 17, 59)) is None)
    check("runtime: po oknie brak ograniczenia", rt.planned_sale_power_w(at(2026, 10, 28, 19, 0)) is None)
    check("runtime: inny dzień brak ograniczenia", rt.planned_sale_power_w(at(2026, 10, 29, 18, 30)) is None)
    at(2026, 10, 28, 18, 5)
    steps = rt._steps("sprzedaz_6000w")
    nums = [v for k, e, v in steps if k == "number"]
    check("runtime: komenda sprzedaży używa mocy z planu zamiast 6000 W", nums and nums[0] == mem["2026-10-28|18"]["power_w"], steps)
    at(2026, 10, 28, 20, 5)
    steps = rt._steps("sprzedaz_6000w")
    nums = [v for k, e, v in steps if k == "number"]
    check("runtime: poza oknem komenda sprzedaży z pełną mocą 6000 W", nums and nums[0] == 6000, steps)
    at(2026, 10, 28, 18, 5)
    hass.states.set("switch.bms_sale_power_fit", "off")
    steps = rt._steps("sprzedaz_6000w")
    nums = [v for k, e, v in steps if k == "number"]
    check("runtime: przełącznik wyłączony → 6000 W także w oknie", nums and nums[0] == 6000, steps)
    # okno z pełną mocą (power_w None) nadpisuje wcześniejsze obniżone
    hass.states.set("switch.bms_sale_power_fit", "on")
    rt._remember_sale_power({"assumptions": {"sale_windows": [{"day": 0, "start": 18, "stop": 19, "power_w": None}]}})
    check("runtime: nowy plan bez obniżenia znosi stare ograniczenie", rt.planned_sale_power_w(at(2026, 10, 28, 18, 5)) is None)
    # śmieci w pamięci nie psują komendy
    rt.state["sale_power_plan"] = {"zly": {"stop": "x"}, "2026-10-28|18": {"stop": 19, "power_w": "abc"}}
    check("runtime: śmieciowe wpisy → brak ograniczenia, bez wyjątku", rt.planned_sale_power_w(at(2026, 10, 28, 18, 5)) is None)
    # moc poniżej 500 W jest ignorowana (nie dławimy sprzedaży do zera)
    rt.state["sale_power_plan"] = {"2026-10-28|18": {"stop": 19, "power_w": 200}}
    check("runtime: moc < 500 W ignorowana", rt.planned_sale_power_w(at(2026, 10, 28, 18, 5)) is None)
    # stare wpisy są sprzątane
    rt.state["sale_power_plan"] = {"2026-10-20|18": {"stop": 19, "power_w": 1500}}
    rt._remember_sale_power({"assumptions": {"sale_windows": []}})
    check("runtime: wpisy starsze niż wczoraj usuwane", "2026-10-20|18" not in rt.state["sale_power_plan"], rt.state["sale_power_plan"])

    print(f"SALEFIT PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
