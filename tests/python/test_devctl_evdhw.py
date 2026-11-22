"""EV i CWU w sterowaniu urządzeniami: tryb „natychmiast”, cel sesji, sesje z kosztem, prąd, limit przyłącza, bramka temperatury CWU."""
import asyncio, sys
from common import *   # noqa
import common
from homeassistant.util import dt as dt_util
from custom_components.bms_komp_dec import devices as DV, device_ctl as DC


def calls(hass, domain, eid):
    return [c for c in hass.services.calls if c[0] == domain and c[2].get("entity_id") == eid]


def setup(cat, **kw):
    hass, c, opt, rt = build()
    dev = dict({"id": "x1", "name": "Urządzenie", "category": cat, "power_eid": "sensor.x_p", "switch_eid": "switch.x"}, **kw)
    rt.devices.set_devices([dev])
    hass.states.set("switch.x", "off")
    hass.states.set("sensor.x_p", 0, {"unit_of_measurement": "W"})
    hass.states.set("switch.bms_device_control", "on")
    hass.states.set(c.config["soc"], 80)
    return hass, c, rt


async def run(rt, t0, minutes, grid=None, hook=None):
    for m in range(minutes):
        t = t0 + timedelta(minutes=m)
        stubs.CLOCK["now"] = t
        if grid is not None:
            rt.coordinator.data = dict(rt.coordinator.data or {}, grid_power=grid(m) if callable(grid) else grid)
        if hook:
            hook(m)
        await rt.dev_ctl.tick(t)


def sanitize_part():
    d = DV.sanitize_device({"name": "w", "power_eid": "sensor.a", "switch_eid": "switch.w", "ctl_mode": "now", "category": "ev",
                            "ev_current_eid": "number.cur", "ev_min_a": 6, "ev_max_a": 99, "ev_phases": 3, "ev_target_pct": 150})
    check("sanitize: tryb now zachowany, prąd max przycięty do 80, procent do 100", d["ctl_mode"] == "now" and d["ev_max_a"] == 80 and d["ev_target_pct"] == 100 and d["ev_phases"] == 3, d)
    d = DV.sanitize_device({"name": "w", "power_eid": "sensor.a", "ev_current_eid": "number.cur", "dhw_max_c": 60})
    check("sanitize: bez przełącznika pola EV puste", d["ev_current_eid"] == "" and d["ctl_mode"] == "off", d)
    d = DV.sanitize_device({"name": "c", "power_eid": "sensor.a", "switch_eid": "switch.c", "dhw_max_c": 55, "dhw_boost_c": 70, "dhw_leg": True, "dhw_leg_c": 80,
                           "dhw_temp_eid": "sensor.t", "dhw_setpoint_eid": "switch.zly"})
    check("sanitize: limit bezpieczeństwa przycina zadaną i antylegionellę, zła encja zadanej odrzucona", d["dhw_boost_c"] == 55 and d["dhw_leg_c"] == 55 and d["dhw_setpoint_eid"] == "" and d["dhw_leg"] is True, d)
    d = DV.sanitize_device({"name": "w", "power_eid": "sensor.a", "switch_eid": "switch.w", "ev_min_a": 16, "ev_max_a": 6})
    check("sanitize: max nie mniejszy niż min", d["ev_max_a"] >= d["ev_min_a"], d)
    d = DV.sanitize_device({"name": "w", "power_eid": "sensor.a", "switch_eid": "switch.w", "ev_soc_eid": "switch.zle", "dhw_leg": "tak"})
    check("sanitize: śmieci (zła domena, nie-bool) odrzucone", d["ev_soc_eid"] == "" and d["dhw_leg"] is False, d)


async def ev_part():
    # natychmiast: włącza po 5 min warunku, bateria domu poniżej progu blokuje
    hass, c, rt = setup("ev", ctl_mode="now", ctl_power_w=1400, ctl_cond_eid="binary_sensor.car", ctl_cond_states="on",
                        ev_current_eid="number.cur", ev_max_a=16)
    hass.states.set("binary_sensor.car", "on")
    hass.states.set("number.cur", 6)
    t0 = at(2026, 6, 10, 20, 0)
    await run(rt, t0, 8, grid=500)
    check("EV natychmiast: włączenie po warunku", len(calls(hass, "switch", "switch.x")) and calls(hass, "switch", "switch.x")[0][1] == "turn_on", hass.services.calls[-3:])
    cur = calls(hass, "number", "number.cur")
    check("EV natychmiast: prąd ustawiony na maks. 16 A", cur and cur[-1][2]["value"] == 16.0, cur)
    # cel kWh: sesja 0,5 kWh, cel 0,3 → stop
    hass, c, rt = setup("ev", ctl_mode="now", ctl_power_w=1400, ev_target_kwh=0.3)
    hass.states.set("switch.x", "on")
    hass.states.set("sensor.x_p", 6000, {"unit_of_measurement": "W"})
    rt.state.setdefault("dev_ctl", {})["x1"] = {"cmd": "on", "ts": 0.0}
    t0 = at(2026, 6, 10, 20, 0)
    await run(rt, t0, 12, grid=100)
    off = [x for x in calls(hass, "switch", "switch.x") if x[1] == "turn_off"]
    st = rt.dev_ctl.status()["devices"]["x1"]
    check("EV: cel sesji (kWh) → wyłączenie, powód z celem", off and "cel sesji" in (st["reason"] or ""), (st, hass.services.calls[-3:]))
    # niska bateria domu w trybie natychmiast
    hass, c, rt = setup("ev", ctl_mode="now", ev_soc_floor=50)
    hass.states.set(c.config["soc"], 30)
    await run(rt, at(2026, 6, 10, 20, 0), 10, grid=100)
    check("EV natychmiast: bateria 30% < 50% → nie włącza", not calls(hass, "switch", "switch.x") and "bateria domu" in (rt.dev_ctl.status()["devices"]["x1"]["reason"] or ""), rt.dev_ctl.status())


