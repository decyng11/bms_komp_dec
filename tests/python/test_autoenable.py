"""Auto-stosowanie / ręczne zatwierdzenie godzin włącza przełącznik zestawu (bez niego okno nie wystartuje), z zabezpieczeniem przed arbitrażem."""
import asyncio, sys
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import automation


def prop(cur, new):
    return {"proposed": new, "current": cur, "confidence": "high", "skip": False}


async def main():
    hass, c, opt, rt = build(); S = hass.states
    for k, v in (("start_grid_charge", "22:00:00"), ("stop_grid_charge", "04:00:00"),
                 ("bateria_sprzedaz_start", "17:00:00"), ("bateria_sprzedaz_stop", "19:00:00")):
        S.set(f"time.bms_{k}", v)
    for sw in ("ladowanie_z_sieci_1", "bateria_sprzedaz_1"):
        S.set(f"switch.bms_{sw}", "off")
    S.set("switch.bms_auto_apply", "on")
    res = {"proposals": {
        "start_grid_charge": prop("22:00", "23:00"), "stop_grid_charge": prop("04:00", "05:00"),
        "bateria_sprzedaz_start": prop("17:00", "18:00"), "bateria_sprzedaz_stop": prop("19:00", "20:00")}}
    out = await automation.async_auto_apply(rt, hass, res)
    check("auto: godziny zapisane", out["applied"].get("start_grid_charge") == "23:00", out)
    check("auto: włączono zestaw ładowania z sieci", S.get("switch.bms_ladowanie_z_sieci_1").state == "on")
    check("auto: włączono zestaw sprzedaży (brak zakazu)", S.get("switch.bms_bateria_sprzedaz_1").state == "on")
    check("auto: zestawy zapamiętane do cofnięcia", set(rt.state.get("auto_enabled", [])) == {"ladowanie_z_sieci_1", "bateria_sprzedaz_1"}, rt.state.get("auto_enabled"))
    await automation.async_undo_auto_apply(rt, hass)
    check("cofnięcie: zestawy znów wyłączone", S.get("switch.bms_ladowanie_z_sieci_1").state == "off" and S.get("switch.bms_bateria_sprzedaz_1").state == "off")
    check("cofnięcie: lista wyczyszczona", rt.state.get("auto_enabled") == [])

    # zakaz sprzedaży (arbitraż: bateria naładowana więcej niż wyprodukowało PV) → sprzedaży NIE włączamy, ładowanie tak
    hass, c, opt, rt = build(); S = hass.states
    for k, v in (("start_grid_charge", "22:00:00"), ("stop_grid_charge", "04:00:00"),
                 ("bateria_sprzedaz_start", "17:00:00"), ("bateria_sprzedaz_stop", "19:00:00")):
        S.set(f"time.bms_{k}", v)
    for sw in ("ladowanie_z_sieci_1", "bateria_sprzedaz_1"):
        S.set(f"switch.bms_{sw}", "off")
    c.data = {**(c.data or {}), "energy_battery_charge_today": 12.0, "energy_pv_today": 2.0}
    S.set("switch.bms_auto_apply", "on")
    check("warunek testu: arbitraż blokuje sprzedaż", rt.arbitrage_status()[0] is True)
    out = await automation.async_auto_apply(rt, hass, res)
    check("arbitraż: sprzedaży nie włączono", S.get("switch.bms_bateria_sprzedaz_1").state == "off", S.get("switch.bms_bateria_sprzedaz_1").state)
    check("arbitraż: ładowanie włączone", S.get("switch.bms_ladowanie_z_sieci_1").state == "on")
    check("arbitraż: powód w dzienniku", "zakaz sprzedaży" in str(list(rt.log.entries.values()) if isinstance(rt.log.entries, dict) else rt.log.entries))

    # niepełne okno (Stop = 00:00) → nic nie włączamy
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge", "22:00:00"); S.set("time.bms_stop_grid_charge", "00:00:00")
    S.set("switch.bms_ladowanie_z_sieci_1", "off")
    en = await automation.async_enable_sets(rt, hass, {"start_grid_charge"})
    check("niepełne okno: bez włączania", en == [] and S.get("switch.bms_ladowanie_z_sieci_1").state == "off")
    # już włączony → bez zmian i bez wpisu do cofnięcia
    S.set("time.bms_stop_grid_charge", "04:00:00"); S.set("switch.bms_ladowanie_z_sieci_1", "on")
    en = await automation.async_enable_sets(rt, hass, {"start_grid_charge"})
    check("już włączony: bez zmian", en == [] and not rt.state.get("auto_enabled"))
    print(f"AUTOENABLE PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
