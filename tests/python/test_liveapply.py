"""Auto-stosowanie okien ładowania z planu na żywo: stabilność ≥ 30 min, cooldown, blisko startu, tryby wyłączone."""
import asyncio, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import automation
from homeassistant.util import dt as dt_util


def pp(cur, new, **kw):
    d = {"skip": False, "proposed": new, "current": cur, "confidence": "high", "reason": "x"}; d.update(kw); return d


def plan(a="11:00", b="13:00"):
    return {"proposals": {"start_grid_charge_2": pp("12:00", a), "stop_grid_charge_2": pp("13:00", b)}}


def setup():
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge_2", "12:00:00"); S.set("time.bms_stop_grid_charge_2", "13:00:00")
    S.set("switch.bms_auto_apply", "on"); S.set("switch.bms_ladowanie_z_sieci_2", "on")
    return hass, c, opt, rt, S


def cur(S):
    return S.get("time.bms_start_grid_charge_2").state[:5], S.get("time.bms_stop_grid_charge_2").state[:5]


async def main():
    t0 = dt_util.now().replace(hour=1, minute=0, second=0, microsecond=0)
    m = lambda x: t0 + timedelta(minutes=x)
    hass, c, opt, rt, S = setup()
    await automation.async_live_apply(rt, hass, plan(), m(0))
    check("pierwszy odczyt: jeszcze nie stosuje", cur(S) == ("12:00", "13:00"), cur(S))
    await automation.async_live_apply(rt, hass, plan(), m(10))
    check("po 10 min: nadal nie", cur(S) == ("12:00", "13:00"))
    await automation.async_live_apply(rt, hass, plan(), m(31))
    check("stabilna ≥ 30 min: zastosowano", cur(S) == ("11:00", "13:00"), cur(S))
    # cooldown: kolejna zmiana od razu nie przechodzi
    S.set("time.bms_start_grid_charge_2", "12:00:00")
    await automation.async_live_apply(rt, hass, plan(), m(32)); await automation.async_live_apply(rt, hass, plan(), m(70))
    check("cooldown 1 h: brak ponownego zastosowania", cur(S) == ("12:00", "13:00"), cur(S))
    await automation.async_live_apply(rt, hass, plan(), m(95))
    check("po cooldownie i stabilności: zastosowano", cur(S) == ("11:00", "13:00"), cur(S))

    # przeskakiwanie planu resetuje licznik
    hass, c, opt, rt, S = setup()
    await automation.async_live_apply(rt, hass, plan("11:00"), m(0))
    await automation.async_live_apply(rt, hass, plan("12:30"), m(20))
    await automation.async_live_apply(rt, hass, plan("12:30"), m(40))
    check("plan przeskoczył: licznik od nowa, nic nie zapisano", cur(S) == ("12:00", "13:00"), cur(S))
    await automation.async_live_apply(rt, hass, plan("12:30"), m(55))
    check("nowa wartość stabilna 35 min: zastosowano", cur(S)[0] == "12:30", cur(S))

    # wyłączone auto-stosowanie / podgląd
    hass, c, opt, rt, S = setup(); S.set("switch.bms_auto_apply", "off")
    await automation.async_live_apply(rt, hass, plan(), m(0)); await automation.async_live_apply(rt, hass, plan(), m(40))
    check("auto-stosowanie wyłączone: nic", cur(S) == ("12:00", "13:00"))
    hass, c, opt, rt, S = setup(); S.set("switch.bms_auto_apply_dry_run", "on")
    await automation.async_live_apply(rt, hass, plan(), m(0)); await automation.async_live_apply(rt, hass, plan(), m(40))
    check("tryb podglądu: nic", cur(S) == ("12:00", "13:00"))

    # okno zaczyna się za 5 min → nie ruszamy
    hass, c, opt, rt, S = setup()
    S.set("time.bms_start_grid_charge_2", f"{m(5).hour:02d}:{m(5).minute:02d}:00")
    pl = {"proposals": {"start_grid_charge_2": pp("x", "11:00"), "stop_grid_charge_2": pp("13:00", "14:00")}}
    await automation.async_live_apply(rt, hass, pl, m(0)); await automation.async_live_apply(rt, hass, pl, m(40))
    check("okno startuje za 5 min: nietknięte", cur(S)[1] == "13:00", cur(S))

    # niska pewność i skip
    hass, c, opt, rt, S = setup()
    low = {"proposals": {"start_grid_charge_2": pp("12:00", "11:00", confidence="low"), "stop_grid_charge_2": pp("13:00", "13:00")}}
    await automation.async_live_apply(rt, hass, low, m(0)); await automation.async_live_apply(rt, hass, low, m(40))
    check("niska pewność: nic", cur(S) == ("12:00", "13:00"))

    # propozycje sprzedaży nie przechodzą ścieżką na żywo
    hass, c, opt, rt, S = setup()
    S.set("time.bms_bateria_sprzedaz_start", "08:00:00"); S.set("time.bms_bateria_sprzedaz_stop", "10:00:00")
    ps = {"proposals": {"bateria_sprzedaz_start": pp("08:00", "07:00"), "bateria_sprzedaz_stop": pp("10:00", "09:00")}}
    await automation.async_live_apply(rt, hass, ps, m(0)); await automation.async_live_apply(rt, hass, ps, m(40))
    check("sprzedaż nie jest stosowana z planu na żywo", S.get("time.bms_bateria_sprzedaz_start").state[:5] == "08:00")
    print(f"LIVEAPPLY PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
