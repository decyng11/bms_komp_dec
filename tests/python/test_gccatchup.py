"""Okno ładowania z sieci zatwierdzone w trakcie trwania (np. 05:13 dla 05:00–06:00) włącza się od razu — raz."""
import asyncio, sys
from common import *   # noqa
import common
from datetime import datetime

TZ = stubs.TZ
def L(h, m, s=10): return datetime(2026, 11, 9, h, m, s, tzinfo=TZ)
def tou_calls(h): return [c for c in h.services.calls if c[0] == "select"]

async def main():
    def setup(start="05:00:00", stop="06:00:00", sw="on"):
        hass, c, opt, rt = build(); S = hass.states
        S.set("time.bms_start_grid_charge", start); S.set("time.bms_stop_grid_charge", stop)
        S.set("switch.bms_ladowanie_z_sieci_1", sw)
        return hass, rt
    hass, rt = setup()
    stubs.CLOCK["now"] = L(4, 50); await rt.process_rules(L(4, 50))
    check("przed oknem: nic", not tou_calls(hass), tou_calls(hass))
    stubs.CLOCK["now"] = L(5, 13); await rt.process_rules(L(5, 13))
    check("w trakcie okna: włącza ładowanie (TOU)", len(tou_calls(hass)) == 1, tou_calls(hass))
    check("zapamiętano start (STOP zadziała)", rt.fired.get("start_grid_charge") is not None)
    n = len(hass.services.calls)
    hass.states.set("select.inverter_time_of_use", "Week")   # nawet gdy ktoś to cofnie — raz na okno
    stubs.CLOCK["now"] = L(5, 13, 40); await rt.process_rules(L(5, 13, 40))
    stubs.CLOCK["now"] = L(5, 30); await rt.process_rules(L(5, 30))
    check("tylko raz na okno", len(tou_calls(hass)) == 1, tou_calls(hass))
    stubs.CLOCK["now"] = L(6, 40); await rt.process_rules(L(6, 40))
    check("po oknie: bez zmian", len(tou_calls(hass)) == 1)

    hass, rt = setup(sw="off")
    stubs.CLOCK["now"] = L(5, 13); await rt.process_rules(L(5, 13))
    check("zestaw wyłączony: nie włącza", not tou_calls(hass))

    hass, rt = setup()
    rt.grid_charging_on = lambda: True
    stubs.CLOCK["now"] = L(5, 13); await rt.process_rules(L(5, 13))
    check("już ładuje (np. Wymuś): nic nie robi", not tou_calls(hass))

    hass, rt = setup(start="05:00:00", stop="05:00:00")
    stubs.CLOCK["now"] = L(5, 13); await rt.process_rules(L(5, 13))
    check("puste okno: nic", not tou_calls(hass))

    hass, rt = setup(start="22:00:00", stop="06:00:00")
    stubs.CLOCK["now"] = L(5, 13); await rt.process_rules(L(5, 13))
    check("okno przez północ: włącza", len(tou_calls(hass)) == 1, tou_calls(hass))
    print(f"GCCATCHUP PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)
asyncio.run(main())
