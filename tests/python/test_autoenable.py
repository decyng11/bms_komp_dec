"""Auto-stosowanie / ręczne zatwierdzenie godzin włącza przełącznik zestawu (bez niego okno nie wystartuje), z zabezpieczeniem przed arbitrażem."""
import asyncio, sys
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import automation


def prop(cur, new):
    return {"proposed": new, "current": cur, "confidence": "high", "skip": False}


async def main():
    hass, c, opt, rt = build(); S = hass.states
    for k, v in (("start_grid_charge", "22:00:00"), ("stop_grid_charge", "04:00:00"),
                 ("bateria_sprzedaz_start", "17:00:00"), ("bateria_sprzedaz_stop", "19:00:00")):
        S.set(f"time.bms_{k}", v)
    for sw in ("ladowanie_z_sieci_1", "bateria_sprzedaz_1"):
        S.set(f"switch.bms_{sw}", "off")
    S.set("switch.bms_auto_apply", "on")
    res = {"proposals": {
        "start_grid_charge": prop("22:00", "23:00"), "stop_grid_charge": prop("04:00", "05:00"),
        "bateria_sprzedaz_start": prop("17:00", "18:00"), "bateria_sprzedaz_stop": prop("19:00", "20:00")}}
    out = await automation.async_auto_apply(rt, hass, res)
    check("auto: godziny zapisane", out["applied"].get("start_grid_charge") == "23:00", out)
    check("auto: włączono zestaw ładowania z sieci", S.get("switch.bms_ladowanie_z_sieci_1").state == "on")
    check("auto: włączono zestaw sprzedaży (brak zakazu)", S.get("switch.bms_bateria_sprzedaz_1").state == "on")
    check("auto: zestawy zapamiętane do cofnięcia", set(rt.state.get("auto_enabled", [])) == {"ladowanie_z_sieci_1", "bateria_sprzedaz_1"}, rt.state.get("auto_enabled"))
    await automation.async_undo_auto_apply(rt, hass)
    check("cofnięcie: zestawy znów wyłączone", S.get("switch.bms_ladowanie_z_sieci_1").state == "off" and S.get("switch.bms_bateria_sprzedaz_1").state == "off")
    check("cofnięcie: lista wyczyszczona", rt.state.get("auto_enabled") == [])

    # zakaz sprzedaży (arbitraż: bateria naładowana więcej niż wyprodukowało PV) → sprzedaży NIE włączamy, ładowanie tak
    hass, c, opt, rt = build(); S = hass.states
    for k, v in (("start_grid_charge", "22:00:00"), ("stop_grid_charge", "04:00:00"),
                 ("bateria_sprzedaz_start", "17:00:00"), ("bateria_sprzedaz_stop", "19:00:00")):
        S.set(f"time.bms_{k}", v)
    for sw in ("ladowanie_z_sieci_1", "bateria_sprzedaz_1"):
        S.set(f"switch.bms_{sw}", "off")
    c.data = {**(c.data or {}), "energy_battery_charge_today": 12.0, "energy_pv_today": 2.0}
    S.set("switch.bms_auto_apply", "on")
    check("warunek testu: arbitraż blokuje sprzedaż", rt.arbitrage_status()[0] is True)
    out = await automation.async_auto_apply(rt, hass, res)
    check("arbitraż: sprzedaży nie włączono", S.get("switch.bms_bateria_sprzedaz_1").state == "off", S.get("switch.bms_bateria_sprzedaz_1").state)
    check("arbitraż: ładowanie włączone", S.get("switch.bms_ladowanie_z_sieci_1").state == "on")
    check("arbitraż: powód w dzienniku", "zakaz sprzedaży" in str(list(rt.log.entries.values()) if isinstance(rt.log.entries, dict) else rt.log.entries))

    # niepełne okno (Stop = 00:00) → nic nie włączamy
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge", "22:00:00"); S.set("time.bms_stop_grid_charge", "00:00:00")
    S.set("switch.bms_ladowanie_z_sieci_1", "off")
    en = await automation.async_enable_sets(rt, hass, {"start_grid_charge"})
    check("niepełne okno: bez włączania", en == [] and S.get("switch.bms_ladowanie_z_sieci_1").state == "off")
    # już włączony → bez zmian i bez wpisu do cofnięcia
    S.set("time.bms_stop_grid_charge", "04:00:00"); S.set("switch.bms_ladowanie_z_sieci_1", "on")
    en = await automation.async_enable_sets(rt, hass, {"start_grid_charge"})
    check("już włączony: bez zmian", en == [] and not rt.state.get("auto_enabled"))

    # --- te same godziny, zestaw wyłączony (STOP wyłączył go po poprzednim oknie) → auto-stosowanie go włącza
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    same = lambda v: {"skip": False, "proposed": v, "current": v, "confidence": "high", "reason": "x"}
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge", "03:00:00"); S.set("time.bms_stop_grid_charge", "05:00:00")
    S.set("switch.bms_ladowanie_z_sieci_1", "off"); S.set("switch.bms_auto_apply", "on")
    pl = {"proposals": {"start_grid_charge": same("03:00"), "stop_grid_charge": same("05:00")}}
    await automation.async_auto_apply(rt, hass, pl)
    check("te same godziny + zestaw wyłączony: auto-stosowanie włącza zestaw", S.get("switch.bms_ladowanie_z_sieci_1").state == "on")
    # ścieżka na żywo (plan co 15 min)
    S.set("switch.bms_ladowanie_z_sieci_1", "off")
    await automation.async_live_apply(rt, hass, pl, dt_util.now().replace(hour=12, minute=0))
    check("plan na żywo: zestaw ładowania uzbrojony od razu", S.get("switch.bms_ladowanie_z_sieci_1").state == "on")
    # pominięte / niska pewność / inne godziny → bez włączania
    for name, props in (("plan pomija okno", {"start_grid_charge": {**same("03:00"), "skip": True}, "stop_grid_charge": {**same("05:00"), "skip": True}}),
                        ("niska pewność", {"start_grid_charge": {**same("03:00"), "confidence": "low"}, "stop_grid_charge": same("05:00")})):
        S.set("switch.bms_ladowanie_z_sieci_1", "off")
        await automation.async_live_apply(rt, hass, {"proposals": props}, dt_util.now().replace(hour=12, minute=0))
        check(f"{name}: zestaw zostaje wyłączony", S.get("switch.bms_ladowanie_z_sieci_1").state == "off")
    # przełącznik „Auto-włączanie zestawów” wyłączony
    S.set("switch.bms_auto_enable_sets", "off")
    await automation.async_live_apply(rt, hass, pl, dt_util.now().replace(hour=12, minute=0))
    await automation.async_auto_apply(rt, hass, pl)
    check("auto-włączanie wyłączone: zestaw zostaje wyłączony", S.get("switch.bms_ladowanie_z_sieci_1").state == "off")
    # sprzedaż: na żywo nie uzbrajamy, a w propozycji dziennej tylko bez zakazu sprzedaży
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("time.bms_bateria_sprzedaz_stop", "19:00:00")
    S.set("switch.bms_bateria_sprzedaz_1", "off"); S.set("switch.bms_auto_apply", "on")
    ps = {"proposals": {"bateria_sprzedaz_start": same("17:00"), "bateria_sprzedaz_stop": same("19:00")}}
    await automation.async_live_apply(rt, hass, ps, dt_util.now().replace(hour=12, minute=0))
    check("sprzedaż: plan na żywo nie włącza zestawu", S.get("switch.bms_bateria_sprzedaz_1").state == "off")
    rt.state["grid_batt"] = {"kwh": 3.0}
    await automation.async_auto_apply(rt, hass, ps)
    check("sprzedaż: energia z sieci w baterii → zestaw NIE jest włączany", S.get("switch.bms_bateria_sprzedaz_1").state == "off")
    rt.state["grid_batt"] = {"kwh": 0.0}
    await automation.async_auto_apply(rt, hass, ps)
    check("sprzedaż: bez zakazu → propozycja dzienna włącza zestaw", S.get("switch.bms_bateria_sprzedaz_1").state == "on")

    # --- powiadomienie: plan przewiduje okno w ciągu 90 min, a zestaw jest wyłączony
    hass, c, opt, rt = build(); S = hass.states
    sent = []
    async def fake_send(kind, title, message, **kw):
        sent.append((kind, message)); return True
    rt.monitor.notifier.send = fake_send
    S.set("time.bms_start_grid_charge_2", "13:00:00"); S.set("time.bms_stop_grid_charge_2", "14:00:00")
    S.set("switch.bms_ladowanie_z_sieci_2", "off")
    pn = {"proposals": {"start_grid_charge_2": same("13:00"), "stop_grid_charge_2": same("14:00")}}
    t12 = dt_util.now().replace(hour=12, minute=0, second=0, microsecond=0)
    await automation.async_notify_sets_off(rt, hass, pn, t12 - timedelta(hours=3))
    check("powiadomienie: 4 h przed oknem — jeszcze nie", not sent)
    await automation.async_notify_sets_off(rt, hass, pn, t12)
    check("powiadomienie: 60 min przed oknem — wysłane", len(sent) == 1 and sent[0][0] == "set_off" and "13:00–14:00" in sent[0][1], sent)
    await automation.async_notify_sets_off(rt, hass, pn, t12 + timedelta(minutes=5))
    check("powiadomienie: raz na okno", len(sent) == 1)
    S.set("switch.bms_ladowanie_z_sieci_2", "on"); rt._set_off_seen.clear()
    await automation.async_notify_sets_off(rt, hass, pn, t12)
    check("powiadomienie: zestaw włączony — brak", len(sent) == 1)

    # --- po STOP-ie stary plan (sprzed STOP-u) nie włącza zestawu z powrotem; świeży plan tak
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge_2", "11:00:00"); S.set("time.bms_stop_grid_charge_2", "13:00:00")
    S.set("switch.bms_ladowanie_z_sieci_2", "off"); S.set("switch.bms_auto_apply", "on")
    t13 = dt_util.now().replace(hour=13, minute=0, second=30, microsecond=0)
    rt.fired["stop_grid_charge_2"] = t13
    pl2 = {"generated_at": (t13 - timedelta(minutes=10)).isoformat(),
           "proposals": {"start_grid_charge_2": same("11:00"), "stop_grid_charge_2": same("13:00")}}
    await automation.async_live_apply(rt, hass, pl2, t13)
    check("plan sprzed STOP-u: zestaw nie jest włączany z powrotem", S.get("switch.bms_ladowanie_z_sieci_2").state == "off")
    pl2["generated_at"] = (t13 + timedelta(minutes=5)).isoformat()
    await automation.async_live_apply(rt, hass, pl2, t13 + timedelta(minutes=6))
    check("świeży plan nadal przewiduje okno: zestaw włączony", S.get("switch.bms_ladowanie_z_sieci_2").state == "on")
    check("zapamiętano, że włączył go EMS", "ladowanie_z_sieci_2" in (rt.state.get("auto_enabled") or []))
    # plan zmienia zdanie (pomija okno) → EMS wyłącza zestaw, który sam włączył
    skp = {"skip": True, "proposed": None, "current": "11:00", "confidence": "high", "reason": "Pomiń — bateria wystarczy"}
    await automation.async_live_apply(rt, hass, {"proposals": {"start_grid_charge_2": skp, "stop_grid_charge_2": skp}}, t13 + timedelta(minutes=30))
    check("plan pomija okno: zestaw włączony przez EMS zostaje wyłączony", S.get("switch.bms_ladowanie_z_sieci_2").state == "off")
    # zestaw włączony ręcznie przez użytkownika — plan pomija, EMS go nie rusza
    S.set("switch.bms_ladowanie_z_sieci_2", "on")
    await automation.async_live_apply(rt, hass, {"proposals": {"start_grid_charge_2": skp, "stop_grid_charge_2": skp}}, t13 + timedelta(minutes=45))
    check("zestaw włączony ręcznie: plan pomija, EMS nie wyłącza", S.get("switch.bms_ladowanie_z_sieci_2").state == "on")
    print(f"AUTOENABLE PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
