"""SOC poniżej ustawionej rezerwy → ładowanie od razu (a nie dopiero w nocnym oknie)."""
import asyncio, sys
sys.path.insert(0, ".")
from common import *   # noqa
import common
src = open("test_dynamic_tariff.py").read().split("async def main():")[0]
exec(compile(src, "dt", "exec"))

async def plan(rf, soc, hour=12):
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 28, hour, 0), soc=soc, buy=("bankilo", TODAY, TOMOR))
    hass.states.set("number.bms_reserve_floor_soc", rf)
    return (await sch.suggest())["proposals"].get("start_grid_charge", {})

async def main():
    st = await plan("15", 20.0)
    check("rezerwa 15%: bez zmian (ładowanie w nocnym oknie)", not st.get("skip") and st.get("proposed") == "02:00", st.get("proposed"))
    st = await plan("30", 20.0)
    check("rezerwa 30%, SOC 20%: start od razu (12:00)", not st.get("skip") and st.get("proposed") == "12:00", st.get("proposed"))
    check("uzasadnienie wspomina rezerwę", "poniżej ustawionej rezerwy" in (st.get("reason") or ""), st.get("reason"))
    st = await plan("30", 45.0)
    check("SOC nad rezerwą: bez ładowania teraz", st.get("proposed") != "12:00", st.get("proposed"))
    print(f"RESERVE PASS={common.PASS} FAIL={common.FAIL}")
asyncio.run(main())
sys.exit(1 if common.FAIL else 0)
