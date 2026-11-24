"""Usterki czujników (sensorfault), zdanie „plan na dziś”, limit eksportu GoodWe i kroki wdrożenia marki."""
import asyncio, sys
from common import *   # noqa
from custom_components.bms_komp_dec import sensorfault as SF, planview as PV, brands as BR, health as HL
GW_MODES = ["auto", "charge_pv", "discharge_pv", "import_ac", "export_ac", "conserve", "battery_standby", "charge_battery", "stopped"]


def goodwe(hass, c):
    S = hass.states
    for e in ("select.inverter_work_mode", "number.inverter_battery_max_charging_current", "number.inverter_export_surplus_power",
              "select.inverter_time_of_use"):
        S._s.pop(e, None)
    c.config["work_mode"] = "select.goodwe_ems_mode"
    S.set("select.goodwe_ems_mode", "auto", {"options": GW_MODES})
    S.set("select.goodwe_operation_mode", "eco", {"options": ["general", "eco"]})
    S.set("number.goodwe_ems_power_limit", 0, {"min": 0, "max": 10000})
    BR.reset_cache()


def run_sf():
    st = SF.new_state(); t = 1_000_000.0
    # PV = 0 przy słonecznej prognozie: usterka dopiero po PV_ZERO_MIN
    f = []
    for i in range(100):
        f = SF.update(st, t + i * 60, 12, 0.0, 50.0, 0.0, 8.0)
    check("PV 0 przez >90 min w słoneczny dzień → usterka pv_zero", [x["kind"] for x in f] == ["pv_zero"], f)
    check("usterka PV wyłącza zaufanie do korekcji na żywo", SF.pv_untrusted(f))
    f = SF.update(st, t + 101 * 60, 12, 1500.0, 50.0, 0.0, 8.0)
    check("PV wróciło → usterka znika", f == [], f)
    st = SF.new_state()
    for i in range(100):
        f = SF.update(st, t + i * 60, 12, 0.0, 50.0, 0.0, 1.5)
    check("słaba prognoza (1.5 kWh) → zero PV nie jest usterką", f == [], f)
    st = SF.new_state()
    for i in range(100):
        f = SF.update(st, t + i * 60, 22, 0.0, 50.0, 0.0, 8.0)
    check("noc → brak usterki", f == [], f)
    st = SF.new_state()
    for i in range(100):
        f = SF.update(st, t + i * 60, 12, 0.0, 50.0, 0.0, None)
    check("brak prognozy → brak usterki", f == [], f)
    # SOC zamarznięty przy przepływie
    st = SF.new_state()
    for i in range(150):
        f = SF.update(st, t + i * 60, 3, 0.0, 61.0, -2000.0, None)
    check("SOC stoi 150 min przy 2 kW → jeszcze bez usterki", f == [], f)
    for i in range(150, 260):
        f = SF.update(st, t + i * 60, 3, 0.0, 61.0, -2000.0, None)
    check("po >180 min przepływu usterka soc_stuck", [x["kind"] for x in f] == ["soc_stuck"], f)
    f = SF.update(st, t + 261 * 60, 3, 0.0, 58.0, -2000.0, None)
    check("SOC ruszył → usterka znika", f == [], f)
    st = SF.new_state()
    for i in range(400):
        f = SF.update(st, t + i * 60, 3, 0.0, 61.0, -50.0, None)
    check("SOC stoi, ale moc ~0 (bateria odpoczywa) → brak usterki", f == [], f)


def run_plan():
    rows = [{"day": "2026-11-24", "h": h, "action": a, "soc": s} for h, a, s in
            [(2, "grid", 60), (3, "grid", 80), (4, "idle", 80), (18, "sell", 60), (19, "sell", 40), (20, "idle", 40), (23, "home", 30)]]
    check("zdanie: ładowanie i sprzedaż", PV.day_sentence(rows, "2026-11-24", 0) == "Ładuję 02:00–04:00 do 80%, sprzedaję 18:00–20:00.",
          PV.day_sentence(rows, "2026-11-24", 0))
    check("zdanie: tylko pozostałe godziny", PV.day_sentence(rows, "2026-11-24", 10) == "Sprzedaję 18:00–20:00.", PV.day_sentence(rows, "2026-11-24", 10))
    check("zdanie: bez akcji", "bez ładowania" in PV.day_sentence(rows, "2026-11-24", 21), PV.day_sentence(rows, "2026-11-24", 21))
    check("zdanie: brak danych", PV.day_sentence([], "2026-11-24", 0) == "" and PV.day_sentence(rows, "2026-11-25", 0) == "")


async def main():
    run_sf(); run_plan()
    hass, c, opt, rt = build(); goodwe(hass, c)
    hass.states.set("number.bms_sell_export_power_w", 5000)
    hass.states.set("number.goodwe_grid_export_limit", 3000)
    hc = HL.health_check(rt); ids = {x["id"]: x for x in hc["checks"]}
    check("limit eksportu < moc sprzedaży → ostrzeżenie", ids["goodwe_export_limit"]["status"] == "warn", ids.get("goodwe_export_limit"))
    hass.states.set("number.goodwe_grid_export_limit", 10000)
    hc = HL.health_check(rt); ids = {x["id"]: x for x in hc["checks"]}
    check("limit eksportu ≥ moc sprzedaży → ok", ids["goodwe_export_limit"]["status"] == "ok", ids.get("goodwe_export_limit"))
    check("kroki wdrożenia marki widoczne (tryb próbny = ostrzeżenie)", ids["brand_guide"]["status"] == "warn" and "1." in ids["brand_guide"]["detail"], ids["brand_guide"])
    rt.sensor_faults = [{"kind": "pv_zero", "text": "PV 0"}]
    hc = HL.health_check(rt); ids = {x["id"]: x for x in hc["checks"]}
    check("sprawdzenie pokazuje usterkę czujnika", ids["sensor_faults"]["status"] == "warn", ids["sensor_faults"])
    rt.insights.pv_live_off = True
    r = rt.insights.pv_multipliers(0, [1.0] * 24)
    check("przy usterce PV korekta na żywo wyłączona (live = 1.0)", r["live"] == 1.0, r["live"])

asyncio.run(main())
