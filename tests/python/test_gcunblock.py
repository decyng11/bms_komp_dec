"""Okno ładowania z sieci przy prądzie ładowania baterii 0 A (blokada PV): EMS zdejmuje blokadę."""
import asyncio, sys
from common import *   # noqa
import common
from datetime import datetime
TZ = stubs.TZ
def L(h, m, s=10): return datetime(2026, 11, 10, h, m, s, tzinfo=TZ)
CC = "number.inverter_battery_max_charging_current"
def cc_calls(h): return [c for c in h.services.calls if c[0] == "number" and c[2].get("entity_id") == CC]
def sel_calls(h): return [c for c in h.services.calls if c[0] == "select"]

async def main():
    def setup(cc=0, tou="Week"):
        hass, c, opt, rt = build(); S = hass.states
        S.set(CC, cc, {"max": 185, "min": 0}); S.set("select.inverter_time_of_use", tou)
        S.set("time.bms_start_grid_charge", "23:00:00"); S.set("time.bms_stop_grid_charge", "23:59:00"); S.set("switch.bms_ladowanie_z_sieci_1", "on")
        return hass, rt
    # start okna przy zablokowanym prądzie: najpierw prąd, potem TOU
    hass, rt = setup(0)
    st = rt._steps("wlacz_ladowanie_siec")
    check("start okna przy 0 A: krok z prądem ładowania + TOU", len(st) == 2 and st[0][0] == "number" and st[0][2] > 0 and st[1][0] == "select", st)
    hass, rt = setup(120)
    st = rt._steps("wlacz_ladowanie_siec")
    check("prąd > 0: tylko TOU (bez zmian)", len(st) == 1 and st[0][0] == "select", st)
    # zabezpieczenie w trakcie okna
    hass, rt = setup(0, tou="Disabled")
    stubs.CLOCK["now"] = L(23, 24); await rt.enforce_guard(L(23, 24))
    check("w oknie, TOU wyłączony, 0 A: przywraca prąd ładowania", len(cc_calls(hass)) == 1 and cc_calls(hass)[0][2]["value"] > 0, cc_calls(hass))
    n = len(cc_calls(hass))
    hass.states.set(CC, 0, {"max": 185}); stubs.CLOCK["now"] = L(23, 25); await rt.enforce_guard(L(23, 25))
    check("kolejny odczyt tuż po: pauza (bez dubla)", len(cc_calls(hass)) == n)
    hass, rt = setup(0, tou="Disabled")
    stubs.CLOCK["now"] = L(12, 0); await rt.enforce_guard(L(12, 0))
    check("poza oknem: blokada PV nietknięta", cc_calls(hass) == [], cc_calls(hass))
    hass, rt = setup(0, tou="Week")
    stubs.CLOCK["now"] = L(23, 24); await rt.enforce_guard(L(23, 24))
    check("okno, ale ładowanie z sieci wyłączone (TOU): nie rusza", cc_calls(hass) == [], cc_calls(hass))
    hass, rt = setup(150, tou="Disabled")
    stubs.CLOCK["now"] = L(23, 24); await rt.enforce_guard(L(23, 24))
    check("prąd 150 A: nic do robienia", cc_calls(hass) == [])
    print(f"GCUNBLOCK PASS={common.PASS} FAIL={common.FAIL}"); sys.exit(1 if common.FAIL else 0)
asyncio.run(main())
