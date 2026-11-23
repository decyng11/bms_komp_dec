"""Pełne ładowanie co N dni: licznik, cel 100% po terminie, brak wpływu gdy wyłączone."""
import asyncio, sys
from datetime import date, timedelta
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec.helpers import switch_on
sys.path.insert(0, "/tmp")
src = open("test_dynamic_tariff.py").read().split("async def main():")[0]
exec(compile(src, "dt", "exec"))

async def main():
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 22, 20, 30), soc=30.0, buy=("bankilo", TODAY, TOMOR))
    S = hass.states
    check("wyłączone: brak terminu", rt.full_charge_due() is None)
    S.set("switch.bms_full_charge", "on"); S.set("number.bms_full_charge_days", "7")
    due = rt.full_charge_due()
    check("włączone, nigdy nie było 100%: termin minął", due is not None and due["days"] is None and due["every"] == 7, due)
    rt.fullcharge_state()["last"] = (d0 - timedelta(days=3)).isoformat()
    check("3 dni temu < 7: jeszcze nie pora", rt.full_charge_due() is None)
    rt.fullcharge_state()["last"] = (d0 - timedelta(days=7)).isoformat()
    due = rt.full_charge_due()
    check("7 dni temu: pora", due is not None and due["days"] == 7, due)
    # plan: cel 100%
    sch.full_due_fn = rt.full_charge_due
    P = (await sch.suggest())["proposals"]
    st = P.get("start_grid_charge", {})
    check("po terminie: ładowanie zaplanowane z celem 100%", not st.get("skip") and "100%" in st.get("reason", "") and "Pełne ładowanie" in st.get("reason", ""), st.get("reason"))
    rt.optimizer = sch
    # tick: SOC 100 zeruje licznik
    S.set(c.config["soc"], 100.0)
    from datetime import datetime as _dt
    await rt.fullcharge_tick(_dt(2026, 11, 22, 21, 0, tzinfo=TZ))
    check("SOC 100% zeruje licznik", rt.fullcharge_state().get("last") == d0.isoformat() and rt.full_charge_due() is None, rt.fullcharge_state())
    # wyłączone: plan bez pełnego ładowania
    S.set("switch.bms_full_charge", "off"); S.set(c.config["soc"], 30.0)
    rt.fullcharge_state()["last"] = (d0 - timedelta(days=30)).isoformat()
    P = (await sch.suggest())["proposals"]
    check("wyłączone: plan nie wspomina pełnego ładowania", "Pełne ładowanie" not in (P.get("start_grid_charge", {}).get("reason") or ""))
    print(f"FULLCHARGE PASS={common.PASS} FAIL={common.FAIL}")
asyncio.run(main())
sys.exit(1 if common.FAIL else 0)
