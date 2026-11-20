"""„Na ile godzin starczy baterii”: wzór, formatowanie, wygładzanie poboru, atrybut czujnika, powiadomienia przy zaniku sieci."""
import asyncio, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import autonomy as AU
from homeassistant.util import dt as dt_util
from custom_components.bms_komp_dec.sensor import BmsRuntimeSensor


def pure():
    e = AU.estimate(60, 20, 10.0, 500)
    check("10 kWh, 60% → 20%: 4 kWh × 0,92 / 0,5 kW ≈ 7,4 h", e and abs(e["hours"] - 7.4) < 0.05 and abs(e["usable_kwh"] - 3.68) < 0.01 and e["load_w"] == 500 and not e["capped"], e)
    check("SOC poniżej progu → 0 h", AU.estimate(15, 20, 10.0, 500)["hours"] == 0.0)
    check("SOC > 100 przycięty do 100", AU.estimate(150, 20, 10.0, 1000)["usable_kwh"] == AU.estimate(100, 20, 10.0, 1000)["usable_kwh"])
    e = AU.estimate(100, 10, 15.0, 0)
    check("pobór 0 → dzielenie przez minimum 50 W, wynik ograniczony do 72 h", e["hours"] == AU.MAX_HOURS and e["capped"], e)
    for args in ((None, 20, 10, 500), (60, None, 10, 500), (60, 20, 0, 500), (60, 20, 10, -5), ("x", 20, 10, 500), (60, 20, 10, float("nan")), (True, 20, 10, 500)):
        check(f"brak danych {args} → None", AU.estimate(*args) is None)
    check("ujemny próg traktowany jak 0", AU.estimate(50, -10, 10, 1000)["usable_kwh"] == AU.estimate(50, 0, 10, 1000)["usable_kwh"])

    f = AU.fmt_hours
    check("fmt: 14 h", f(14.2) == "14 h" and f(10.0) == "10 h")
    check("fmt: 1 h 20 min", f(1 + 20 / 60) == "1 h 20 min")
    check("fmt: pełne godziny poniżej 10", f(3.0) == "3 h" and f(3.99) == "4 h")
    check("fmt: 40 min", f(40 / 60) == "40 min")
    check("fmt: poniżej 10 min", f(0.05) == "mniej niż 10 min" and f(0.0) == "mniej niż 10 min")
    check("fmt: ponad 3 doby", f(100, True) == "ponad 3 doby" and f(72.0) == "ponad 3 doby")
    check("fmt: 59,9 min → „1 h”, nie „60 min”", f(0.9999) == "1 h", f(0.9999))
    check("fmt: minuty do 5", f(43 / 60) == "45 min" and f(2 + 12 / 60) == "2 h 10 min", (f(43 / 60), f(2 + 12 / 60)))

    check("ema: brak poprzedniej → pomiar", AU.ema(None, 800, 10) == 800.0)
    v = 200.0
    for _ in range(6):                                       # minuta pomiarów 3 kW co 10 s
        v = AU.ema(v, 3000, 10)
    check("ema: minuta czajnika 3 kW podnosi średnią tylko częściowo (≈ 200 → < 1200)", 200 < v < 1200, v)
    v = 200.0
    for _ in range(360):                                     # godzina stałego 1 kW
        v = AU.ema(v, 1000, 10)
    check("ema: po godzinie stałego poboru zbiega do 1 kW", abs(v - 1000) < 5, v)
    check("ema: przerwa > godziny → bierze nowy pomiar", AU.ema(200, 900, 7200) == 900.0)
    check("ema: zły pomiar zostawia poprzednią", AU.ema(200, "x", 10) == 200.0 and AU.ema(200, -5, 10) == 200.0 and AU.ema(200, float("nan"), 10) == 200.0)
    check("ema: brak obu → None", AU.ema(None, None, 10) is None)

    est = AU.estimate(60, 20, 10.0, 1500)                    # usable 3,68 kWh, 1,5 kW → 2,45 h
    hint = AU.extend_hint(est, [("Bojler", 1200.0), ("Pralka", 300.0)])
    check("podpowiedź: wyłączenie bojlera 1,2 kW wydłuża do ok. 12 h", "„Bojler”" in hint and "1,2 kW" in hint and "12 h" in hint, hint)
    check("podpowiedź: mały odbiornik (< 300 W) nic nie proponuje", AU.extend_hint(est, [("Lampka", 100.0)]) == "")
    check("podpowiedź: brak urządzeń → pusto", AU.extend_hint(est, []) == "" and AU.extend_hint(est, None) == "" and AU.extend_hint(None, [("a", 999.0)]) == "")
    check("podpowiedź: bez zysku (odbiornik prawie nie zmienia czasu) → pusto", AU.extend_hint(AU.estimate(60, 20, 10.0, 5000), [("Czajnik", 300.0)]) == "")


def setup_rt(soc=60.0, load=500.0, floor=20.0):
    hass, c, opt, rt = build(); S = hass.states
    S.set(c.config["soc"], soc)
    c.data = dict(c.data or {}, load_power=load)
    rt.inverter_floor = lambda: {"hourly": [floor] * 24, "source": "test"}
    return hass, c, rt


