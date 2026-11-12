"""Plan pomija sprzedaż → EMS wyłącza zestaw sprzedaży (a gdy plan wraca — włącza); zysk w zł przy propozycjach."""
import asyncio, sys
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import automation


def sk(conf="high", reason="Pomiń — sprzedaż nieopłacalna"):
    return {"skip": True, "proposed": None, "current": "18:00", "confidence": conf, "reason": reason}


def ok_p(cur, new):
    return {"skip": False, "proposed": new, "current": cur, "confidence": "high", "reason": "x"}


def setup():
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_bateria_sprzedaz_start_2", "18:00:00"); S.set("time.bms_bateria_sprzedaz_stop_2", "19:00:00")
    S.set("switch.bms_bateria_sprzedaz_2", "on"); S.set("switch.bms_auto_apply", "on")
    return hass, c, opt, rt, S


async def main():
    hass, c, opt, rt, S = setup()
    res = {"proposals": {"bateria_sprzedaz_start_2": sk(), "bateria_sprzedaz_stop_2": sk()}}
    out = await automation.async_auto_apply(rt, hass, res)
    check("plan pomija sprzedaż → zestaw wyłączony", S.get("switch.bms_bateria_sprzedaz_2").state == "off", out)
    check("zapamiętano, że wyłączył go EMS", rt.state.get("auto_disabled") == ["bateria_sprzedaz_2"], rt.state.get("auto_disabled"))
    check("wynik zawiera disabled_sets", out.get("disabled_sets") == ["bateria_sprzedaz_2"], out)
    # plan znów proponuje sprzedaż (te same godziny) → zestaw wraca
    res2 = {"proposals": {"bateria_sprzedaz_start_2": ok_p("18:00", "18:00"), "bateria_sprzedaz_stop_2": ok_p("19:00", "19:00")}}
    await automation.async_auto_apply(rt, hass, res2)
    check("plan wraca do sprzedaży → zestaw znów włączony", S.get("switch.bms_bateria_sprzedaz_2").state == "on")
    check("lista wyłączonych wyczyszczona", rt.state.get("auto_disabled") == [])

    # niska pewność (brak danych) → nic nie ruszamy
    hass, c, opt, rt, S = setup()
    await automation.async_auto_apply(rt, hass, {"proposals": {"bateria_sprzedaz_start_2": sk("low", "Pomiń — brak cen RCE"), "bateria_sprzedaz_stop_2": sk("low")}})
    check("niska pewność: zestaw zostaje włączony", S.get("switch.bms_bateria_sprzedaz_2").state == "on")
    # tylko podgląd
    S.set("switch.bms_auto_apply_dry_run", "on")
    await automation.async_auto_apply(rt, hass, res)
    check("tryb podglądu: nic nie wyłączono", S.get("switch.bms_bateria_sprzedaz_2").state == "on")
    S.set("switch.bms_auto_apply_dry_run", "off")

    # zestaw wyłączony ręcznie przez użytkownika: plan go nie włącza sam, gdy godziny bez zmian
    hass, c, opt, rt, S = setup()
    S.set("switch.bms_bateria_sprzedaz_2", "off")
    await automation.async_auto_apply(rt, hass, res2)
    check("wyłączony ręcznie, plan bez zmian godzin: zostaje wyłączony", S.get("switch.bms_bateria_sprzedaz_2").state == "off")

    # trwa sprzedaż → nie ruszamy
    hass, c, opt, rt, S = setup()
    S.set("select.inverter_work_mode", "Export First")
    await automation.async_auto_apply(rt, hass, res)
    check("trwa sprzedaż: zestaw nietknięty", S.get("switch.bms_bateria_sprzedaz_2").state == "on")

    # cofnięcie przywraca wyłączony przez plan zestaw
    hass, c, opt, rt, S = setup()
    await automation.async_auto_apply(rt, hass, res)
    await automation.async_undo_auto_apply(rt, hass)
    check("cofnięcie: zestaw znów włączony", S.get("switch.bms_bateria_sprzedaz_2").state == "on" and rt.state.get("auto_disabled") == [])

    # ścieżka dzienna: brak zmian godzin, ale plan pomija sprzedaż → zestaw wyłączony
    hass, c, opt, rt, S = setup()
    class Opt:
        async def suggest(self): return {"proposals": {"bateria_sprzedaz_start_2": sk(), "bateria_sprzedaz_stop_2": sk()}}
    await automation.async_daily_suggest(rt, hass, Opt())
    check("dzienna propozycja bez zmian godzin też wyłącza zestaw", S.get("switch.bms_bateria_sprzedaz_2").state == "off")

    # zerowanie okna: plan nie ma sprzedaży → stop = start (także gdy zestaw był już wyłączony)
    hass, c, opt, rt, S = setup()
    await automation.async_auto_apply(rt, hass, res)
    check("brak propozycji: okno wyzerowane (stop = start)",
          S.get("time.bms_bateria_sprzedaz_stop_2").state[:5] == "18:00" and S.get("time.bms_bateria_sprzedaz_start_2").state[:5] == "18:00",
          (S.get("time.bms_bateria_sprzedaz_start_2").state, S.get("time.bms_bateria_sprzedaz_stop_2").state))
    hass, c, opt, rt, S = setup()
    S.set("switch.bms_bateria_sprzedaz_2", "off")
    await automation.async_auto_apply(rt, hass, res)
    check("zestaw już wyłączony: okno i tak wyzerowane", S.get("time.bms_bateria_sprzedaz_stop_2").state[:5] == "18:00")
    hass, c, opt, rt, S = setup()
    await automation.async_auto_apply(rt, hass, {"proposals": {"bateria_sprzedaz_start_2": sk("low"), "bateria_sprzedaz_stop_2": sk("low")}})
    check("niska pewność: godziny nietknięte", S.get("time.bms_bateria_sprzedaz_stop_2").state[:5] == "19:00")
    hass, c, opt, rt, S = setup()
    S.set("switch.bms_auto_apply_dry_run", "on")
    await automation.async_auto_apply(rt, hass, res)
    check("podgląd: godziny nietknięte", S.get("time.bms_bateria_sprzedaz_stop_2").state[:5] == "19:00")
    # plan wraca do sprzedaży z nowym stopem → okno znów ustawione
    hass, c, opt, rt, S = setup()
    await automation.async_auto_apply(rt, hass, res)
    await automation.async_auto_apply(rt, hass, {"proposals": {"bateria_sprzedaz_start_2": ok_p("18:00", "18:00"), "bateria_sprzedaz_stop_2": ok_p("18:00", "19:00")}})
    check("plan wraca: stop ustawiony z powrotem, zestaw włączony",
          S.get("time.bms_bateria_sprzedaz_stop_2").state[:5] == "19:00" and S.get("switch.bms_bateria_sprzedaz_2").state == "on")
    print(f"SALESYNC PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
