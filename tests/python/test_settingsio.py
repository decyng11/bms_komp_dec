"""Eksport i import ustawień EMS: kopia, podgląd zmian, walidacja, pominięcie trybu próbnego."""
import asyncio, json
from common import *   # noqa
import common
from custom_components.bms_komp_dec import settingsio as SIO


async def main():
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build(); S = hass.states
    S.set("number.bms_reserve_floor_soc", 25); S.set("switch.bms_sell_enabled", "off"); S.set("switch.bms_brand_test_mode", "on")
    rt.profile_save("Weekend", "🏠")
    rt.state["notify_cfg"] = {"phone_level": "all"}
    ex = rt.settings_export()
    check("eksport: format i wersja schematu", ex["format"] == SIO.FORMAT and ex["schema"] == 1)
    check("eksport: wartości liczb i przełączników", ex["values"].get("reserve_floor_soc") == 25.0 and ex["values"].get("sell_enabled") is False, list(ex["values"])[:5])
    check("eksport: bez trybu próbnego marki", "brand_test_mode" not in ex["values"])
    check("eksport: własny profil i powiadomienia", len(ex["custom_profiles"]) == 1 and ex["notify_cfg"] == {"phone_level": "all"})
    check("eksport daje się zapisać jako JSON", bool(json.dumps(ex)))
    # import: te same ustawienia → brak zmian
    r = await rt.settings_import(json.dumps(ex), False)
    check("import tych samych ustawień: nic do zmiany", r["changes"] == [] and not r["applied"], r)
    # zmiana w pliku
    ex2 = json.loads(json.dumps(ex)); ex2["values"]["reserve_floor_soc"] = 40; ex2["values"]["sell_enabled"] = True
    ex2["values"]["brand_test_mode"] = False; ex2["values"]["nieistniejace"] = 1; ex2["values"]["pv_plan_pessimism_pct"] = 9999
    r = await rt.settings_import(ex2, False)
    keys = sorted(x["key"] for x in r["changes"])
    check("podgląd: tylko realne zmiany", keys == ["reserve_floor_soc", "sell_enabled"], keys)
    check("podgląd: pominięte nieznane, błędny zakres i tryb próbny", set(r["skipped"]) >= {"nieistniejace", "pv_plan_pessimism_pct", "brand_test_mode"}, r["skipped"])
    check("podgląd nic nie zapisuje", float(S.get("number.bms_reserve_floor_soc").state) == 25.0)
    r = await rt.settings_import(ex2, True)
    check("zastosowanie: zapisane i bez błędów", r["applied"] and r["failed"] == [], r)
    calls = [(d, s, x.get("entity_id"), x.get("value")) for d, s, x in hass.services.calls if d in ("number", "switch")]
    check("zapisano rezerwę 40 i włączono sprzedaż", ("number", "set_value", "number.bms_reserve_floor_soc", 40.0) in calls and ("switch", "turn_on", "switch.bms_sell_enabled", None) in calls, calls[-4:])
    check("tryb próbny nietknięty", not any(c_[2] == "switch.bms_brand_test_mode" for c_ in calls))
    # złe pliki
    for bad, frag in (("{nie json", "JSON"), ({"format": "inny"}, "plik ustawień EMS"), ({"format": SIO.FORMAT, "schema": 9}, "nowszej")):
        try:
            await rt.settings_import(bad, False); ok = False
        except ValueError as e:
            ok = frag in str(e)
        check(f"zły plik odrzucony ({frag})", ok)
    check("wpis w dzienniku o wczytaniu", any("Wczytano ustawienia" in str(e.get("msg")) for e in rt.log.last(50)))

asyncio.run(main())
print(f"SETTINGSIO PASS={common.PASS} FAIL={common.FAIL}")
