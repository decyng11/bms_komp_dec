"""0.8.8: alert „plan zakłada zejście do progu baterii” — plan 24 h przewiduje SOC przy progu falownika w ciągu 16 h."""
import asyncio, sys
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec import notify_cfg as N

def pn(h, nid): return [c for c in h.services.calls if c[0] == "persistent_notification" and c[1] == "create" and c[2].get("notification_id") == nid]
def env():
    hass, c, opt, rt = build()
    c.config["notify_service"] = "notify.mobile_app_tel"
    hass.states.set("switch.bms_notifications_enabled", "on")
    return hass, c, opt, rt

def plan(soc, floor=20.0, start="2026-11-07T08:00:00+01:00", props=None, error=None):
    n = len(soc)
    return {"error": error, "curve": {"start": start, "hours": n, "soc": soc, "floor": [floor] * n}, "proposals": props or {}}

async def main():
    check("katalog: rodzaj plan_floor istnieje, włączony, 12 h", N.CATALOG["plan_floor"][3] is True and N.CATALOG["plan_floor"][5] == 720)
    hass, c, opt, rt = env(); S = hass.states
    now = at(2026, 11, 7, 7, 40)
    S.set(c.config["soc"], 60)
    # 1. SOC dochodzi do progu o 14:00 (indeks 6), bez ładowania z sieci
    soc = [55, 50, 45, 40, 35, 30, 20.0, 20.0] + [20.0] * 10
    rt._plan = plan(soc, props={"start_grid_charge": {"proposed": None, "skip": True, "reason": "Pomiń — bateria wystarczy do rana"}})
    await rt.monitor._plan_floor(now)
    n = pn(hass, "bms_plan_floor")
    check("alert: jedno powiadomienie", len(n) == 1, n)
    m = n[0][2]["message"] if n else ""
    check("alert: godzina 14:00, dziś, próg 20%", "dziś ok. 14:00" in m and "(20%)" in m, m)
    check("alert: powód braku ładowania z planu", "Plan nie przewiduje ładowania z sieci" in m and "bateria wystarczy do rana" in m, m)
    # 2. powtórka w tym samym czasie — odstęp 12 h
    await rt.monitor._plan_floor(at(2026, 11, 7, 8, 0))
    check("alert: drugi raz w odstępie 12 h — nie", len(pn(hass, "bms_plan_floor")) == 1)
    # 3. plan z ładowaniem z sieci, które nie wystarcza
    hass, c, opt, rt = env(); S = hass.states; S.set(c.config["soc"], 60)
    rt._plan = plan(soc, props={"start_grid_charge": {"proposed": "22:00", "skip": False}, "stop_grid_charge": {"proposed": "06:00", "skip": False}})
    await rt.monitor._plan_floor(at(2026, 11, 7, 7, 40))
    m = (pn(hass, "bms_plan_floor") or [[0, 0, {"message": ""}]])[0][2]["message"]
    check("alert: zaplanowane ładowanie 22:00–06:00 nie wystarcza", "22:00–06:00" in m and "nie wystarcza" in m, m)
    # 4. próg poza horyzontem 16 h → brak alertu (indeks 20 = 04:00 następnego dnia, 20 h po starcie)
    hass, c, opt, rt = env(); S = hass.states; S.set(c.config["soc"], 60)
    far = [60.0] * 20 + [20.0] * 4
    rt._plan = plan(far)
    await rt.monitor._plan_floor(at(2026, 11, 7, 7, 40))
    check("brak alertu, gdy próg dalej niż 16 h", not pn(hass, "bms_plan_floor"))
    # 5. SOC powyżej progu przez cały plan → brak
    rt._plan = plan([60.0] * 24)
    await rt.monitor._plan_floor(at(2026, 11, 7, 7, 40))
    check("brak alertu, gdy SOC nie schodzi do progu", not pn(hass, "bms_plan_floor"))
    # 6. SOC teraz już przy progu → to robi „niski SOC”
    S.set(c.config["soc"], 21)
    rt._plan = plan(soc)
    await rt.monitor._plan_floor(at(2026, 11, 7, 7, 40))
    check("brak alertu, gdy bateria już jest przy progu", not pn(hass, "bms_plan_floor"))
    # 7. próg 0 (brak danych z falownika) nie wywołuje alertu przy SOC 0
    S.set(c.config["soc"], 60)
    rt._plan = plan([0.0] * 24, floor=0.0)
    await rt.monitor._plan_floor(at(2026, 11, 7, 7, 40))
    check("próg 0 → brak alertu", not pn(hass, "bms_plan_floor"))
    # 8. błąd planu / brak planu / śmieci
    for bad in (None, {"error": "x", "curve": {"start": "x", "soc": [1], "floor": [1]}}, {"curve": {"start": "nie-data", "soc": [10] * 3, "floor": [20] * 3}},
                {"curve": {"start": "2026-11-07T08:00:00+01:00", "soc": [10] * 3, "floor": [20]}}, {"curve": {}}):
        rt._plan = bad
        try:
            await rt.monitor._plan_floor(at(2026, 11, 7, 7, 40)); ok = True
        except Exception as err:   # noqa: BLE001
            ok = False
        check(f"odporność na złe dane planu: {str(bad)[:40]}", ok and not pn(hass, "bms_plan_floor"))
    # 9. przełącznik rodzaju wyłączony w konfiguratorze
    hass, c, opt, rt = env(); S = hass.states; S.set(c.config["soc"], 60)
    rt.state["notify_cfg"] = N.effective({"kinds": {"plan_floor": {"on": False}}})
    rt._plan = plan(soc)
    await rt.monitor._plan_floor(at(2026, 11, 7, 7, 40))
    check("wyłączone w konfiguratorze → brak powiadomienia", not pn(hass, "bms_plan_floor"))
    # 10. podpięte do pętli monitora
    import inspect
    from custom_components.bms_komp_dec import monitor as mon
    check("tick wywołuje _plan_floor", "_plan_floor" in inspect.getsource(mon.Monitor.tick) if hasattr(mon, "Monitor") else "_plan_floor" in inspect.getsource(mon))

    print(f"PLANFLOOR PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