async def runtime_part():
    # ---------- wygładzony pobór i szacunek
    hass, c, rt = setup_rt()
    t = dt_util.now().replace(microsecond=0)
    check("bez pomiarów: brak szacunku", rt.autonomy() is None)
    rt._track_load(t)
    a = rt.autonomy()
    cap = float(rt.optimizer.config.get("battery_capacity_kwh", 10.0))
    check("pierwszy pomiar 500 W daje szacunek", a is not None and a["load_w"] == 500 and a["floor"] == 20.0 and a["soc"] == 60.0 and a["text"], a)
    for i in range(1, 7):                                     # minuta czajnika 3 kW
        c.data["load_power"] = 3000
        rt._track_load(t + timedelta(seconds=10 * i))
    a2 = rt.autonomy()
    check("minuta czajnika nie zmienia szacunku drastycznie (pobór wygładzony < 1,2 kW)", a2["load_w"] < 1200 and a2["hours"] > a["hours"] * 0.35, (a, a2))
    # brak load_power: zostaje ostatnia średnia
    c.data["load_power"] = None
    rt._track_load(t + timedelta(seconds=80))
    check("brak odczytu poboru: zostaje poprzednia średnia", rt.autonomy() is not None)
    hass.states.set(c.config["soc"], "unavailable")
    check("brak SOC: brak szacunku", rt.autonomy() is None)

    # próg z falownika niedostępny → zapas z ustawień
    hass, c, rt = setup_rt()
    rt.inverter_floor = lambda: (_ for _ in ()).throw(RuntimeError("x"))
    rt._track_load(dt_util.now())
    a = rt.autonomy()
    check("brak progu falownika: próg z ustawień (rezerwa minimalna)", a is not None and a["floor"] == 15.0, a)

    # ---------- atrybut czujnika reserve_soc
    hass, c, rt = setup_rt()
    rt._track_load(dt_util.now())
    sens = BmsRuntimeSensor(c, "reserve_soc", "x", None, "mdi:x"); sens.coordinator = c
    attrs = sens.extra_state_attributes or {}
    check("czujnik: atrybut autonomy z tekstem i liczbami", isinstance(attrs.get("autonomy"), dict) and attrs["autonomy"].get("text") and attrs["autonomy"]["hours"] > 0, attrs.get("autonomy"))
    check("autonomy jest nierejestrowany w historii", "autonomy" in BmsRuntimeSensor._unrecorded_attributes)

    # ---------- powiadomienie o zaniku sieci
    hass, c, rt = setup_rt(soc=60.0, load=1500.0)
    c.config["notify_service"] = "notify.mobile_app_tel"
    hass.states.set("switch.bms_notifications_enabled", "on")
    hass.states.set("sensor.bojler_moc", 1200, {"unit_of_measurement": "W"})
    rt.devices.set_devices([{"id": "boj", "name": "Bojler", "category": "boiler", "power_eid": "sensor.bojler_moc"}])
    rt._track_load(dt_util.now())
    from custom_components.bms_komp_dec.const import CONF_GRID_VOLTAGE_L1
    hass.states.set(c.config[CONF_GRID_VOLTAGE_L1] if CONF_GRID_VOLTAGE_L1 in c.config else "sensor.inverter_grid_voltage_l1", 0)
    c.get_float_opt = lambda key: 0.0 if key == CONF_GRID_VOLTAGE_L1 else None
    t0 = at(2026, 11, 20, 14, 0)
    await rt.monitor._grid_outage(t0)
    await rt.monitor._grid_outage(t0 + timedelta(seconds=90))
    pn = [x for x in hass.services.calls if x[0] == "persistent_notification" and x[1] == "create"]
    msg = pn[0][2]["message"] if pn else ""
    check("zanik sieci: powiadomienie z czasem pracy baterii", "Bateria wystarczy na ok." in msg and "przy poborze 1500 W, bez PV" in msg, msg)
    check("zanik sieci: propozycja wyłączenia największego odbiornika", "Wyłączenie „Bojler”" in msg and "wydłuży" in msg, msg)

    # ---------- bez danych o baterii powiadomienie działa jak dotąd
    hass, c, rt = setup_rt()
    c.config["notify_service"] = "notify.mobile_app_tel"
    hass.states.set("switch.bms_notifications_enabled", "on")
    from custom_components.bms_komp_dec.const import CONF_GRID_VOLTAGE_L1
    c.get_float_opt = lambda key: 0.0 if key == CONF_GRID_VOLTAGE_L1 else None
    rt._load_ema = None
    await rt.monitor._grid_outage(t0)
    await rt.monitor._grid_outage(t0 + timedelta(seconds=90))
    pn = [x for x in hass.services.calls if x[0] == "persistent_notification" and x[1] == "create"]
    check("zanik sieci bez poboru: powiadomienie bez linii o czasie, bez błędu", pn and "Bateria wystarczy" not in pn[0][2]["message"] and "zanik sieci" in pn[0][2]["title"].lower(), pn)


async def main():
    pure()
    await runtime_part()


asyncio.run(main())
print(f"AUTONOMY PASS={common.PASS} FAIL={common.FAIL}")
