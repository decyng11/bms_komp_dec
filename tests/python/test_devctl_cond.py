"""Warunek uruchomienia urządzenia (np. „auto podłączone”): oczyszczanie pól, włączanie, wyłączanie, niedostępna encja, status."""
import asyncio, sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import devices as DV
from custom_components.bms_komp_dec.const import DEFAULT_PRICE_BUY_ENTITY as BUY


def sw_calls(hass, eid="switch.boj"):
    return [c[1] for c in hass.services.calls if c[0] in ("switch", "input_boolean") and c[2].get("entity_id") == eid]


def setup(mode="neg", **kw):
    hass, c, opt, rt = build()
    dev = dict({"id": "boj", "name": "Bojler", "category": "boiler", "power_eid": "sensor.boj_p", "switch_eid": "switch.boj",
                "ctl_mode": mode, "ctl_power_w": 2000, "ctl_soc": 90}, **kw)
    rt.devices.set_devices([dev])
    hass.states.set("switch.boj", "off")
    hass.states.set("sensor.boj_p", 0, {"unit_of_measurement": "W"})
    hass.states.set("switch.bms_device_control", "on")
    hass.states.set(c.config["soc"], 95)
    hass.states.set(BUY, 0.5)
    return hass, c, rt


async def run(rt, t0, minutes, grid=500, hook=None):
    for m in range(minutes):
        t = t0 + timedelta(minutes=m)
        stubs.CLOCK["now"] = t
        rt.coordinator.data = dict(rt.coordinator.data or {}, grid_power=grid(m) if callable(grid) else grid)
        if hook:
            hook(m)
        await rt.dev_ctl.tick(t)


def follow(hass):
    def _f(m):
        last = sw_calls(hass)[-1:]
        if last:
            hass.states.set("switch.boj", "on" if last[0] == "turn_on" else "off")
    return _f


def pure():
    base = {"category": "ev", "power_eid": "sensor.p", "switch_eid": "switch.auto", "ctl_mode": "neg"}
    d = DV.sanitize_device(dict(base, ctl_cond_eid="binary_sensor.auto_podlaczone", ctl_cond_states=" ON , Charging,on, "))
    check("warunek: encja i stany znormalizowane", d["ctl_cond_eid"] == "binary_sensor.auto_podlaczone" and d["ctl_cond_states"] == "on,charging", d)
    d = DV.sanitize_device(dict(base))
    check("brak warunku: pusta encja, stan domyślny on", d["ctl_cond_eid"] == "" and d["ctl_cond_states"] == "on", d)
    for bad in ("sensor", "Sensor.X Y", "x.y.z", "binary_sensor.", "../etc", 5, None, ["a"], "sensor.<img>"):
        d = DV.sanitize_device(dict(base, ctl_cond_eid=bad, ctl_cond_states="home"))
        check(f"zła encja warunku {bad!r} → warunek wyłączony", d["ctl_cond_eid"] == "" and d["ctl_cond_states"] == "on", d)
    d = DV.sanitize_device(dict(base, switch_eid="", ctl_mode="off", ctl_cond_eid="binary_sensor.x"))
    check("bez przełącznika warunek jest odrzucany", d["ctl_cond_eid"] == "", d)
    d = DV.sanitize_device(dict(base, ctl_cond_eid="sensor.x", ctl_cond_states=",".join(f"s{i}" for i in range(20))))
    check("liczba stanów ograniczona", len(d["ctl_cond_states"].split(",")) == DV.COND_MAX_STATES, d["ctl_cond_states"])
    d = DV.sanitize_device(dict(base, ctl_cond_eid="sensor.x", ctl_cond_states="a" * 200))
    check("długość stanu ograniczona", len(d["ctl_cond_states"]) <= 30, d["ctl_cond_states"])
    d = DV.sanitize_device(dict(base, ctl_cond_eid="sensor.x", ctl_cond_states=" , ,"))
    check("same przecinki → domyślnie on", d["ctl_cond_states"] == "on", d)
    d = DV.sanitize_device(dict(base, ctl_cond_eid="sensor.x", ctl_cond_states=123))
    check("liczba zamiast napisu nie wywraca", d["ctl_cond_states"] == "123", d)
    d2 = DV.sanitize_device(d)
    check("sanitize jest idempotentne", d2["ctl_cond_eid"] == d["ctl_cond_eid"] and d2["ctl_cond_states"] == d["ctl_cond_states"])


