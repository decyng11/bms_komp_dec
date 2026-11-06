"""0.8.1: prognoza PV z Forecast.Solar (platforma energy HA), sumowanie połaci, jednostki, karta; zużycie dziś
w planie z tempa dnia; profil roboczy/wolny; pstryk-ha-next (gross/net)."""
import asyncio, sys, types
from datetime import date, datetime, timedelta, timezone
exec(open("test_dynamic_tariff.py").read().split("async def main():")[0])
from custom_components.bms_komp_dec import pv_forecast as PF, load_forecast as LF, presets as PR
PASS = FAIL = 0
def check(name, cond, info=""):
    global PASS, FAIL
    if cond: PASS += 1; print("ok  ", name)
    else: FAIL += 1; print("FAIL", name, info)
TZ1 = timezone(timedelta(hours=1))
FS_DAY = {7: 120, 8: 480, 9: 900, 10: 1300, 11: 1500, 12: 1450, 13: 1200, 14: 800, 15: 350, 16: 60}   # Wh w godzinie (od początku okresu)

def install_fs(hass, entries, per_entry):
    """Atrapa Forecast.Solar: wpisy w config_entries, energy.async_get_solar_forecast i rejestr encji."""
    ents = [types.SimpleNamespace(entry_id=f"fs{i}", state=types.SimpleNamespace(value="loaded"), domain="forecast_solar") for i in range(entries)]
    other = getattr(hass, "config_entries", None)
    hass.config_entries = types.SimpleNamespace(async_entries=lambda dom=None: ents if dom == "forecast_solar" else [], async_get_entry=lambda i: None)
    m = types.ModuleType("homeassistant.components.forecast_solar.energy")
    async def get(h, eid):
        return per_entry(eid)
    m.async_get_solar_forecast = get
    sys.modules["homeassistant.components.forecast_solar"] = types.ModuleType("homeassistant.components.forecast_solar")
    sys.modules["homeassistant.components.forecast_solar.energy"] = m
    reg = {"sensor.energy_production_today": "forecast_solar", "sensor.energy_production_tomorrow": "forecast_solar"}
    sys.modules["homeassistant.helpers.entity_registry"].async_get = lambda h: types.SimpleNamespace(
        async_get=lambda e: types.SimpleNamespace(platform=reg[e]) if e in reg else None, entities={}, async_get_entity_id=lambda *a: None)

def wh_hours(days, scale=1.0):
    out = {}
    for d in days:
        for h, v in FS_DAY.items():
            out[datetime(d.year, d.month, d.day, h, tzinfo=TZ1).isoformat()] = v * scale
    return out

