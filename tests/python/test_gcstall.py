"""Ostrzeżenie: okno ładowania z sieci trwa, a bateria nie ładuje."""
import asyncio, sys
from common import *   # noqa
import common

async def main():
    hass, c, opt, rt = build()
    c.config["notify_service"] = "notify.mobile_app_tel"
    hass.states.set("switch.bms_notifications_enabled", "on")
    sent = []
    async def fake_send(kind, title, msg, **kw): sent.append(kind); return True
    rt.monitor.notifier.send = fake_send
    rt.state["grid_target_plan"] = {"target": 40}
    st = {"soc": 29.0, "on": True, "bp": -890.0}
    rt.soc = lambda: st["soc"]
    rt.grid_charging_on = lambda: st["on"]
    rt.battery_sign = lambda: {"sign": 1}
    rt.coordinator.data = {"battery_power": st["bp"]}
    async def step(t, **kw):
        st.update(kw); rt.coordinator.data = {"battery_power": st["bp"]}
        await rt.monitor._grid_charge_stalled(at(2026, 11, 9, 5, t))
    await step(0); await step(3)
    check("przed 5 min cicho", sent == [], sent)
    await step(6)
    check("po 5 min ostrzeżenie", sent == ["grid_charge_stalled"], sent)
    await step(8); await step(9)
    check("tylko raz", len(sent) == 1, sent)
    sent.clear(); rt.state["gc_stall"] = {}
    await step(10, bp=2000.0); await step(20)
    check("ładuje się: cicho", sent == [], sent)
    await step(30, bp=-800.0, soc=41.0); await step(45)
    check("SOC przy celu: cicho", sent == [], sent)
    await step(50, soc=29.0, on=False); await step(58)
    check("okno wyłączone: cicho", sent == [], sent)
    print(f"GCSTALL PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)
asyncio.run(main())