async def main():
    pure()
    t0 = at(2026, 6, 10, 13, 0)

    # ---------- bez warunku zachowanie bez zmian
    hass, c, rt = setup(ctl_cond_eid="")
    hass.states.set(BUY, -0.2)
    await run(rt, t0, 8, hook=follow(hass))
    check("bez warunku: włącza jak dotąd", sw_calls(hass) == ["turn_on"], sw_calls(hass))

    # ---------- warunek niespełniony: nie włącza, powód widoczny
    hass, c, rt = setup(ctl_cond_eid="binary_sensor.auto", ctl_cond_states="on")
    hass.states.set("binary_sensor.auto", "off", {"friendly_name": "Auto podłączone"})
    hass.states.set(BUY, -0.2)
    await run(rt, t0, 10, hook=follow(hass))
    st = rt.dev_ctl.status()["devices"]["boj"]
    check("warunek niespełniony: bez włączenia", sw_calls(hass) == [], sw_calls(hass))
    check("status: powód z nazwą encji i stanem", "Auto podłączone = off" in (st.get("reason") or "") and "potrzebne: on" in st["reason"], st)
    check("status: blok cond z ok=False", st["cond"] == {"eid": "binary_sensor.auto", "ok": False, "why": st["reason"]}, st["cond"])

    # ---------- warunek się spełnia: włącza
    hass.states.set("binary_sensor.auto", "on", {"friendly_name": "Auto podłączone"})
    await run(rt, t0 + timedelta(minutes=10), 8, hook=follow(hass))
    check("warunek spełniony + ujemna cena → włączenie", sw_calls(hass) == ["turn_on"], sw_calls(hass))
    st = rt.dev_ctl.status()["devices"]["boj"]
    check("status: cond ok=True", st["cond"]["ok"] is True and st["cond"]["why"] is None, st["cond"])

    # ---------- warunek przestaje być spełniony (auto odpięte): wyłącza od razu, bez czekania 10 minut
    hass.states.set("binary_sensor.auto", "off", {"friendly_name": "Auto podłączone"})
    await run(rt, t0 + timedelta(minutes=18), 2, hook=follow(hass))
    check("auto odpięte → natychmiastowe wyłączenie (przed upływem 10 min od włączenia)", sw_calls(hass) == ["turn_on", "turn_off"], sw_calls(hass))
    check("powód wyłączenia w dzienniku", any("wyłączono — warunek: Auto podłączone = off" in e.get("msg", "") for e in rt.log.last(10)), [e.get("msg") for e in rt.log.last(4)])

    # ---------- encja warunku niedostępna / nieistniejąca → nie włączamy
    for st_val in ("unavailable", "unknown", ""):
        hass, c, rt = setup(ctl_cond_eid="binary_sensor.auto")
        hass.states.set("binary_sensor.auto", st_val)
        hass.states.set(BUY, -0.2)
        await run(rt, t0, 10, hook=follow(hass))
        check(f"encja warunku „{st_val}” → bez włączenia", sw_calls(hass) == [] and "niedostępny" in (rt.dev_ctl.status()["devices"]["boj"].get("reason") or ""), rt.dev_ctl.status())
    hass, c, rt = setup(ctl_cond_eid="binary_sensor.nie_ma")
    hass.states.set(BUY, -0.2)
    await run(rt, t0, 10, hook=follow(hass))
    check("encja warunku nie istnieje → bez włączenia", sw_calls(hass) == [], sw_calls(hass))

    # ---------- kilka dozwolonych stanów, wielkość liter
    hass, c, rt = setup(ctl_cond_eid="sensor.wallbox", ctl_cond_states="charging, Ready")
    hass.states.set("sensor.wallbox", "READY")
    hass.states.set(BUY, -0.2)
    await run(rt, t0, 8, hook=follow(hass))
    check("stan „READY” pasuje do „ready” (bez względu na wielkość liter)", sw_calls(hass) == ["turn_on"], sw_calls(hass))
    hass2, c2, rt2 = setup(ctl_cond_eid="sensor.wallbox", ctl_cond_states="charging, Ready")
    hass2.states.set("sensor.wallbox", "disconnected")
    hass2.states.set(BUY, -0.2)
    await run(rt2, t0, 8, hook=follow(hass2))
    st = rt2.dev_ctl.status()["devices"]["boj"]
    check("stan spoza listy → bez włączenia, powód z listą stanów", sw_calls(hass2) == [] and "charging lub ready" in (st.get("reason") or ""), st)

    # ---------- warunek dotyczy też trybu „pv”
    hass, c, rt = setup(mode="pv", ctl_cond_eid="binary_sensor.auto")
    hass.states.set("binary_sensor.auto", "off")
    hass.states.set(c.config["soc"], 95)
    await run(rt, t0, 12, grid=-3000, hook=follow(hass))
    check("tryb pv: nadwyżka jest, ale warunek nie → bez włączenia", sw_calls(hass) == [], sw_calls(hass))
    hass.states.set("binary_sensor.auto", "on")
    await run(rt, t0 + timedelta(minutes=12), 12, grid=-3000, hook=follow(hass))
    check("tryb pv: warunek spełniony → włączenie", sw_calls(hass) == ["turn_on"], sw_calls(hass))

    # ---------- urządzenie włączone ręcznie nie jest ruszane mimo niespełnionego warunku (nie wyłączamy cudzych)
    hass, c, rt = setup(ctl_cond_eid="binary_sensor.auto")
    hass.states.set("binary_sensor.auto", "off")
    hass.states.set("switch.boj", "on")
    hass.states.set(BUY, 0.5)
    await run(rt, t0, 15, hook=follow(hass))
    check("włączone ręcznie: EMS go nie wyłącza", sw_calls(hass) == [], sw_calls(hass))

    # ---------- status bez warunku: cond = None
    hass, c, rt = setup()
    check("status bez warunku: cond None", rt.dev_ctl.status()["devices"]["boj"]["cond"] is None)

    print(f"DEVCTL_COND PASS={common.PASS} FAIL={common.FAIL}")


asyncio.run(main())
