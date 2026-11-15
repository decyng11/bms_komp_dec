"""Strażnik rozjazdu: falownik ładuje z sieci bez zlecenia EMS → zgłoszenie po czasie karencji; zlecone ładowanie nie alarmuje."""
import asyncio, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from homeassistant.util import dt as dt_util


def notes(rt):
    return [e for e in (list(rt.log.entries.values()) if isinstance(rt.log.entries, dict) else list(rt.log.entries))
            if "Rozjazd" in e.get("msg", "")]


async def main():
    base = dt_util.now().replace(hour=9, minute=0, second=0, microsecond=0)
    # ładowanie włączone „z zewnątrz” (stan falownika), EMS nic nie zlecał
    hass, c, opt, rt = build(); S = hass.states
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    rt.state.pop("gc_origin", None)                       # symulacja: włączone poza EMS (np. aplikacja producenta)
    check("warunek testu: falownik ładuje z sieci", rt.grid_charging_on())
    await rt.enforce_guard(base)
    check("pierwsze wykrycie: jeszcze bez zgłoszenia", not notes(rt))
    await rt.enforce_guard(base + timedelta(minutes=5))
    check("w czasie karencji: bez zgłoszenia", not notes(rt))
    await rt.enforce_guard(base + timedelta(minutes=11))
    check("po karencji: zgłoszenie rozjazdu", len(notes(rt)) == 1, notes(rt))
    check("rozjazd tylko zgłoszony — ładowanie nietknięte", rt.grid_charging_on())
    await rt.enforce_guard(base + timedelta(minutes=20))
    check("brak powtórzenia w krótkim czasie", len(notes(rt)) == 1, notes(rt))

    # ręczna komenda = właściciel → bez zgłoszenia
    hass, c, opt, rt = build()
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    for m in (0, 5, 15, 40):
        await rt.enforce_guard(base + timedelta(minutes=m))
    check("ręczne włączenie: bez zgłoszenia", not notes(rt))
    await rt.run_command("wylacz_ladowanie_siec", source="ręcznie")
    check("wyłączenie czyści właściciela", not rt.state.get("gc_origin"))

    # okno trwa → bez zgłoszenia
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge", "09:00:00"); S.set("time.bms_stop_grid_charge", "10:00:00")
    S.set("switch.bms_ladowanie_z_sieci_1", "on")
    rt.state.pop("gc_sched", None)
    await rt.run_command("wlacz_ladowanie_siec", source="harmonogram")
    rt.state.pop("gc_origin", None)
    for m in (0, 15, 40):
        await rt.enforce_guard(base + timedelta(minutes=m))
    check("w oknie ładowania: bez zgłoszenia", not notes(rt))

    # nic nie ładuje → bez zgłoszenia i stan zerowany
    hass, c, opt, rt = build()
    for m in (0, 15, 40):
        await rt.enforce_guard(base + timedelta(minutes=m))
    check("brak ładowania: bez zgłoszenia", not notes(rt))
    print(f"MISMATCH PASS={common.PASS} FAIL={common.FAIL}")


asyncio.run(main())
