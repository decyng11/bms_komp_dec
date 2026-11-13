"""Awaryjny STOP po czasie, puste okno, limit przesunięcia dla pustego okna, cofnięcie zerowania, ponowienia na żywo."""
import asyncio, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import automation
from homeassistant.util import dt as dt_util


def cmds(rt):
    ents = list(rt.log.entries.values()) if isinstance(rt.log.entries, dict) else list(rt.log.entries)
    return [e["msg"] for e in ents if e.get("kind") in ("command", "guard")]


async def main():
    base = dt_util.now().replace(hour=5, minute=0, second=0, microsecond=0)
    # --- ładowanie z sieci: start z harmonogramu 05:00, STOP 06:00 przepadł (restart HA) → awaryjny STOP o 06:03
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge", "05:00:00"); S.set("time.bms_stop_grid_charge", "06:00:00")
    S.set("switch.bms_ladowanie_z_sieci_1", "on")
    await rt.process_rules(base)
    check("start z harmonogramu zapamiętany", (rt.state.get("gc_sched") or {}).get("start_key") == "start_grid_charge", rt.state.get("gc_sched"))
    check("warunek testu: ładowanie z sieci trwa", rt.grid_charging_on())
    await rt.enforce_guard(base + timedelta(minutes=30))
    check("w trakcie okna: bez awaryjnego STOP", rt.grid_charging_on() and rt.state.get("gc_sched"))
    rt.fired.clear(); rt._guard_last.clear()                       # „restart HA”: pamięć ulotna znika, znacznik w stanie zostaje
    await rt.enforce_guard(base + timedelta(minutes=63))
    check("po oknie: awaryjny STOP wyłączył ładowanie", not rt.grid_charging_on(), cmds(rt)[-3:])
    check("awaryjny STOP: wpis w dzienniku i znacznik usunięty", any("Awaryjny STOP" in m for m in cmds(rt)) and not rt.state.get("gc_sched"))

    # zwykły STOP o czasie czyści znacznik — awaryjny nie jest potrzebny
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge", "05:00:00"); S.set("time.bms_stop_grid_charge", "06:00:00")
    S.set("switch.bms_ladowanie_z_sieci_1", "on")
    await rt.process_rules(base); await rt.process_rules(base + timedelta(hours=1))
    check("zwykły STOP: znacznik usunięty, ładowanie wyłączone", not rt.state.get("gc_sched") and not rt.grid_charging_on())

    # ładowanie włączone ręcznie (bez harmonogramu) — awaryjny STOP go nie rusza
    hass, c, opt, rt = build(); S = hass.states
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    await rt.enforce_guard(base + timedelta(hours=3))
    check("ręczne ładowanie poza oknami: nietknięte", rt.grid_charging_on())

    # „Wymuś ładowanie” po oknie: awaryjny STOP nie przerywa
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge", "05:00:00"); S.set("time.bms_stop_grid_charge", "06:00:00")
    S.set("switch.bms_ladowanie_z_sieci_1", "on")
    await rt.process_rules(base)
    S.set("switch.bms_force_charge_battery", "on")
    await rt.enforce_guard(base + timedelta(minutes=63))
    check("Wymuś ładowanie włączone: bez awaryjnego STOP", rt.grid_charging_on())

    # --- sprzedaż: start z harmonogramu, STOP przepadł → awaryjny STOP
    hass, c, opt, rt = build(); S = hass.states
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0}
    t17 = base.replace(hour=17)
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("time.bms_bateria_sprzedaz_stop", "18:00:00")
    S.set("switch.bms_bateria_sprzedaz_1", "on")
    await rt.process_rules(t17)
    check("warunek testu: sprzedaż trwa", rt.is_selling(), cmds(rt)[-2:])
    await rt.enforce_guard(t17 + timedelta(minutes=30))
    check("sprzedaż w oknie: bez awaryjnego STOP", rt.is_selling())
    rt.fired.clear(); rt._guard_last.clear()
    await rt.enforce_guard(t17 + timedelta(minutes=62))
    check("sprzedaż po oknie: awaryjny STOP", not rt.is_selling(), cmds(rt)[-3:])

    # --- puste okno (start = stop) włączone ręcznie: ani START, ani STOP
    hass, c, opt, rt = build(); S = hass.states
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0}
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("time.bms_bateria_sprzedaz_stop", "17:00:00")
    S.set("switch.bms_bateria_sprzedaz_1", "on")
    out = await rt.process_rules(t17)
    check("puste okno: nic nie wykonano", not out["results"] and not rt.is_selling(), out)

    # --- limit przesunięcia nie blokuje pustego (wyzerowanego) okna
    hass, c, opt, rt = build(); S = hass.states
    S.set("switch.bms_auto_apply", "on"); S.set("switch.bms_bateria_sprzedaz_2", "off")
    S.set("time.bms_bateria_sprzedaz_start_2", "08:00:00"); S.set("time.bms_bateria_sprzedaz_stop_2", "08:00:00")
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0}
    pp = lambda cur, new: {"skip": False, "proposed": new, "current": cur, "confidence": "high", "reason": "x"}
    far = {"proposals": {"bateria_sprzedaz_start_2": pp("08:00", "18:00"), "bateria_sprzedaz_stop_2": pp("08:00", "19:00")}}
    out = await automation.async_auto_apply(rt, hass, far)
    check("puste okno: propozycja o 10 h dalej zastosowana mimo limitu 4 h",
          S.get("time.bms_bateria_sprzedaz_start_2").state[:5] == "18:00" and S.get("time.bms_bateria_sprzedaz_stop_2").state[:5] == "19:00", out)
    S.set("time.bms_bateria_sprzedaz_start_2", "08:00:00"); S.set("time.bms_bateria_sprzedaz_stop_2", "09:00:00")
    out = await automation.async_auto_apply(rt, hass, far)
    check("zwykłe okno: limit przesunięcia nadal działa", S.get("time.bms_bateria_sprzedaz_start_2").state[:5] == "08:00", out)

    # --- cofnięcie przywraca wyzerowane godziny sprzedaży
    hass, c, opt, rt = build(); S = hass.states
    S.set("switch.bms_auto_apply", "on"); S.set("switch.bms_bateria_sprzedaz_2", "on")
    S.set("time.bms_bateria_sprzedaz_start_2", "18:00:00"); S.set("time.bms_bateria_sprzedaz_stop_2", "19:00:00")
    sk = {"skip": True, "proposed": None, "current": "18:00", "confidence": "high", "reason": "Pomiń — nieopłacalna"}
    await automation.async_auto_apply(rt, hass, {"proposals": {"bateria_sprzedaz_start_2": sk, "bateria_sprzedaz_stop_2": sk}})
    check("warunek testu: okno wyzerowane", S.get("time.bms_bateria_sprzedaz_stop_2").state[:5] == "18:00")
    await automation.async_undo_auto_apply(rt, hass)
    check("cofnięcie: stop wraca na 19:00, zestaw włączony",
          S.get("time.bms_bateria_sprzedaz_stop_2").state[:5] == "19:00" and S.get("switch.bms_bateria_sprzedaz_2").state == "on")

    # --- plan na żywo: odstęp 1 h tylko po faktycznej zmianie; odrzucona propozycja nie zaśmieca dziennika
    hass, c, opt, rt = build(); S = hass.states
    S.set("switch.bms_auto_apply", "on"); S.set("switch.bms_ladowanie_z_sieci_2", "on")
    S.set("time.bms_start_grid_charge_2", "12:00:00"); S.set("time.bms_stop_grid_charge_2", "13:00:00")
    t0 = base.replace(hour=1); m = lambda x: t0 + timedelta(minutes=x)
    pl = {"proposals": {"start_grid_charge_2": pp("12:00", "11:00"), "stop_grid_charge_2": pp("13:00", "13:00")}}
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")           # system zajęty
    await automation.async_live_apply(rt, hass, pl, m(0)); await automation.async_live_apply(rt, hass, pl, m(31))
    check("zajęty (trwa ładowanie): nic nie zapisano", S.get("time.bms_start_grid_charge_2").state[:5] == "12:00")
    await rt.run_command("wylacz_ladowanie_siec", source="ręcznie")
    await automation.async_live_apply(rt, hass, pl, m(45))
    check("po 14 min od nieudanej próby: jeszcze nie", S.get("time.bms_start_grid_charge_2").state[:5] == "12:00")
    await automation.async_live_apply(rt, hass, pl, m(62))
    check("po 30 min od nieudanej próby (bez czekania godziny): zastosowano", S.get("time.bms_start_grid_charge_2").state[:5] == "11:00")
    # limit przesunięcia: jedna próba, potem cisza przez 6 h
    hass, c, opt, rt = build(); S = hass.states
    S.set("switch.bms_auto_apply", "on"); S.set("switch.bms_ladowanie_z_sieci_2", "on")
    S.set("time.bms_start_grid_charge_2", "12:00:00"); S.set("time.bms_stop_grid_charge_2", "13:00:00")
    farp = {"proposals": {"start_grid_charge_2": pp("12:00", "18:00"), "stop_grid_charge_2": pp("13:00", "19:00")}}
    for x in (0, 31, 100, 200, 300):
        await automation.async_live_apply(rt, hass, farp, m(x))
    ents = list(rt.log.entries.values()) if isinstance(rt.log.entries, dict) else list(rt.log.entries)
    n = len([e for e in ents if "z planu na żywo" in e["msg"]])
    check("limit przesunięcia: jedna próba w ciągu 5 h (bez zaśmiecania dziennika)", n == 1, n)
    await automation.async_live_apply(rt, hass, farp, m(31 + 361))
    ents = list(rt.log.entries.values()) if isinstance(rt.log.entries, dict) else list(rt.log.entries)
    check("po 6 h: kolejna próba", len([e for e in ents if "z planu na żywo" in e["msg"]]) == 2)
    print(f"LATESTOP PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