async def main():
    # ---------- 1. Forecast.Solar: plan dostaje prognozę godzinową
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), soc=60.0, mode="zone", buy=("g12w",), pv=1.2)
    for e in ("sensor.solcast_pv_forecast_forecast_today", "sensor.solcast_pv_forecast_forecast_tomorrow"):
        hass.states._d.pop(e, None) if hasattr(hass.states, "_d") else None
    sch.config["pv_forecast_today"] = "sensor.energy_production_today"; sch.config["pv_forecast_tomorrow"] = "sensor.energy_production_tomorrow"
    hass.states.set("sensor.energy_production_today", 8.16, {"unit_of_measurement": "kWh"})
    hass.states.set("sensor.energy_production_tomorrow", 8.16, {"unit_of_measurement": "kWh"})
    install_fs(hass, 1, lambda eid: {"wh_hours": wh_hours([d0, d1])})
    await sch.pv_fc.async_refresh(force=True)
    h1 = sch._read_pv_hourly(1)
    check("FS: prognoza godzinowa jutro (kWh/h)", h1 and abs(h1[11] - 1.5) < 1e-9 and h1[3] == 0.0, h1)
    check("FS: suma godzin = suma dzienna", h1 and abs(sum(h1) - 8.16) < 1e-6, h1 and sum(h1))
    res = await sch.suggest(); P = res["proposals"]
    check("FS: plan nie pomija blokady PV z powodu braku prognozy", "brak prognozy godzinowej" not in (P.get("pv_export_start", {}).get("reason") or ""), P.get("pv_export_start"))
    cur = res["curve"]
    check("FS: krzywa planu ma PV jutro w dzień", max(cur["pv"]) > 1.0, cur["pv"])
    a = res["assumptions"]
    check("FS: założenia planu podają źródło Forecast.Solar", a["pv_source"] == "Forecast.Solar" and a["pv_hourly_tomorrow"] and a["pv_tomorrow_kwh"] == 8.2, a)
    pay = sch.pv_card_payload()
    check("FS: dane dla karty — godziny dziś/jutro i 7 dni", pay["pv_hourly_tomorrow"] and len(pay["pv_daily"]) == 7 and pay["pv_daily"][1]["kwh"] == 8.16 and pay["pv_forecast_source"] == "Forecast.Solar", pay)
    check("FS: dni bez prognozy = None (nie zero)", pay["pv_daily"][3]["kwh"] is None, pay["pv_daily"][3])
    # ---------- 2. dwie połacie (dwa wpisy) → suma
    install_fs(hass, 2, lambda eid: {"wh_hours": wh_hours([d0, d1], 1.0 if eid == "fs0" else 0.5)})
    await sch.pv_fc.async_refresh(force=True)
    check("FS: dwie połacie — godziny sumowane", abs(sch._read_pv_hourly(1)[11] - 2.25) < 1e-9, sch._read_pv_hourly(1)[11])
    check("FS: dwie połacie — suma dzienna z obu (encja jednego wpisu ma tylko swoją)", abs(sch._read_pv_forecast_kwh("pv_forecast_tomorrow", "") - 12.24) < 1e-6, sch._read_pv_forecast_kwh("pv_forecast_tomorrow", ""))
    # ---------- 3. jednostki
    install_fs(hass, 1, lambda eid: {"wh_hours": wh_hours([d0, d1])})
    await sch.pv_fc.async_refresh(force=True)
    hass.states.set("sensor.energy_production_today", 8160, {"unit_of_measurement": "Wh"})
    check("suma dzienna w Wh przeliczona na kWh", abs(sch._read_pv_forecast_kwh("pv_forecast_today", "") - 8.16) < 1e-9, sch._read_pv_forecast_kwh("pv_forecast_today", ""))
    check("state_kwh: MWh", PF.state_kwh(types.SimpleNamespace(states=types.SimpleNamespace(get=lambda e: types.SimpleNamespace(state="0.01", attributes={"unit_of_measurement": "MWh"}))), "x") == 10.0)
    # ---------- 4. odświeżanie co 10 min, błędy
    calls = []
    install_fs(hass, 1, lambda eid: (calls.append(eid), {"wh_hours": wh_hours([d0, d1])})[1])
    await sch.pv_fc.async_refresh(force=True); await sch.pv_fc.async_refresh(); await sch.pv_fc.async_refresh()
    check("FS: bez odpytywania co minutę (raz na 10 min)", len(calls) == 1, calls)
    def boom(eid): raise RuntimeError("x")
    install_fs(hass, 1, boom)
    await sch.pv_fc.async_refresh(force=True)
    check("FS: wyjątek platformy nie psuje planu (zostają poprzednie dane)", sch._read_pv_hourly(1) is not None and sch.pv_fc.fs_error)
    install_fs(hass, 0, lambda eid: None)
    await sch.pv_fc.async_refresh(force=True)
    check("bez Forecast.Solar i Solcasta: brak prognozy godzinowej", sch._read_pv_hourly(1) is None)
    # ---------- 5. Solcast nadal ma pierwszeństwo
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), soc=60.0, mode="zone", buy=("g12w",), pv=1.2)
    install_fs(hass, 1, lambda eid: {"wh_hours": wh_hours([d0, d1], 3.0)})
    await sch.pv_fc.async_refresh(force=True)
    check("Solcast ma pierwszeństwo przed Forecast.Solar", abs(sch._read_pv_hourly(1)[11] - 1.2) < 1e-9, sch._read_pv_hourly(1)[11])
    check("źródło: Solcast", sch.pv_source() == "Solcast")

    # ---------- 6. zużycie: godziny do północy z tempa dnia
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), soc=60.0, mode="zone", buy=("g12w",), pv=1.2, load=12.0)
    base = await sch.suggest()
    rem = [None] * 21 + [1.0, 1.0, 1.0]
    c.data["load_forecast"]["hourly_remaining_today"] = rem
    res = await sch.suggest()
    t0 = datetime.fromisoformat(res["curve"]["start"])
    i22 = [i for i in range(res["curve"]["hours"]) if (t0 + timedelta(hours=i)).hour == 22 and (t0 + timedelta(hours=i)).date() == d0][0]
    check("plan: zużycie dziś wieczorem z tempa dnia (1,0 kWh/h zamiast profilu jutra)", res["curve"]["load"][i22] == 1.0 and base["curve"]["load"][i22] == 0.5, (res["curve"]["load"][i22], base["curve"]["load"][i22]))
    j = [i for i in range(res["curve"]["hours"]) if (t0 + timedelta(hours=i)).date() == d1 and (t0 + timedelta(hours=i)).hour == 22][0]
    check("plan: godziny jutra nadal z prognozy jutra", res["curve"]["load"][j] == 0.5, res["curve"]["load"][j])
    check("plan: większe zużycie wieczorem → niższy SOC o północy", res["curve"]["soc"][i22 + 1] < base["curve"]["soc"][i22 + 1], (res["curve"]["soc"][i22 + 1], base["curve"]["soc"][i22 + 1]))
    check("założenia: zużycie dziś z tempa dnia", res["assumptions"]["load_today_source"] == "tempo dnia" and res["assumptions"]["load_rest_today_kwh"] == 3.0, res["assumptions"])
    c.data["load_forecast"]["hourly_remaining_today"] = ["x", None, float("nan")] + [None] * 21
    check("śmieci w liście zużycia → profil (bez wyjątku)", (await sch.suggest())["assumptions"]["load_today_source"] == "profil")
    # rezerwa też widzi tempo dnia
    c.data["load_forecast"]["hourly_forecast"] = [0.5] * 24
    c.data["load_forecast"]["hourly_remaining_today"] = rem
    rt._reserve_cache = None
    r_hi = rt.reserve()["need_kwh"]
    c.data["load_forecast"]["hourly_remaining_today"] = None; rt._reserve_cache = None
    r_base = rt.reserve()["need_kwh"]
    check("rezerwa: wyższe zużycie do północy → większa potrzeba", r_hi > r_base, (r_hi, r_base))

    # ---------- 7. load_forecast: pozostałe dziś i profil roboczy/wolny
    cls = [v for v in vars(LF).values() if isinstance(v, type) and "_average_profile" in vars(v)][0]
    lf = object.__new__(cls); lf.hass = hass
    work = [0.02] * 6 + [0.08] * 3 + [0.03] * 8 + [0.06] * 5 + [0.03] * 2
    off = [0.03] * 9 + [0.06] * 8 + [0.04] * 5 + [0.03] * 2
    lf.profiles = {}
    for i in range(1, 22):
        d = date(2026, 11, 4) - timedelta(days=i)
        p = off if d.weekday() >= 5 else work
        s = sum(p); lf.profiles[d.isoformat()] = [x / s for x in p]
    pw, po = lf._average_profile(False), lf._average_profile(True)
    check("profil dni roboczych ≠ profil weekendu", pw and po and abs(pw[7] - po[7]) > 0.01, (pw and pw[7], po and po[7]))
    check("profil weekendu = średnia z weekendów", abs(po[12] - off[12] / sum(off)) < 1e-9)
    lf.profiles = {k: v for k, v in list(lf.profiles.items())[:5]}
    check("za mało dni danego typu → profil ze wszystkich dni", lf._average_profile(True) == lf._average_profile(None))
    now = datetime(2026, 11, 4, 20, 30, tzinfo=TZ1)
    kwh, hrs = lf._remaining_today(now, 12.0, 10.5)
    check("pozostało dziś = prognoza bieżąca − zużycie dotychczas", kwh == 1.5 and hrs[19] is None and abs(sum(x for x in hrs if x) - 1.5) < 0.01, (kwh, hrs))
    check("bieżąca godzina proporcjonalnie (30 min z 60)", hrs[20] < hrs[21], (hrs[20], hrs[21]))
    check("zużycie powyżej prognozy → 0, nie ujemne", lf._remaining_today(now, 10.0, 12.0)[0] == 0.0)
    check("brak prognozy → None", lf._remaining_today(now, None, 1.0) == (None, None))

    # ---------- 8. pstryk-ha-next (Miosp): ceny gross/net, wykrywanie
    hass, c, sch, rt, d0, d1 = await env((2026, 11, 4, 20, 30), soc=30.0, buy=None, cfg_extra={"price_buy_entity": "sensor.pstryk_current_price", "tariff_mode": "auto"})
    fr = lambda d, p: [{"start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "gross": p[h], "net": round(p[h] / 1.23, 4), "is_cheap": False} for h in range(24)]
    hass.states.set("sensor.pstryk_current_price", TODAY[20], {"basis": "gross", "today_prices": fr(d0, TODAY), "tomorrow_prices": fr(d1, TOMOR)})
    b0 = sch.buy_hourly_for(d0); b1 = sch.buy_hourly_for(d1)
    check("pstryk-ha-next: ceny brutto dziś i jutro", b0 and b1 and abs(b0[8] - TODAY[8]) < 1e-9 and abs(b1[3] - TOMOR[3]) < 1e-9, (b0 and b0[8], b1 and b1[3]))
    T.set_profile(T.make_profile(sch.config, prices_fn=sch.buy_hourly_for, eff_fn=lambda: 0.9, source="test"))
    res = await sch.suggest(); st = res["proposals"].get("start_grid_charge", {})
    check("pstryk-ha-next: plan ładuje w najtańszych godzinach", not st.get("skip") and "najtańsze godziny" in (st.get("reason") or ""), st)
    hass.states.set("sensor.pstryk_current_price", 0.6, {"basis": "net", "today_prices": fr(d0, TODAY), "tomorrow_prices": fr(d1, TOMOR)})
    b0 = sch.buy_hourly_for(d0)
    check("pstryk-ha-next: basis=net → ceny netto (jak stan encji)", b0 and abs(b0[8] - round(TODAY[8] / 1.23, 4)) < 1e-9, b0 and b0[8])
    h3 = stubs.FakeHass(); h3.states.set("sensor.pstryk_current_price", 0.7, {})
    check("wykrywanie: sensor.pstryk_current_price jako cena zakupu", PR.detect_price_entities(h3).get("price_buy_entity") == "sensor.pstryk_current_price", PR.detect_price_entities(h3))
    h4 = stubs.FakeHass(); h4.states.set("sensor.pstryk_current_price", 0.7, {}); h4.states.set("sensor.pstryk_current_buy_price", 0.7, {})
    check("wykrywanie: balgerion/kriskomp nadal przed pstryk-ha-next", PR.detect_price_entities(h4).get("price_buy_entity") == "sensor.pstryk_current_buy_price")
    print(f"PV-FORECAST PASS={PASS} FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)
asyncio.run(main())
