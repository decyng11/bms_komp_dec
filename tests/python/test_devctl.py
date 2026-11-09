"""0.8.5: sterowanie urządzeniami (nadwyżka PV / najtańsze godziny) z zabezpieczeniami."""
import asyncio, sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import devices as DV, device_ctl as DC


def sw_calls(hass, eid):
    return [c[1] for c in hass.services.calls if c[0] in ("switch", "input_boolean") and c[2].get("entity_id") == eid]


def setup(mode="pv", **kw):
    hass, c, opt, rt = build()
    dev = dict({"id": "boj", "name": "Bojler", "category": "boiler", "power_eid": "sensor.boj_p", "switch_eid": "switch.boj",
                "ctl_mode": mode, "ctl_power_w": 2000, "ctl_soc": 90}, **kw)
    rt.devices.set_devices([dev])
    hass.states.set("switch.boj", "off")
    hass.states.set("sensor.boj_p", 0, {"unit_of_measurement": "W"})
    hass.states.set("switch.bms_device_control", "on")
    hass.states.set(c.config["soc"], 95)
    return hass, c, rt


async def run(rt, t0, minutes, grid=None, step=1, hook=None):
    for m in range(0, minutes, step):
        t = t0 + timedelta(minutes=m)
        stubs.CLOCK["now"] = t
        if grid is not None:
            rt.coordinator.data = dict(rt.coordinator.data or {}, grid_power=grid(m) if callable(grid) else grid)
        if hook:
            hook(m)
        await rt.dev_ctl.tick(t)