async def ev_pv_part():
    hass, c, rt = setup("ev", ctl_mode="pv", ctl_power_w=1400, ctl_soc=50, ev_current_eid="number.cur", ev_max_a=16, ev_grid_limit_w=0)
    hass.states.set("number.cur", 6)
    t0 = at(2026, 6, 10, 12, 0)
    await run(rt, t0, 8, grid=-3500)
    check("EV PV: włączenie przy nadwyżce 3,5 kW", [x[1] for x in calls(hass, "switch", "switch.x")] == ["turn_on"])
    cur = calls(hass, "number", "number.cur")
    check("EV PV: prąd z nadwyżki (3500 W / 230 V = 15 A)", cur and cur[-1][2]["value"] == 15.0, cur)
    # limit przyłącza
    hass, c, rt = setup("ev", ctl_mode="now", ev_current_eid="number.cur", ev_max_a=16, ev_grid_limit_w=5000, ctl_cond_eid="")
    hass.states.set("switch.x", "on"); hass.states.set("sensor.x_p", 2300, {"unit_of_measurement": "W"})
    rt.state.setdefault("dev_ctl", {})["x1"] = {"cmd": "on", "ts": 0.0}
    await run(rt, at(2026, 6, 10, 19, 0), 3, grid=4500)
    cur = calls(hass, "number", "number.cur")
    check("EV: limit przyłącza obniża prąd poniżej 16 A", cur and 6 <= cur[-1][2]["value"] < 16, cur)


async def session_part():
    hass, c, rt = setup("ev", ctl_mode="now", ctl_cond_eid="binary_sensor.car", ctl_cond_states="on")
    hass.states.set("binary_sensor.car", "on")
    hass.states.set("sensor.x_p", 7000, {"unit_of_measurement": "W"})
    hass.states.set(c.config["price_buy"] if "price_buy" in c.config else "sensor.price", 0.8)
    t0 = at(2026, 6, 10, 20, 0)
    await run(rt, t0, 31)
    s = rt.dev_ctl.status()["devices"]["x1"]
    check("sesja: trwa, liczy kWh", s["sess"] and s["sess"]["kwh"] > 2.5, s)
    hass.states.set("binary_sensor.car", "off")
    await run(rt, t0 + timedelta(minutes=31), 2)
    s = rt.dev_ctl.status()["devices"]["x1"]
    check("sesja: po odłączeniu zapisana w last_sess", s["sess"] is None and s["last_sess"] and s["last_sess"]["kwh"] > 2.5, s)
    check("sesja: wpis w dzienniku i powiadomienie w skrzynce", any("sesja ładowania zakończona" in e.get("msg", "") for e in rt.log.last(30)))
    # bardzo krótka sesja nie jest zapisywana
    hass, c, rt = setup("ev", ctl_mode="now", ctl_cond_eid="binary_sensor.car")
    hass.states.set("binary_sensor.car", "on")
    await run(rt, at(2026, 6, 10, 20, 0), 3)
    hass.states.set("binary_sensor.car", "off")
    await run(rt, at(2026, 6, 10, 20, 3), 2)
    check("sesja poniżej 0,2 kWh pominięta", rt.dev_ctl.status()["devices"]["x1"]["last_sess"] is None)


