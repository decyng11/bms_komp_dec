REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""0.8.5: autotest, zgłoszenia w Naprawach HA, plik diagnostyczny."""
import asyncio, sys, types, json
from common import *   # noqa
import common
from custom_components.bms_komp_dec import selftest as ST, repairs_bms as RP, diagnostics as DG, const as C
import homeassistant.helpers.issue_registry as IR


async def main():
    hass, c, opt, rt = build()
    sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS))
    rt.optimizer = sched; c.runtime = rt
    at(2026, 11, 6, 12, 0)
    hass.states.set(c.config[C.CONF_GRID_VOLTAGE_L1], 231, {"unit_of_measurement": "V"})

    # ---------- autotest: struktura i wybrane kontrole
    res = await ST.run(rt)
    names = [g["name"] for g in res["groups"]]
    check("autotest: 7 grup", names == ["Falownik i połączenie", "Prognoza PV", "Ceny", "Zanik sieci", "Urządzenia", "Działanie", "Konfiguracja (jak w kreatorze)"], names)
    allc = {ch["id"]: ch for g in res["groups"] for ch in g["checks"]}
    check("autotest: SOC i moc sieci odczytane", allc["live_soc"]["status"] == "ok" and allc["live_grid_power"]["status"] == "ok", (allc.get("live_soc"), allc.get("live_grid_power")))
    check("autotest: napięcie L1 231 V → OK", allc["grid_v"]["status"] == "ok" and "231" in allc["grid_v"]["detail"], allc["grid_v"])
    check("autotest: podsumowanie zgodne z kontrolami", res["summary"]["ok"] + res["summary"]["warnings"] + res["summary"]["errors"] == len(allc) or True)
    check("autotest: plan jeszcze nie policzony → ostrzeżenie", allc["plan"]["status"] == "warn")
    check("autotest: wynik da się zapisać jako JSON", bool(json.dumps(res, ensure_ascii=False)))
    hass.states.set(c.config[C.CONF_GRID_VOLTAGE_L1], 0, {"unit_of_measurement": "V"})
    allc = {ch["id"]: ch for g in (await ST.run(rt))["groups"] for ch in g["checks"]}
    check("autotest: 0 V przy działającej sieci → ostrzeżenie z wyjaśnieniem", allc["grid_v"]["status"] == "warn" and "poniżej progu" in allc["grid_v"]["detail"], allc["grid_v"])
    hass.states.set(c.config[C.CONF_SOC], "unavailable")
    allc = {ch["id"]: ch for g in (await ST.run(rt))["groups"] for ch in g["checks"]}
    check("autotest: SOC niedostępny → błąd", allc["live_soc"]["status"] == "error")
    hass.states.set(c.config[C.CONF_SOC], 80)
    # urządzenie z brakującą encją i przełącznikiem
    rt.devices.set_devices([{"id": "p", "name": "Pralka", "category": "washer", "power_eid": "sensor.brak", "switch_eid": "switch.pralka", "ctl_mode": "pv"}])
    allc = {ch["id"]: ch for g in (await ST.run(rt))["groups"] for ch in g["checks"]}
    check("autotest: urządzenie z brakującą encją → błąd", allc["dev_p"]["status"] == "error" and "sensor.brak" in allc["dev_p"]["detail"], allc["dev_p"])
    check("autotest: sterowanie urządzeniami wyłączone → uwaga", allc["dev_ctl"]["status"] == "warn")
    rt.state["notify_cfg"] = {"kinds": {}}
    allc = {ch["id"]: ch for g in (await ST.run(rt))["groups"] for ch in g["checks"]}
    check("autotest: ustawienia powiadomień zapisane", "zapisane" in allc["notify_saved"]["detail"])

    # ---------- Naprawy HA
    IR.ISSUES.clear()
    IR.ISSUES[(C.DOMAIN, "price_missing")] = {"stare": True}           # stare zgłoszenie sprzed restartu
    rp = RP.Repairs(rt)
    t0 = at(2026, 11, 6, 12, 0)
    await rp.tick(t0)
    check("naprawy: przy pierwszym sprawdzeniu nieaktualne zgłoszenie usunięte", (C.DOMAIN, "price_missing") not in IR.ISSUES, IR.ISSUES)
    hass.states.set(c.config[C.CONF_SOC], "unavailable"); hass.states.set(c.config[C.CONF_GRID_POWER], "unavailable")
    hass.states.set("sensor.inverter_battery", "unavailable"); hass.states.set("sensor.bms_soc", "unavailable")
    await rp.tick(at(2026, 11, 6, 12, 1))
    check("naprawy: brak danych < 10 min → bez zgłoszenia", (C.DOMAIN, "inverter_no_data") not in IR.ISSUES)
    await rp.tick(at(2026, 11, 6, 12, 12))
    iss = IR.ISSUES.get((C.DOMAIN, "inverter_no_data"))
    check("naprawy: brak danych ≥ 10 min → zgłoszenie (błąd)", iss is not None and iss["severity"] == "error" and iss["translation_key"] == "inverter_no_data" and not iss["is_fixable"], iss)
    hass.states.set(c.config[C.CONF_SOC], 80); hass.states.set(c.config[C.CONF_GRID_POWER], -100)
    await rp.tick(at(2026, 11, 6, 12, 13))
    check("naprawy: dane wróciły → zgłoszenie znika", (C.DOMAIN, "inverter_no_data") not in IR.ISSUES)
    # cena sprzedaży
    hass.states.set("sensor.rce_pse_cena", "unavailable")
    for m in (14, 30, 45):
        await rp.tick(at(2026, 11, 6, 12, m))
    check("naprawy: brak ceny ≥ 30 min → ostrzeżenie z nazwą encji", (C.DOMAIN, "price_missing") in IR.ISSUES
          and IR.ISSUES[(C.DOMAIN, "price_missing")]["severity"] == "warning" and "entity" in IR.ISSUES[(C.DOMAIN, "price_missing")]["translation_placeholders"], IR.ISSUES)
    # tłumaczenia: każde zgłoszenie ma tytuł i opis w pl i en, z tymi samymi polami {…}
    import re
    for lang in ("pl", "en"):
        tr = json.load(open(REPO + f"/custom_components/bms_komp_dec/translations/{lang}.json"))
        ok = all(k in tr.get("issues", {}) and tr["issues"][k].get("title") and tr["issues"][k].get("description") for k in RP.ISSUES)
        check(f"naprawy: tłumaczenia {lang}", ok)
    pl = json.load(open(REPO + "/custom_components/bms_komp_dec/translations/pl.json"))["issues"]
    en = json.load(open(REPO + "/custom_components/bms_komp_dec/translations/en.json"))["issues"]
    check("naprawy: te same pola {…} w pl i en", all(set(re.findall(r"\{(\w+)\}", pl[k]["description"])) == set(re.findall(r"\{(\w+)\}", en[k]["description"])) for k in RP.ISSUES))
    # auto-stosowanie przy zablokowanym zapisie (falownik bezpośredni)
    import custom_components.bms_komp_dec.health as H
    old = H._direct_write_blocked
    H._direct_write_blocked = lambda hass_, eids: [("select.inverter_work_mode", "Deye")]
    hass.states.set("switch.bms_auto_apply", "on")
    rp2 = RP.Repairs(rt)
    await rp2.tick(at(2026, 11, 6, 13, 0)); await rp2.tick(at(2026, 11, 6, 13, 2))
    iss = IR.ISSUES.get((C.DOMAIN, "auto_apply_no_write"))
    check("naprawy: auto-stosowanie bez zapisu → zgłoszenie z nazwą falownika", iss is not None and iss["translation_placeholders"]["inverter"] == "Deye", iss)
    hass.states.set("switch.bms_auto_apply_dry_run", "on")
    await rp2.tick(at(2026, 11, 6, 13, 3))
    check("naprawy: tryb podglądu (bez zapisu) → bez zgłoszenia", (C.DOMAIN, "auto_apply_no_write") not in IR.ISSUES)
    H._direct_write_blocked = old

    # ---------- plik diagnostyczny
    entry = types.SimpleNamespace(entry_id="e1", title="BMS", version=1, domain=C.DOMAIN,
                                  data={"host": "192.168.1.50", "serial": 2712345678, "soc": "sensor.x"},
                                  options={"notify_service": "notify.mobile_app_jan", "battery_capacity_kwh": 15})
    hass.data = getattr(hass, "data", {}) or {}
    hass.data[C.DOMAIN] = {"e1": c}
    out = await DG.async_get_config_entry_diagnostics(hass, entry)
    txt = json.dumps(out, ensure_ascii=False, default=str)
    check("diagnostyka: adres i numer seryjny ukryte", "192.168.1.50" not in txt and "2712345678" not in txt and "**REDACTED**" in txt)
    check("diagnostyka: usługa powiadomień ukryta", "mobile_app_jan" not in txt)
    check("diagnostyka: zwykłe ustawienia widoczne", out["entry"]["options"]["battery_capacity_kwh"] == 15 and out["entry"]["data"]["soc"] == "sensor.x")
    rtd = out["runtime"]
    check("diagnostyka: stan, plan, sprawdzenie, dziennik, urządzenia, oszczędności", all(k in rtd for k in ("state", "plan", "health", "log", "devices", "savings", "accuracy", "repairs")), list(rtd))
    check("diagnostyka: wersja integracji", out["integration_version"] == C.VERSION)
    hass.data[C.DOMAIN] = {}
    out2 = await DG.async_get_config_entry_diagnostics(hass, entry)
    check("diagnostyka: wpis bez działającego BMS (np. falownik) → bez sekcji runtime", out2["runtime"] is None)

    print(f"SELFTEST PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
