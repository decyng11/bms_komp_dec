"""0.8.6: sterowanie falownikami Sofar (G3 — tryb pasywny, hybrydowy — Work Mode / Timed) i tryb próbny."""
import asyncio, sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import brands as BR, health as HL
from homeassistant.exceptions import HomeAssistantError

G3_MODES = ["Self Use", "Time of Use", "Optimized Revenue", "Passive", "Peak Shaving", "Off-Grid", "Generator", "Export Priority"]
HY_MODES = ["Auto", "Time of Use", "Timed", "Passive", "Peak Shaving"]
BIG = {"min": -2147483648, "max": 2147483647}


def sofar_g3(hass, c):
    S = hass.states
    for e in ("select.inverter_work_mode", "number.inverter_battery_max_charging_current", "number.inverter_export_surplus_power",
              "select.inverter_time_of_use"):
        S._s.pop(e, None)
    c.config["work_mode"] = "select.inverter_storage_control_mode"
    S.set("select.inverter_storage_control_mode", "Self Use", {"options": G3_MODES})
    S.set("number.inverter_passive_grid_power", 0, BIG)
    S.set("number.inverter_passive_minimum_battery_power", 0, BIG)
    S.set("number.inverter_passive_maximum_battery_power", 0, BIG)
    BR.reset_cache()


def sofar_hybrid(hass, c):
    S = hass.states
    for e in ("number.inverter_battery_max_charging_current", "number.inverter_export_surplus_power", "select.inverter_time_of_use"):
        S._s.pop(e, None)
    S.set("select.inverter_work_mode", "Auto", {"options": HY_MODES})
    for p in ("charge", "discharge"):
        S.set(f"time.inverter_timed_{p}_start", "00:00:00"); S.set(f"time.inverter_timed_{p}_end", "00:00:00")
        S.set(f"number.inverter_timed_{p}_power", 0, {"min": 0, "max": 3000})
    S.set("number.inverter_battery_max_charge_current", 50, {"min": 0, "max": 65})
    BR.reset_cache()


def svc(hass):
    return [(d, s, x.get("entity_id"), x.get("option", x.get("value", x.get("time")))) for d, s, x in hass.services.calls
            if d in ("select", "number", "time")]