async def dhw_part():
    kw = dict(ctl_mode="pv", ctl_power_w=2000, ctl_soc=0, dhw_temp_eid="sensor.cwu_t", dhw_max_c=60, dhw_boost_c=55)
    hass, c, rt = setup("boiler", **kw)
    hass.states.set("sensor.cwu_t", 61)
    await run(rt, at(2026, 6, 10, 12, 0), 10, grid=-4000)
    check("CWU: temperatura ≥ limit → nie włącza mimo nadwyżki", not calls(hass, "switch", "switch.x"), hass.services.calls[-3:])
    check("CWU: powód z temperaturą", "temperatura" in (rt.dev_ctl.status()["devices"]["x1"]["reason"] or ""))
    hass, c, rt = setup("boiler", **kw)
    hass.states.set("sensor.cwu_t", 40)
    await run(rt, at(2026, 6, 10, 12, 0), 8, grid=-4000)
    check("CWU: 40 °C i nadwyżka → włącza", [x[1] for x in calls(hass, "switch", "switch.x")] == ["turn_on"], hass.services.calls[-3:])
    # włączone i temperatura osiąga zadaną → wyłączenie od razu (bez 10 min odstępu)
    hass.states.set("switch.x", "on"); hass.states.set("sensor.x_p", 2000, {"unit_of_measurement": "W"})
    hass.states.set("sensor.cwu_t", 56)
    await run(rt, at(2026, 6, 10, 12, 9), 1, grid=-1000)
    check("CWU: osiągnięto zadaną → wyłączenie natychmiast", [x[1] for x in calls(hass, "switch", "switch.x")][-1] == "turn_off", calls(hass, "switch", "switch.x"))
    # komfort: tryb neg (czeka na ujemną cenę), ale 40 °C o 4:00 przy komforcie 45 °C na 6:00 → wymuś
    hass, c, rt = setup("boiler", ctl_mode="neg", ctl_power_w=2000, dhw_temp_eid="sensor.cwu_t", dhw_comfort_c=45, dhw_comfort_h=6, dhw_max_c=60)
    hass.states.set("sensor.cwu_t", 40)
    await run(rt, at(2026, 6, 10, 4, 0), 8, grid=500)
    check("CWU: komfort wymusza grzanie mimo trybu ujemnej ceny", calls(hass, "switch", "switch.x") and calls(hass, "switch", "switch.x")[0][1] == "turn_on", hass.services.calls[-3:])
    # czujnik milczy → blokada
    hass, c, rt = setup("boiler", **kw)
    hass.states.set("sensor.cwu_t", "unavailable")
    await run(rt, at(2026, 6, 10, 12, 0), 10, grid=-4000)
    check("CWU: czujnik niedostępny → nie grzeje", not calls(hass, "switch", "switch.x"))
    # antylegionella: niedziela 22.11.2026, 60 °C wymagane, temp 52, po 21:00 domyka
    hass, c, rt = setup("boiler", ctl_mode="neg", ctl_power_w=2000, dhw_temp_eid="sensor.cwu_t", dhw_max_c=65, dhw_boost_c=55, dhw_leg=True, dhw_leg_c=60, dhw_leg_dow=6)
    hass.states.set("sensor.cwu_t", 52)
    await run(rt, at(2026, 11, 22, 21, 10), 8, grid=500)
    check("antylegionella: po 21:00 w dzień cyklu włącza", calls(hass, "switch", "switch.x") and calls(hass, "switch", "switch.x")[0][1] == "turn_on", hass.services.calls[-3:])
    hass.states.set("switch.x", "on"); hass.states.set("sensor.cwu_t", 60.4)
    await run(rt, at(2026, 11, 22, 22, 0), 2, grid=500)
    check("antylegionella: po osiągnięciu cel odnotowany w tym tygodniu", rt.dev_ctl.status()["devices"]["x1"]["leg_week"] == "2026-W47", rt.dev_ctl.status())
    # zadana pompy ciepła
    hass, c, rt = setup("heat_pump_dhw", ctl_mode="now", ctl_power_w=1000, dhw_setpoint_eid="number.sp", dhw_sp_hi=55, dhw_sp_lo=45)
    hass.states.set("number.sp", 45)
    await run(rt, at(2026, 6, 10, 12, 0), 8, grid=0)
    sp = calls(hass, "number", "number.sp")
    check("pompa ciepła: podczas grzania zadana podniesiona do 55", sp and sp[-1][2]["value"] == 55.0, sp)


async def main():
    sanitize_part()
    await ev_part()
    await ev_pv_part()
    await session_part()
    await dhw_part()

asyncio.run(main())


def big_part():
    hass, c, opt, rt = build()
    at(2026, 6, 10, 12, 0)
    rt.devices.set_devices([{"id": "ev1", "name": "Auto", "category": "ev", "power_eid": "sensor.ev_p"},
                            {"id": "fr1", "name": "Pralka", "category": "washer", "power_eid": "sensor.w_p"}])
    today = dt_util.now().date()
    days = {}
    for i in range(1, 32):
        k = (today - timedelta(days=i)).isoformat()
        days[k] = 20.0
        rt.devices.data["ev1"]["daily"][k] = 1.0            # 5% zużycia domu
        rt.devices.data["fr1"]["daily"][k] = 1.0
    ids = [d["id"] for d in rt.devices.big_devices(days)]
    check("EV od 3% zużycia liczone osobno, pralka 5% nie", ids == ["ev1"], ids)


big_part()
print(f"DEVCTL_EVDHW PASS={common.PASS} FAIL={common.FAIL}")