async def main():
    # ---------- konfiguracja
    d = DV.sanitize_device({"name": "x", "power_eid": "sensor.a", "switch_eid": "light.a", "ctl_mode": "pv"})
    check("przełącznik spoza switch/input_boolean odrzucony, tryb wyłączony", d["switch_eid"] == "" and d["ctl_mode"] == "off", d)
    d = DV.sanitize_device({"name": "x", "power_eid": "sensor.a", "switch_eid": "input_boolean.a", "ctl_mode": "cheap", "ctl_hours": 99, "ctl_soc": -5})
    check("input_boolean, tryb najtańsze, wartości przycięte", d["ctl_mode"] == "cheap" and d["ctl_hours"] == 12 and d["ctl_soc"] == 0, d)
    d = DV.sanitize_device({"name": "x", "power_eid": "sensor.a", "switch_eid": "switch.a", "ctl_mode": "bzdura"})
    check("nieznany tryb → wyłączony", d["ctl_mode"] == "off")
    check("domyślnie bez sterowania", DV.sanitize_device({"name": "x", "power_eid": "sensor.a"})["ctl_mode"] == "off")

    # ---------- nadwyżka PV: 5 min warunku, potem włączenie
    hass, c, rt = setup()
    t0 = at(2026, 6, 10, 12, 0)
    await run(rt, t0, 4, grid=-3000)
    check("nadwyżka 3 kW < 5 min → jeszcze nic", sw_calls(hass, "switch.boj") == [])
    await run(rt, t0 + timedelta(minutes=4), 3, grid=-3000)
    check("po 5 min nadwyżki → włączenie", sw_calls(hass, "switch.boj") == ["turn_on"], sw_calls(hass, "switch.boj"))
    check("akcja w dzienniku", any("Bojler: włączono" in e.get("msg", "") for e in rt.log.last(20)))
    hass.states.set("switch.boj", "on"); hass.states.set("sensor.boj_p", 2000, {"unit_of_measurement": "W"})
    # urządzenie pracuje: eksport spadł do 1 kW (2 kW zjada bojler) → nadwyżka liczona z bojlerem = 3 kW → zostaje
    await run(rt, t0 + timedelta(minutes=7), 10, grid=-1000)
    check("pracuje przy własnym poborze (nadwyżka liczona z urządzeniem)", sw_calls(hass, "switch.boj") == ["turn_on"])
    # chmura: import 1500 W przy pracującym bojlerze (2 kW) → nadwyżka 0,5 kW < 50% potrzeby → wyłączenie po 5 min
    await run(rt, t0 + timedelta(minutes=17), 4, grid=1500)
    check("spadek nadwyżki < 5 min → jeszcze pracuje", sw_calls(hass, "switch.boj") == ["turn_on"])
    await run(rt, t0 + timedelta(minutes=21), 3, grid=1500)
    check("spadek nadwyżki ≥ 5 min → wyłączenie", sw_calls(hass, "switch.boj") == ["turn_on", "turn_off"], sw_calls(hass, "switch.boj"))
    hass.states.set("switch.boj", "off"); hass.states.set("sensor.boj_p", 0, {"unit_of_measurement": "W"})
    # od razu znów słońce: nie wcześniej niż 10 min od ostatniej zmiany
    await run(rt, t0 + timedelta(minutes=24), 7, grid=-3000)
    check("najwyżej jedna zmiana na 10 min", sw_calls(hass, "switch.boj") == ["turn_on", "turn_off"], sw_calls(hass, "switch.boj"))
    await run(rt, t0 + timedelta(minutes=31), 6, grid=-3000)
    check("po 10 min — ponowne włączenie", sw_calls(hass, "switch.boj") == ["turn_on", "turn_off", "turn_on"], sw_calls(hass, "switch.boj"))

    # ---------- SOC poniżej progu: nie włącza
    hass, c, rt = setup()
    hass.states.set(c.config["soc"], 70)
    await run(rt, at(2026, 6, 10, 12, 0), 15, grid=-4000)
    check("SOC 70% < 90% → bez włączania", sw_calls(hass, "switch.boj") == [])
    check("powód widoczny w statusie", "SOC" in (rt.dev_ctl.status()["devices"]["boj"]["reason"] or ""), rt.dev_ctl.status())

    # ---------- główny przełącznik wyłączony
    hass, c, rt = setup()
    hass.states.set("switch.bms_device_control", "off")
    await run(rt, at(2026, 6, 10, 12, 0), 15, grid=-4000)
    check("sterowanie wyłączone → nic nie robi", sw_calls(hass, "switch.boj") == [])
    # włączone przez BMS, potem użytkownik wyłącza główny przełącznik → BMS wyłącza swoje urządzenie
    hass.states.set("switch.bms_device_control", "on")
    await run(rt, at(2026, 6, 10, 12, 20), 7, grid=-4000)
    hass.states.set("switch.boj", "on")
    hass.states.set("switch.bms_device_control", "off")
    await run(rt, at(2026, 6, 10, 12, 30), 1, grid=-4000)
    check("po wyłączeniu sterowania BMS wyłącza to, co włączył", sw_calls(hass, "switch.boj") == ["turn_on", "turn_off"], sw_calls(hass, "switch.boj"))

    # ---------- urządzenie włączone ręcznie: BMS go nie wyłącza
    hass, c, rt = setup()
    hass.states.set("switch.boj", "on")
    await run(rt, at(2026, 6, 10, 12, 0), 30, grid=2000)
    check("włączone ręcznie (nie przez BMS) → BMS nie wyłącza", sw_calls(hass, "switch.boj") == [])

    # ---------- ręczne przełączenie wbrew BMS: do końca dnia bez sterowania
    hass, c, rt = setup()
    t0 = at(2026, 6, 10, 12, 0)
    await run(rt, t0, 7, grid=-4000)
    check("włączone przez BMS", sw_calls(hass, "switch.boj") == ["turn_on"])
    hass.states.set("switch.boj", "off")                     # ktoś wyłączył ręcznie
    await run(rt, t0 + timedelta(minutes=6), 1, grid=-4000)
    check("od razu po komendzie — czekamy na odświeżenie stanu", not rt.dev_ctl.status()["devices"]["boj"]["manual"])
    await run(rt, t0 + timedelta(minutes=9), 60, grid=-4000)
    check("ręczne wyłączenie → BMS nie włącza do końca dnia", sw_calls(hass, "switch.boj") == ["turn_on"] and rt.dev_ctl.status()["devices"]["boj"]["manual"], sw_calls(hass, "switch.boj"))
    await run(rt, at(2026, 6, 11, 12, 0), 7, grid=-4000)
    check("następnego dnia sterowanie wraca", sw_calls(hass, "switch.boj") == ["turn_on", "turn_on"], sw_calls(hass, "switch.boj"))

    # ---------- zanik sieci: wyłącza od razu i nie włącza
    hass, c, rt = setup()
    t0 = at(2026, 6, 10, 12, 0)
    await run(rt, t0, 7, grid=-4000)
    hass.states.set("switch.boj", "on")
    rt.state["grid_outage"] = {"since": t0.timestamp()}
    await run(rt, t0 + timedelta(minutes=8), 1, grid=-4000)
    check("zanik sieci → natychmiastowe wyłączenie", sw_calls(hass, "switch.boj") == ["turn_on", "turn_off"], sw_calls(hass, "switch.boj"))
    hass.states.set("switch.boj", "off")
    await run(rt, t0 + timedelta(minutes=20), 20, grid=-4000)
    check("zanik sieci → nie włącza", sw_calls(hass, "switch.boj") == ["turn_on", "turn_off"])

    # ---------- dzienny limit pracy
    hass, c, rt = setup(ctl_max_h=0.5)
    t0 = at(2026, 6, 10, 12, 0)
    def keep_on(m):
        if sw_calls(hass, "switch.boj")[-1:] == ["turn_on"]:
            hass.states.set("switch.boj", "on")
    await run(rt, t0, 45, grid=-4000, hook=keep_on)
    calls = sw_calls(hass, "switch.boj")
    check("limit 0,5 h → wyłączenie po ok. 30 min pracy", calls == ["turn_on", "turn_off"], calls)
    on_h = rt.dev_ctl.status()["devices"]["boj"]["on_h"]
    check("czas pracy liczony", 0.45 <= on_h <= 0.55, on_h)

    # ---------- najtańsze godziny (taryfa dynamiczna w planie)
    hass, c, rt = setup(mode="cheap", ctl_hours=2, ctl_power_w=2000)
    t0 = at(2026, 6, 10, 20, 0)
    buy = [0.9] * 30
    buy[6] = buy[7] = 0.2                                     # 02:00–04:00 najtaniej (start krzywej 20:00)
    rt._plan = {"curve": {"start": "2026-06-10T20:00:00+02:00", "pv": [0.0] * 30, "load": [0.5] * 30, "buy": buy, "sell": [0.3] * 30}}
    await run(rt, t0, 60, grid=500)
    st = rt.dev_ctl.status()["devices"]["boj"]
    check("okno najtańszych godzin 02:00–04:00", st["window"] and st["window"][0][11:16] == "02:00" and st["window"][1][11:16] == "04:00", st)
    check("przed oknem nic", sw_calls(hass, "switch.boj") == [])
    await run(rt, at(2026, 6, 11, 2, 0), 5, grid=500, hook=keep_on)
    check("w oknie → włączenie", sw_calls(hass, "switch.boj") == ["turn_on"], sw_calls(hass, "switch.boj"))
    # plan się zmienia w trakcie okna — okno nie przesuwa się
    buy2 = list(buy); buy2[6] = buy2[7] = 0.9; buy2[10] = buy2[11] = 0.1
    rt._plan["curve"]["buy"] = buy2
    await run(rt, at(2026, 6, 11, 2, 5), 110, grid=500, hook=keep_on)
    check("plan zmienił się w trakcie okna — urządzenie pracuje do końca okna", sw_calls(hass, "switch.boj") == ["turn_on"], sw_calls(hass, "switch.boj"))
    await run(rt, at(2026, 6, 11, 3, 55), 20, grid=500, hook=keep_on)
    calls = sw_calls(hass, "switch.boj")
    check("koniec okna (04:00) → wyłączenie; okno nie przesunięte w trakcie", calls[:2] == ["turn_on", "turn_off"], calls)
    off_t = [e for e in rt.log.last(30) if "Bojler: wyłączono" in e.get("msg", "")]
    check("wyłączenie z powodem w dzienniku", bool(off_t))

    # ---------- najtańsze okno: PV liczone po cenie sprzedaży
    curve = {"start": "2026-06-10T08:00:00+02:00", "pv": [0, 0, 0, 0, 4, 4, 0, 0], "load": [0.5] * 8, "buy": [0.6] * 8, "sell": [0.2] * 8}
    bw = DC.best_window(curve, 2, 2.0)
    check("najtańsze okno = nadwyżka PV 12:00–14:00", bw and bw[0].hour == 12 and bw[1].hour == 14 and bw[3] == 4.0, bw)
    check("brak planu → brak okna", DC.best_window(None, 2, 1.0) is None)

    # ---------- oszczędzanie energii przy niskim SOC
    d = DV.sanitize_device({"name": "x", "power_eid": "sensor.a", "switch_eid": "switch.a", "ctl_no_shed": True})
    check("ctl_no_shed zapisywane", d["ctl_no_shed"] is True and DV.sanitize_device({"name": "x", "power_eid": "sensor.a"})["ctl_no_shed"] is False)
    def shed_env(no_shed=False, thr=30, mode="off", soc=50, sw="on"):
        hass, c, rt = setup(mode, ctl_no_shed=no_shed)
        hass.states.set("switch.boj", sw); hass.states.set("number.bms_device_shed_soc", thr); hass.states.set(c.config["soc"], soc)
        return hass, c, rt
    hass, c, rt = shed_env()
    t0 = at(2026, 11, 9, 5, 0)
    await run(rt, t0, 10)
    check("SOC wyżej niż próg: nic", sw_calls(hass, "switch.boj") == [])
    hass.states.set(c.config["soc"], 25)
    await run(rt, t0 + timedelta(minutes=10), 4)
    check("SOC < próg krócej niż 5 min: jeszcze nic", sw_calls(hass, "switch.boj") == [])
    await run(rt, t0 + timedelta(minutes=14), 4)
    check("po 5 min wyłącza urządzenie (też bez trybu sterowania)", sw_calls(hass, "switch.boj") == ["turn_off"], sw_calls(hass, "switch.boj"))
    hass.states.set("switch.boj", "off")
    hass.states.set(c.config["soc"], 33)
    await run(rt, t0 + timedelta(minutes=18), 10)
    check("SOC 33% < próg+5: nadal wyłączone", sw_calls(hass, "switch.boj") == ["turn_off"])
    hass.states.set(c.config["soc"], 36)
    await run(rt, t0 + timedelta(minutes=28), 10)
    check("po odbiciu SOC włącza z powrotem", sw_calls(hass, "switch.boj") == ["turn_off", "turn_on"], sw_calls(hass, "switch.boj"))
    hass.states.set("switch.boj", "on")
    await run(rt, t0 + timedelta(minutes=40), 10)
    check("po powrocie bez ponownego wyłączania", sw_calls(hass, "switch.boj") == ["turn_off", "turn_on"])
    # nie dotyczy
    hass, c, rt = shed_env(no_shed=True, soc=20)
    await run(rt, at(2026, 11, 9, 5, 0), 12)
    check("„nie dotyczy”: nie wyłącza", sw_calls(hass, "switch.boj") == [])
    # próg 0 = wyłączone, główny przełącznik
    hass, c, rt = shed_env(thr=0, soc=5); await run(rt, at(2026, 11, 9, 5, 0), 12)
    check("próg 0: nie wyłącza", sw_calls(hass, "switch.boj") == [])
    hass, c, rt = shed_env(soc=5); hass.states.set("switch.bms_device_control", "off"); await run(rt, at(2026, 11, 9, 5, 0), 12)
    check("sterowanie urządzeniami wyłączone: nie wyłącza", sw_calls(hass, "switch.boj") == [])
    # urządzenie już wyłączone — nie włączamy go po powrocie
    hass, c, rt = shed_env(soc=5, sw="off"); t0 = at(2026, 11, 9, 5, 0); await run(rt, t0, 12)
    hass.states.set(c.config["soc"], 60); await run(rt, t0 + timedelta(minutes=12), 12)
    check("wyłączone przed oszczędzaniem: bez komend", sw_calls(hass, "switch.boj") == [])
    # ręczne włączenie w trakcie oszczędzania — szanujemy do końca dnia
    hass, c, rt = shed_env(soc=5); t0 = at(2026, 11, 9, 5, 0); await run(rt, t0, 8)
    hass.states.set("switch.boj", "on"); await run(rt, t0 + timedelta(minutes=8), 20)
    check("włączone ręcznie: nie wyłączamy ponownie tego dnia", sw_calls(hass, "switch.boj") == ["turn_off"], sw_calls(hass, "switch.boj"))

    print(f"DEVCTL PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