async def main():
    # ---------- Deye bez zmian
    hass, c, opt, rt = build(); BR.reset_cache()
    hass.states.set("select.inverter_work_mode", "Zero Export To Load", {"options": ["Selling First", "Zero Export To Load", "Zero Export To CT"]})
    check("Deye: wykryty po opcjach trybu", rt.brand() == BR.DEYE)
    check("Deye: kroki jak dotąd", rt._steps("sprzedaz_6000w")[0] == ("select", "select.inverter_work_mode", "Selling First"), rt._steps("sprzedaz_6000w"))
    check("Deye: tryb próbny Sofara nie dotyczy", not rt.brand_test_mode())

    # ---------- Sofar G3
    hass, c, opt, rt = build(); sofar_g3(hass, c)
    opt.config = {"max_charge_power_w": 6000, "max_discharge_power_w": 8000}
    hass.states.set("number.bms_sell_export_power_w", 5000)
    check("G3: wykryty", rt.brand() == BR.SOFAR_G3)
    st = rt._steps("sprzedaz_6000w")
    check("G3 sprzedaż: Passive, bateria min = max = −5000, tryb na końcu",
          st == [("number", "number.inverter_passive_grid_power", 0), ("number", "number.inverter_passive_minimum_battery_power", -5000),
                 ("number", "number.inverter_passive_maximum_battery_power", -5000), ("select", "select.inverter_storage_control_mode", "Passive")], st)
    st = rt._steps("wlacz_ladowanie_siec")
    check("G3 ładowanie z sieci: min = max = +6000", st[1][2] == 6000 and st[2][2] == 6000 and st[3][2] == "Passive", st)
    st = rt._steps("zablokuj_ladowanie")
    check("G3 blokada PV: min = −8000 (może oddawać), max = 0", st[1][2] == -8000 and st[2][2] == 0, st)
    check("G3 eksport PV z blokadą: jak blokada (min −8000, max 0)", rt._steps("eksport_pv_blokada") == rt._steps("zablokuj_ladowanie"))
    for k in ("nadwyzka_9700w", "przywroc_ladowanie", "odblokuj_ladowanie", "wylacz_ladowanie_siec"):
        check(f"G3 {k}: Self Use", rt._steps(k) == [("select", "select.inverter_storage_control_mode", "Self Use")], rt._steps(k))
    # tryb próbny (domyślnie): nic nie zapisuje, wpis w dzienniku
    await rt.run_command("wlacz_ladowanie_siec", source="test")
    check("G3 tryb próbny: brak zapisu do falownika", svc(hass) == [], svc(hass))
    check("G3 tryb próbny: kroki w dzienniku", any("TRYB PRÓBNY" in e["msg"] and "passive_minimum_battery_power = 6000" in e["msg"] for e in rt.log.last(5)), rt.log.last(3))
    hc = HL.health_check(rt)
    ids = {x["id"]: x for x in hc["checks"]}
    check("sprawdzenie: marka, encje Sofara, opcje, tryb próbny", ids["brand"]["detail"].startswith("Sofar G3") and ids["ctl_bat_min"]["status"] == "ok"
          and ids["opt_mode"]["status"] == "ok" and ids["brand_test"]["status"] == "warn" and "ctl_work_mode" not in ids, list(ids)[:12])
    check("sprawdzenie: podgląd komend dla Sofara", all(x["ok"] for x in hc["commands"]), [x for x in hc["commands"] if not x["ok"]])
    # zapis włączony
    hass.states.set("switch.bms_brand_test_mode", "off")
    await rt.run_command("wlacz_ladowanie_siec", source="test"); await settle(hass)
    calls = svc(hass)
    check("G3 zapis: 4 kroki do falownika", [x[2] for x in calls] == ["number.inverter_passive_grid_power", "number.inverter_passive_minimum_battery_power",
                                                                       "number.inverter_passive_maximum_battery_power", "select.inverter_storage_control_mode"], calls)
    check("G3 stan: ładowanie z sieci", rt.grid_charging_on() and not rt.is_selling() and not rt.pv_charge_blocked())
    await rt.run_command("sprzedaz_6000w", source="ręcznie", enforce_guard=False); await settle(hass)
    check("G3 stan: sprzedaż", rt.is_selling() and not rt.grid_charging_on())
    await rt.run_command("zablokuj_ladowanie", source="test"); await settle(hass)
    check("G3 stan: blokada ładowania PV", rt.pv_charge_blocked() and not rt.is_selling())
    await rt.run_command("odblokuj_ladowanie", source="test"); await settle(hass)
    check("G3 stan: praca normalna", not rt.pv_charge_blocked() and not rt.is_selling() and not rt.grid_charging_on())
    # zabezpieczenie: sprzedaż przy niskim SOC → praca normalna
    await rt.run_command("sprzedaz_6000w", source="ręcznie", enforce_guard=False); await settle(hass)
    hass.states.set(c.config["soc"], 12)
    await rt.enforce_guard(at(2026, 11, 6, 18, 0)); await settle(hass)
    check("G3 zabezpieczenie: niski SOC zatrzymuje sprzedaż (Self Use)", hass.states.get("select.inverter_storage_control_mode").state == "Self Use")
    # brak encji
    hass.states._s.pop("number.inverter_passive_grid_power")
    BR.reset_cache()
    try:
        rt._steps("sprzedaz_6000w"); raised = False
    except HomeAssistantError as e:
        raised = "passive_grid_power" in str(e)
    check("G3: brak encji → czytelny błąd, bez zapisu", raised)

    # ---------- Sofar hybrydowy
    hass, c, opt, rt = build(); sofar_hybrid(hass, c)
    opt.config = {"max_charge_power_w": 6000, "max_discharge_power_w": 3000}
    hass.states.set("number.bms_sell_export_power_w", 2500)
    check("Hybrid: wykryty", rt.brand() == BR.SOFAR_HYBRID)
    st = rt._steps("wlacz_ladowanie_siec")
    check("Hybrid ładowanie z sieci: okno 00:00–23:59, moc przycięta do 3000, rozładowanie wyłączone, Timed",
          ("time", "time.inverter_timed_charge_end", "23:59:00") in st and ("number", "number.inverter_timed_charge_power", 3000) in st
          and ("time", "time.inverter_timed_discharge_end", "00:00:00") in st and st[-1] == ("select", "select.inverter_work_mode", "Timed"), st)
    st = rt._steps("sprzedaz_6000w")
    check("Hybrid sprzedaż: okno rozładowania, moc 2500", ("number", "number.inverter_timed_discharge_power", 2500) in st
          and ("time", "time.inverter_timed_discharge_end", "23:59:00") in st, st)
    check("Hybrid blokada PV: prąd ładowania 0", rt._steps("zablokuj_ladowanie") == [("number", "number.inverter_battery_max_charge_current", 0)])
    rt.state["normal_charge_current"] = 50
    check("Hybrid przywróć ładowanie: zapamiętany prąd i Auto", rt._steps("przywroc_ladowanie") == [("number", "number.inverter_battery_max_charge_current", 50),
                                                                                                    ("select", "select.inverter_work_mode", "Auto")], rt._steps("przywroc_ladowanie"))
    hass.states.set("switch.bms_brand_test_mode", "off")
    await rt.run_command("wlacz_ladowanie_siec", source="test"); await settle(hass)
    check("Hybrid zapis: czas przez time.set_value", any(x[0] == "time" and x[3] == "23:59:00" for x in svc(hass)), svc(hass))
    check("Hybrid stan: ładowanie z sieci", rt.grid_charging_on() and not rt.is_selling())
    await rt.run_command("wylacz_ladowanie_siec", source="test"); await settle(hass)
    check("Hybrid stan: po wyłączeniu — Auto", not rt.grid_charging_on() and hass.states.get("select.inverter_work_mode").state == "Auto")
    await rt.run_command("zablokuj_ladowanie", source="test"); await settle(hass)
    check("Hybrid stan: blokada PV", rt.pv_charge_blocked())
    check("Hybrid: odczyt zwrotny godziny (HH:MM)", rt._mismatches([("time", "time.inverter_timed_charge_end", "23:59:00")]) == [])

    print(f"SOFAR PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
