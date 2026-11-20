"""Lista „co dziś nie działa”: braki cen RCE/zakupu, prognozy PV, plan, zapis do falownika, kolizja okien, urządzenia, alarmy, naprawione dane."""
import asyncio, json, sys
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import issues as ISS, tariff as tar, scheduler, const, notify_cfg
from custom_components.bms_komp_dec.sensor import BmsRuntimeSensor


async def env(now=(2026, 11, 20, 20, 0), **kw):
    hass, c, sched = await mk(now, 60, **kw)
    d0 = date(*now[:3]); d1 = d0 + timedelta(days=1)
    price = lambda h: 250 if 10 <= h < 15 else (700 if 17 <= h < 21 else 450)
    # jutro musi się różnić od dziś — identyczna lista jest odrzucana przez czytnik jako kopia
    hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": arr(d0, price) + arr(d1, lambda h: price(h) + 37)})
    rt = rtm.BmsRuntime(hass, c, sched)
    c.runtime = rt
    return hass, c, sched, rt


def ids(lst):
    return [i["id"] for i in lst]


async def main():
    tar.set_profile(tar.make_profile({"tariff_mode": "zone"}, prices_fn=lambda d: None, eff_fn=lambda: 0.9, source=""))

    # ---------- zdrowy układ: nic na liście
    hass, c, sched, rt = await env()
    now = at(2026, 11, 20, 20, 0)
    got = ISS.collect(rt, now)
    check("zdrowy układ → lista pusta", got == [], got)

    # ---------- ceny RCE
    hass, c, sched, rt = await env()
    S = hass.states
    S.set("sensor.rce_pse_cena", 0.6, {})
    got = ISS.collect(rt, at(2026, 11, 20, 12, 0))
    check("brak cen RCE na dziś → ostrzeżenie z liczbą godzin", "rce_today" in ids(got) and "0/24" in next(i for i in got if i["id"] == "rce_today")["detail"], got)
    check("przed 15:00 brak cen na jutro nie jest usterką", "rce_tomorrow" not in ids(got))
    got = ISS.collect(rt, at(2026, 11, 20, 16, 0))
    check("po 15:00 brak cen RCE na jutro → ostrzeżenie", "rce_tomorrow" in ids(got), got)
    d0 = date(2026, 11, 20)
    S.set("sensor.rce_pse_cena", 0.6, {"prices": arr(d0, lambda h: 400)})
    got = ISS.collect(rt, at(2026, 11, 20, 16, 0))
    check("są ceny na dziś, brak na jutro → tylko jutro", ids(got).count("rce_today") == 0 and "rce_tomorrow" in ids(got), got)
    S.set("sensor.rce_pse_cena", 0.6, {"prices": arr(d0, lambda h: 400) + arr(d0 + timedelta(days=1), lambda h: 430 + h if h != 5 else None)})
    got = ISS.collect(rt, at(2026, 11, 20, 16, 0))
    check("jutro niepełne (23/24) → ostrzeżenie", "rce_tomorrow" in ids(got) and "23/24" in next(i for i in got if i["id"] == "rce_tomorrow")["detail"], got)

    # ---------- prognoza PV
    hass, c, sched, rt = await env()
    S = hass.states
    for eid in ("sensor.solcast_pv_forecast_forecast_today", "sensor.solcast_pv_forecast_forecast_tomorrow"):
        S.set(eid, "unavailable", {})
    got = ISS.collect(rt, at(2026, 11, 20, 12, 0))
    check("brak prognozy PV na dziś", "pv_today" in ids(got) and "pv_tomorrow" not in ids(got), got)
    got = ISS.collect(rt, at(2026, 11, 20, 19, 0))
    check("po 18:00 brak prognozy na jutro", "pv_tomorrow" in ids(got), got)
    got = ISS.collect(rt, at(2026, 11, 20, 2, 0))
    check("w nocy (przed 4:00) brak prognozy dziś nie jest zgłaszany", "pv_today" not in ids(got), got)

    # ---------- plan
    hass, c, sched, rt = await env()
    now = at(2026, 11, 20, 20, 0)
    rt._plan = {"error": "SOC niedostępny — nie można zaproponować harmonogramu.", "generated_at": now.isoformat()}
    got = ISS.collect(rt, now)
    check("plan z błędem → poziom error", got and got[0]["id"] == "plan_error" and got[0]["level"] == "error", got)
    rt._plan = {"generated_at": (now - timedelta(minutes=90)).isoformat()}
    got = ISS.collect(rt, now)
    check("plan sprzed 90 min → ostrzeżenie o braku odświeżania", "plan_stale" in ids(got) and "90 min" in next(i for i in got if i["id"] == "plan_stale")["detail"], got)
    rt._plan = {"generated_at": (now - timedelta(minutes=5)).isoformat()}
    check("świeży plan → bez uwag", "plan_stale" not in ids(ISS.collect(rt, now)))

    # ---------- alarmy, kolizja okien, urządzenia, naprawione dane
    hass, c, sched, rt = await env()
    S = hass.states
    now = at(2026, 11, 20, 20, 0)
    rt.state["alarms_active"] = {"sensor.inverter_fault": "F23 Leakage"}
    got = ISS.collect(rt, now)
    check("alarm falownika → error i nazwa encji", got and got[0]["id"] == "alarms" and "F23" in got[0]["detail"], got)
    rt.state["alarms_active"] = {}
    for k, v in dict(start_grid_charge="22:00:00", stop_grid_charge="06:00:00", bateria_sprzedaz_start="05:00:00", bateria_sprzedaz_stop="08:00:00").items():
        S.set(f"time.bms_{k}", v)
    S.set("switch.bms_bateria_sprzedaz_1", "on"); S.set("switch.bms_ladowanie_z_sieci_1", "on")
    got = ISS.collect(rt, now)
    check("kolizja okien ładowania i sprzedaży → ostrzeżenie", "window_conflict" in ids(got), got)
    for k in ("start_grid_charge", "stop_grid_charge", "bateria_sprzedaz_start", "bateria_sprzedaz_stop"):
        S.set(f"time.bms_{k}", "00:00:00")
    rt.devices.set_devices([{"id": "boj", "name": "Bojler", "category": "boiler", "power_eid": "sensor.boj_p", "switch_eid": "switch.boj", "ctl_mode": "cheap"}])
    S.set("switch.boj", "unavailable")
    got = ISS.collect(rt, now)
    check("sterowanie wyłączone → niedostępny przełącznik nie jest zgłaszany", "devices_switch" not in ids(got), got)
    S.set("switch.bms_device_control", "on")
    got = ISS.collect(rt, now)
    check("sterowanie włączone + przełącznik niedostępny → ostrzeżenie z nazwą", "devices_switch" in ids(got) and "Bojler" in next(i for i in got if i["id"] == "devices_switch")["detail"], got)
    S.set("switch.boj", "off")
    check("przełącznik wrócił → problem znika", "devices_switch" not in ids(ISS.collect(rt, now)))
    rt.ledger.integrity.note("dni księgi: pominięto 2 uszkodzonych wpisów")
    got = ISS.collect(rt, now)
    check("naprawione dane przy starcie → informacja", "data_repaired" in ids(got) and next(i for i in got if i["id"] == "data_repaired")["level"] == "info", got)

    # ---------- taryfa dynamiczna: ceny zakupu
    hass, c, sched, rt = await env()
    S = hass.states
    tar.set_profile(tar.make_profile({"tariff_mode": "dynamic"}, prices_fn=sched.buy_hourly_for, eff_fn=lambda: 0.9, source="sensor.pstryk_current_buy_price"))
    now = at(2026, 11, 20, 12, 0)
    got = ISS.collect(rt, now)
    check("taryfa dynamiczna bez cen zakupu na dziś → ostrzeżenie", "buy_today" in ids(got), got)
    S.set(c.config["price_buy_entity"] if "price_buy_entity" in c.config else const.DEFAULT_PRICE_BUY_ENTITY, 0.8,
          {"prices": arr(date(2026, 11, 20), lambda h: 0.8)})
    sched.config["price_buy_entity"] = const.DEFAULT_PRICE_BUY_ENTITY
    got = ISS.collect(rt, at(2026, 11, 20, 12, 0))
    check("są ceny na dziś, jutro jeszcze nie opublikowane (12:00) → bez uwag o zakupie", "buy_today" not in ids(got) and "buy_tomorrow" not in ids(got), got)
    got = ISS.collect(rt, at(2026, 11, 20, 17, 0))
    bt = [i for i in got if i["id"] == "buy_tomorrow"]
    check("po 16:00 brak cen zakupu na jutro → wpis z wyjaśnieniem", bt and bt[0]["level"] in ("info", "warn") and bt[0]["detail"], got)
    tar.set_profile(tar.make_profile({"tariff_mode": "zone"}, prices_fn=lambda d: None, eff_fn=lambda: 0.9, source=""))

    # ---------- kolejność, odporność, limit
    hass, c, sched, rt = await env()
    now = at(2026, 11, 20, 20, 0)
    rt.state["alarms_active"] = {"sensor.f": "x"}
    rt._plan = {"generated_at": (now - timedelta(minutes=90)).isoformat()}
    rt.ledger.integrity.note("x")
    lv = [i["level"] for i in ISS.collect(rt, now)]
    check("błędy przed ostrzeżeniami przed informacjami", lv == sorted(lv, key={"error": 0, "warn": 1, "info": 2}.get), lv)
    def boom(): raise RuntimeError("kaput")
    sched.rce_arrays = boom
    got = ISS.collect(rt, now)
    check("awaria jednej kontroli (RCE) nie zasłania pozostałych", "alarms" in ids(got) and "plan_stale" in ids(got), got)
    check("lista ma limit", len(ISS.collect(rt, now)) <= ISS.MAX_ISSUES)
    json.dumps(ISS.collect(rt, now), allow_nan=False)

    # ---------- runtime: odświeżanie co minutę i „od kiedy”
    hass, c, sched, rt = await env()
    t0 = at(2026, 11, 20, 20, 0)
    rt.state["alarms_active"] = {"sensor.f": "x"}
    await rt.issues_tick(t0)
    first = rt.issues[0]["since"]
    check("issues_tick: lista z polem since", rt.issues and rt.issues[0]["id"] == "alarms" and first == round(t0.timestamp()), rt.issues)
    rt.state["alarms_active"] = {}
    await rt.issues_tick(t0 + timedelta(seconds=20))
    check("w ciągu minuty lista się nie przelicza (oszczędność)", rt.issues and rt.issues[0]["id"] == "alarms")
    await rt.issues_tick(t0 + timedelta(seconds=70))
    check("po minucie problem zniknął z listy", rt.issues == [], rt.issues)
    rt.state["alarms_active"] = {"sensor.f": "y"}
    await rt.issues_tick(t0 + timedelta(minutes=10))
    check("nawrót problemu = nowe „od kiedy”", rt.issues[0]["since"] == round((t0 + timedelta(minutes=10)).timestamp()), rt.issues)
    await rt.issues_tick(t0 + timedelta(minutes=12))
    await rt.issues_tick(t0 + timedelta(minutes=13))
    check("trwający problem zachowuje „od kiedy”", rt.issues[0]["since"] == round((t0 + timedelta(minutes=10)).timestamp()), rt.issues)
    await rt.tick(at(2026, 11, 20, 21, 0))
    check("tick runtime odświeża listę", isinstance(rt.issues, list))

    # ---------- sensor i raport
    s = BmsRuntimeSensor(c, "monitor_status", "x", None, "mdi:x"); s.coordinator = c
    a = s.extra_state_attributes
    check("sensor monitor_status: atrybut issues", "issues" in a and isinstance(a["issues"], list) and json.dumps(a["issues"], allow_nan=False))
    check("issues nie trafia do bazy (unrecorded)", "issues" in BmsRuntimeSensor._unrecorded_attributes)
    from custom_components.bms_komp_dec import diagnostics as DG
    rep = await DG.async_build_report(rt)
    check("raport diagnostyczny ma sekcję „Co dziś nie działa”", "Co dziś nie działa" in rep["text"], rep["text"][:300])

    print(f"ISSUES PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
