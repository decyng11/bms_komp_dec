"""GoodWe: sterowanie tryby EMS (Auto / Import AC / Export AC / Discharge PV) jak Deye i Sofar, z trybem próbnym."""
import asyncio, sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import brands as BR, health as HL
from homeassistant.exceptions import HomeAssistantError

# nazwy opcji tak, jak podaje je integracja GoodWe w HA (snake_case)
GW_MODES = ["auto", "charge_pv", "discharge_pv", "import_ac", "export_ac", "conserve", "off_grid", "battery_standby", "buy_power", "sell_power",
            "charge_battery", "discharge_battery", "stopped"]


def goodwe(hass, c):
    S = hass.states
    for e in ("select.inverter_work_mode", "number.inverter_battery_max_charging_current", "number.inverter_export_surplus_power",
              "select.inverter_time_of_use"):
        S._s.pop(e, None)
    c.config["work_mode"] = "select.goodwe_ems_mode"
    S.set("select.goodwe_ems_mode", "auto", {"options": GW_MODES})
    S.set("select.goodwe_operation_mode", "eco", {"options": ["general", "off_grid", "backup", "eco", "peak_shaving"]})
    S.set("number.goodwe_ems_power_limit", 0, {"min": 0, "max": 10000})
    BR.reset_cache()


def svc(hass):
    return [(d, s, x.get("entity_id"), x.get("option", x.get("value"))) for d, s, x in hass.services.calls if d in ("select", "number")]


async def main():
    hass, c, opt, rt = build(); goodwe(hass, c)
    opt.config = {"max_charge_power_w": 6000, "max_discharge_power_w": 12000}
    hass.states.set("number.bms_sell_export_power_w", 5000)
    check("GoodWe: wykryty po opcjach EMS mode", rt.brand() == BR.GOODWE, rt.brand())
    st = rt._steps("sprzedaz_6000w")
    check("sprzedaż: tryb pracy „general”, tryb export_ac, potem moc 5000 W",
          st == [("select", "select.goodwe_operation_mode", "general"), ("select", "select.goodwe_ems_mode", "export_ac"), ("number", "number.goodwe_ems_power_limit", 5000)], st)
    st = rt._steps("wlacz_ladowanie_siec")
    check("ładowanie z sieci: import_ac, potem moc 6000 W", st[-2:] == [("select", "select.goodwe_ems_mode", "import_ac"), ("number", "number.goodwe_ems_power_limit", 6000)], st)
    st = rt._steps("zablokuj_ladowanie")
    check("blokada PV: discharge_pv, moc przycięta do zakresu encji (10000)", st[-2:] == [("select", "select.goodwe_ems_mode", "discharge_pv"), ("number", "number.goodwe_ems_power_limit", 10000)], st)
    check("eksport PV z blokadą: jak blokada", rt._steps("eksport_pv_blokada") == rt._steps("zablokuj_ladowanie"))
    for k in ("nadwyzka_9700w", "przywroc_ladowanie", "odblokuj_ladowanie", "wylacz_ladowanie_siec"):
        check(f"{k}: auto", rt._steps(k) == [("select", "select.goodwe_ems_mode", "auto")], rt._steps(k))
    # tryb próbny: nic nie zapisuje
    await rt.run_command("wlacz_ladowanie_siec", source="test")
    check("tryb próbny: brak zapisu do falownika", svc(hass) == [], svc(hass))
    check("tryb próbny: kroki w dzienniku", any("TRYB PRÓBNY" in e["msg"] and "import_ac" in e["msg"] for e in rt.log.last(5)), rt.log.last(3))
    hc = HL.health_check(rt)
    ids = {x["id"]: x for x in hc["checks"]}
    check("sprawdzenie: marka GoodWe, encje, opcje, tryb próbny", ids["brand"]["detail"].startswith("GoodWe") and ids["ctl_power"]["status"] == "ok"
          and ids["opt_mode"]["status"] == "ok" and ids["brand_test"]["status"] == "warn", list(ids)[:10])
    hass.states.set("switch.bms_brand_test_mode", "off")
    await rt.run_command("wlacz_ladowanie_siec", source="test"); await settle(hass)
    check("zapis: tryb pracy, tryb EMS, potem moc", [x[2] for x in svc(hass)] == ["select.goodwe_operation_mode", "select.goodwe_ems_mode", "number.goodwe_ems_power_limit"], svc(hass))
    check("po zapisie tryb pracy to general, więc kolejny zapis go nie powtarza", rt._steps("sprzedaz_6000w")[0][1] == "select.goodwe_ems_mode", rt._steps("sprzedaz_6000w"))
    check("stan: ładowanie z sieci", rt.grid_charging_on() and not rt.is_selling() and not rt.pv_charge_blocked())
    await rt.run_command("sprzedaz_6000w", source="ręcznie", enforce_guard=False); await settle(hass)
    check("stan: sprzedaż", rt.is_selling() and not rt.grid_charging_on())
    await rt.run_command("zablokuj_ladowanie", source="test"); await settle(hass)
    check("stan: blokada ładowania PV", rt.pv_charge_blocked() and not rt.is_selling())
    await rt.run_command("odblokuj_ladowanie", source="test"); await settle(hass)
    check("stan: praca normalna", not rt.pv_charge_blocked() and not rt.is_selling() and not rt.grid_charging_on())
    await rt.run_command("sprzedaz_6000w", source="ręcznie", enforce_guard=False); await settle(hass)
    hass.states.set(c.config["soc"], 12)
    await rt.enforce_guard(at(2026, 11, 6, 18, 0)); await settle(hass)
    check("zabezpieczenie: niski SOC zatrzymuje sprzedaż (auto)", hass.states.get("select.goodwe_ems_mode").state == "auto")
    # firmware bez Import AC, ale z Charge Battery: wymuszone ładowanie
    hass.states.set("select.goodwe_ems_mode", "auto", {"options": ["auto", "export_ac", "battery_standby", "charge_battery"]})
    BR.reset_cache()
    check("brak Import AC: ładowanie przez charge_battery", rt._steps("wlacz_ladowanie_siec")[-2][2] == "charge_battery", rt._steps("wlacz_ladowanie_siec"))
    # brak obu: czytelny błąd
    hass.states.set("select.goodwe_ems_mode", "auto", {"options": ["auto", "export_ac", "battery_standby"]})
    BR.reset_cache()
    try:
        rt._steps("wlacz_ladowanie_siec"); raised = False
    except HomeAssistantError as e:
        raised = "Import AC" in str(e)
    check("brak opcji ładowania: czytelny błąd, bez zapisu", raised)
    # brak encji mocy
    hass.states.set("select.goodwe_ems_mode", "auto", {"options": GW_MODES}); hass.states._s.pop("number.goodwe_ems_power_limit"); BR.reset_cache()
    try:
        rt._steps("sprzedaz_6000w"); raised = False
    except HomeAssistantError as e:
        raised = "ems_power_limit" in str(e)
    check("brak encji mocy: czytelny błąd", raised)
    print(f"GOODWE PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
