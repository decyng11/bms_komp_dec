"""Plan 24 h: błąd (SOC niedostępny) nie może być trzymany 15 minut."""
import asyncio, sys
sys.path.insert(0, ".")
from common import *   # noqa
import common

async def main():
    hass, c, sched = await mk((2026, 11, 3, 20, 55), 60)
    S = hass.states
    rt = rtm.BmsRuntime(hass, c, sched); c.runtime = rt
    S.set(c.config["soc"], "unavailable")
    p = await rt.refresh_plan()
    check("SOC niedostępny → plan z błędem", p and "SOC niedostępny" in (p.get("error") or ""), p)
    S.set(c.config["soc"], 60)
    at(2026, 11, 3, 20, 55, 5)
    p = await rt.refresh_plan()
    check("po 5 s nie przeliczamy ponownie (bez zalewania obliczeniami)", p.get("error"), p.get("error"))
    at(2026, 11, 3, 20, 55, 30)
    p = await rt.refresh_plan()
    check("po 30 s, gdy SOC wrócił, plan jest przeliczony", not p.get("error") and (p.get("curve") or {}).get("hours", 0) > 0, p.get("error"))
    at(2026, 11, 3, 21, 5, 0)
    n0 = rt._plan_ts
    p = await rt.refresh_plan()
    check("poprawny plan nadal jest trzymany ~15 min", rt._plan_ts == n0)
    at(2026, 11, 3, 21, 12, 0)
    p = await rt.refresh_plan()
    check("po 15 min poprawny plan jest odświeżany", rt._plan_ts != n0)
    # błąd w trakcie pracy: SOC znika → przy następnym odświeżeniu (po TTL) pojawia się błąd, a po powrocie szybko znika
    S.set(c.config["soc"], "unknown"); at(2026, 11, 3, 21, 40, 0)
    p = await rt.refresh_plan(); check("SOC znika → błąd", bool(p.get("error")))
    S.set(c.config["soc"], 58); at(2026, 11, 3, 21, 40, 25)
    p = await rt.refresh_plan(); check("SOC wraca → plan wraca w ciągu ~25 s", not p.get("error"))
    print(f"PLAN-RETRY PASS={common.PASS} FAIL={common.FAIL}")
asyncio.run(main())
