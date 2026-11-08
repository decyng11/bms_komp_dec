"""0.8.1: konfigurator powiadomień — włączanie, telefon / tylko HA, odstęp, cisza nocna, progi; nowe zdarzenia;
podsumowania dnia / tygodnia / miesiąca; usługi."""
import asyncio, sys, types
from common import *   # noqa
import common
from custom_components.bms_komp_dec import notify_cfg as N, monitor as mon
from homeassistant.exceptions import HomeAssistantError

def push(h): return [c for c in h.services.calls if c[0] == "notify"]
def pn(h, nid=None): return [c for c in h.services.calls if c[0] == "persistent_notification" and c[1] == "create" and (nid is None or c[2].get("notification_id") == nid)]
def clear(h): h.services.calls.clear()
def env():
    hass, c, opt, rt = build()
    c.config["notify_service"] = "notify.mobile_app_tel"
    hass.states.set("switch.bms_notifications_enabled", "on")
    return hass, c, opt, rt
def setcfg(rt, kinds=None, sched=None):
    rt.state["notify_cfg"] = N.effective({"kinds": kinds or {}, "sched": sched or {}})

async def main():
    # ---------- 1. ustawienia: domyślne, śmieci, cisza nocna
    e = N.effective(None)
    check("domyślne: wszystkie rodzaje z katalogu", set(e["kinds"]) == set(N.CATALOG) and len(N.CATALOG) >= 30, len(N.CATALOG))
    check("domyślne: niski SOC włączony, na telefon, 6 h", e["kinds"]["low_soc"] == {"on": True, "phone": True, "cooldown": 360, "quiet_ok": False})
    g = N.effective({"kinds": {"low_soc": {"on": "tak", "cooldown": 7, "phone": False}, "nieznany": {"on": True}, "weak_pv": {"thr": 9999}},
                     "sched": {"quiet": {"on": True, "start": "25:00", "end": "07:00"}, "weekly": {"weekday": 9}, "monthly": {"day": 31}}})
    check("śmieci: zły typ i spoza listy odstępów ignorowane, poprawne pola przyjęte", g["kinds"]["low_soc"]["on"] is True and g["kinds"]["low_soc"]["cooldown"] == 360 and g["kinds"]["low_soc"]["phone"] is False)
    check("śmieci: nieznany rodzaj pominięty", "nieznany" not in g["kinds"])
    check("próg przycięty do zakresu", g["kinds"]["weak_pv"]["thr"] == 50.0, g["kinds"]["weak_pv"])
    check("zła godzina / dzień → domyślne", g["sched"]["quiet"]["start"] == "22:00" and g["sched"]["weekly"]["weekday"] == 6 and g["sched"]["monthly"]["day"] == 1, g["sched"])
    q = N.effective({"sched": {"quiet": {"on": True, "start": "22:00", "end": "07:00"}}})
    check("cisza nocna przez północ", N.in_quiet(q, 23, 0) and N.in_quiet(q, 6, 59) and not N.in_quiet(q, 7, 0) and not N.in_quiet(q, 21, 59))
    q2 = N.effective({"sched": {"quiet": {"on": True, "start": "13:00", "end": "15:00"}}})
    check("cisza w dzień", N.in_quiet(q2, 14, 0) and not N.in_quiet(q2, 15, 0))
    check("cisza wyłączona", not N.in_quiet(N.effective(None), 23, 0))
    check("każdy domyślny odstęp jest na liście do wyboru (karta pokaże go poprawnie)", all(spec[5] in N.COOLDOWNS for spec in N.CATALOG.values()), [k for k, spec in N.CATALOG.items() if spec[5] not in N.COOLDOWNS])
    check("katalog dla karty: grupy, progi", all(x["group"] in N.GROUPS for x in N.catalog_payload()) and any("thr" in x for x in N.catalog_payload()))

    # ---------- 2. wysyłka wg ustawień
    hass, c, opt, rt = env(); n = rt.monitor.notifier
    at(2026, 11, 5, 12, 0)
    ok = await n.send("low_soc", "T", "M")
    check("domyślnie: HA + telefon", ok and len(pn(hass)) == 1 and len(push(hass)) == 1)
    clear(hass); ok = await n.send("low_soc", "T", "M")
    check("odstęp 6 h: drugie od razu nie idzie", not ok and not pn(hass))
    setcfg(rt, {"low_soc": {"cooldown": 0}}); clear(hass)
    check("odstęp 0: idzie zawsze", await n.send("low_soc", "T", "M") and len(push(hass)) == 1)
    setcfg(rt, {"low_soc": {"on": False}}); clear(hass)
    r = await n.send("low_soc", "T", "M")
    check("wyłączony rodzaj: nic nie wysyła, ale jest w dzienniku", not r and not hass.services.calls and "wyłączone w konfiguratorze" in rt.log.last(1)[0]["msg"])
    setcfg(rt, {"low_soc": {"phone": False, "cooldown": 0}}); clear(hass)
    await n.send("low_soc", "T", "M")
    check("tylko HA: bez pusha", len(pn(hass)) == 1 and not push(hass))
    setcfg(rt, {"low_soc": {"cooldown": 0}, "alarm": {"cooldown": 0}}, {"quiet": {"on": True, "start": "22:00", "end": "07:00"}})
    at(2026, 11, 5, 23, 30); clear(hass)
    await n.send("low_soc", "T", "M")
    check("cisza nocna: zwykłe tylko w HA", len(pn(hass)) == 1 and not push(hass))
    clear(hass); await n.send("alarm", "A", "M")
    check("cisza nocna: alarm przechodzi na telefon", len(push(hass)) == 1)
    setcfg(rt, {"alarm": {"quiet_ok": False, "cooldown": 0}}, {"quiet": {"on": True, "start": "22:00", "end": "07:00"}}); clear(hass)
    await n.send("alarm", "A", "M")
    check("alarm z wyłączonym „przez ciszę” też czeka", not push(hass))
    clear(hass); await n.send("test", "T", "M", force=True)
    check("test: pomija ciszę i odstępy", len(push(hass)) == 1)
    hass.states.set("switch.bms_notifications_enabled", "off"); clear(hass)
    check("główny wyłącznik nadal wycisza wszystko", not await n.send("alarm", "A", "M", key="x2") and not hass.services.calls)

    # ---------- 3. zdarzenia z monitora
    hass, c, opt, rt = env(); n = rt.monitor.notifier
    S = hass.states
    setcfg(rt, {"battery_full": {"on": True}, "high_import": {"on": True}})
    t = at(2026, 11, 5, 13, 0); S.set(c.config["soc"], 100); await rt.monitor._battery_full(t); await rt.monitor._battery_full(t)
    check("bateria pełna: raz na dobę", len(pn(hass, "bms_battery_full")) == 1)
    setcfg(rt, {"battery_full": {"on": True, "cooldown": 0}, "high_import": {"on": True}})
    await rt.monitor._battery_full(at(2026, 11, 5, 15, 0))
    check("bateria pełna: raz na dobę także przy odstępie 0", len(pn(hass, "bms_battery_full")) == 1)
    await rt.monitor._battery_full(at(2026, 11, 6, 9, 0))
    check("bateria pełna: następnego dnia znowu", len(pn(hass, "bms_battery_full")) == 2)
    setcfg(rt, {"battery_temp_high": {"cooldown": 0}, "battery_temp_low": {"cooldown": 0}, "high_import": {"on": True}})
    S.set(c.config["battery_temperature"], 50); await rt.monitor._battery_temp(t); await rt.monitor._battery_temp(t); await rt.monitor._battery_temp(t)
    S.set(c.config["battery_temperature"], 44); await rt.monitor._battery_temp(t)
    S.set(c.config["battery_temperature"], 46); await rt.monitor._battery_temp(t)
    check("temperatura wysoka: raz, do spadku poniżej progu − 3 (wahania 44–46 °C nie powtarzają)", len(pn(hass, "bms_battery_temp_high")) == 1)
    S.set(c.config["battery_temperature"], 20); await rt.monitor._battery_temp(t)
    S.set(c.config["battery_temperature"], 1); await rt.monitor._battery_temp(t)
    check("temperatura niska (próg 3 °C)", len(pn(hass, "bms_battery_temp_low")) == 1)
    S.set(c.config["grid_voltage_l1"], 0); await rt.monitor._grid_outage(at(2026, 11, 5, 13, 0)); await rt.monitor._grid_outage(at(2026, 11, 5, 13, 0, 40))
    check("zanik sieci: nie od razu (60 s)", not pn(hass, "bms_grid_outage"))
    await rt.monitor._grid_outage(at(2026, 11, 5, 13, 1, 30))
    check("zanik sieci po 60 s", len(pn(hass, "bms_grid_outage")) == 1 and "zanik" in pn(hass, "bms_grid_outage")[0][2]["title"])
    S.set(c.config["grid_voltage_l1"], 231); await rt.monitor._grid_outage(at(2026, 11, 5, 13, 20))
    gp = pn(hass, "bms_grid_outage")
    check("powrót sieci z czasem przerwy", len(gp) == 2 and "wróciła" in gp[1][2]["title"] and "20 min" in gp[1][2]["message"], gp[-1])
    S.set(c.config["grid_power"], 8000); await rt.monitor._high_import(at(2026, 11, 5, 14, 0)); await rt.monitor._high_import(at(2026, 11, 5, 14, 4))
    check("pobór > 7 kW: nie przed 5 min", not pn(hass, "bms_high_import"))
    await rt.monitor._high_import(at(2026, 11, 5, 14, 6))
    check("pobór > 7 kW przez 5 min", len(pn(hass, "bms_high_import")) == 1)
    # ceny jutro
    d1 = date(2026, 11, 6)
    opt._read_rce_arrays = lambda: {d1.isoformat(): [0.4] * 10 + [-0.05, -0.02, 0.0] + [0.4] * 6 + [1.35] + [0.4] * 4}
    opt.rce_expected_hours = lambda d: 24
    rt._plan = {"proposals": {"bateria_sprzedaz_start": {"proposed": "19:00", "skip": False}}}
    await rt.monitor._prices_tomorrow(at(2026, 11, 5, 13, 0))
    check("ceny jutro: nie przed 14:00", not pn(hass, "bms_rce_negative"))
    await rt.monitor._prices_tomorrow(at(2026, 11, 5, 15, 0)); await rt.monitor._prices_tomorrow(at(2026, 11, 5, 16, 0))
    neg, hi = pn(hass, "bms_rce_negative"), pn(hass, "bms_rce_high")
    check("ceny ujemne jutro: godziny 10–13, raz", len(neg) == 1 and "10–13" in neg[0][2]["message"], neg)
    check("cena wysoka jutro: 19:00 i plan sprzedaży", len(hi) == 1 and "19:00" in hi[0][2]["message"] and "start 19:00" in hi[0][2]["message"], hi)
    opt._read_rce_arrays = lambda: {d1.isoformat(): [0.4] * 20}
    hass2 = hass; clear(hass2); rt.state["notify_once"] = {}
    await rt.monitor._prices_tomorrow(at(2026, 11, 5, 15, 0))
    check("niepełne ceny jutro: brak powiadomień o cenach", not pn(hass, "bms_rce_negative") and not pn(hass, "bms_rce_high"))
    # źródła
    opt._read_pv_hourly = lambda off: None
    await rt.monitor._sources(at(2026, 11, 5, 18, 30)); await rt.monitor._sources(at(2026, 11, 5, 19, 30))
    check("brak prognozy PV na jutro: raz na dobę", len(pn(hass, "bms_pv_forecast_missing")) == 1)
    # zużycie
    c.data["load_forecast"] = {"days": [{"label": "Wczoraj"}, {"label": "Dziś", "forecast": 10.0, "nowcast": 12.0}]}
    await rt.monitor._load_above(at(2026, 11, 5, 15, 0))
    check("zużycie +20% < próg 30%: bez powiadomienia", not pn(hass, "bms_load_above"))
    c.data["load_forecast"] = {"days": [{"label": "Wczoraj"}, {"label": "Dziś", "forecast": 10.0, "nowcast": 14.0}]}
    await rt.monitor._load_above(at(2026, 11, 5, 11, 0))
    check("zużycie: nie przed 12:00", not pn(hass, "bms_load_above"))
    await rt.monitor._load_above(at(2026, 11, 5, 15, 0))
    check("zużycie +40% > próg 30%", len(pn(hass, "bms_load_above")) == 1 and "+40%" in pn(hass, "bms_load_above")[0][2]["message"])
    # słabe PV
    opt._read_pv_forecast_kwh = lambda k, d: 1.2
    rt._plan = {"proposals": {"start_grid_charge": {"proposed": "02:00", "skip": False}, "stop_grid_charge": {"proposed": "05:00"}}}
    await rt.monitor._weak_pv(at(2026, 11, 5, 17, 30))
    wp = pn(hass, "bms_weak_pv")
    check("słabe PV jutro + planowane ładowanie z sieci", len(wp) == 1 and "1.2 kWh" in wp[0][2]["message"] and "02:00–05:00" in wp[0][2]["message"], wp)
    # zdrowie baterii
    rt.stats.summary = lambda cap: {"eff_trend_pp": -4.0, "eff_30d": 84.0, "eff_90d": 88.0}
    await rt.monitor._health(at(2026, 11, 5, 12, 10))
    check("spadek sprawności o 4 pkt > próg 3", len(pn(hass, "bms_battery_health")) == 1)

    # ---------- 4. zdarzenia z runtime
    hass, c, opt, rt = env(); S = hass.states
    setcfg(rt, {"sale": {"on": True}, "grid_charge": {"on": True}, "schedule_skipped": {"on": True}, "price_reaction": {"on": True}})
    rt.state["grid_target_plan"] = {"target": 80.0}
    setcfg(rt, {"sale": {"on": True}, "grid_charge": {"on": True}, "schedule_skipped": {"on": True}, "price_reaction": {"on": True}, "grid_charge_target": {"cooldown": 0}})
    S.set(c.config["soc"], 60)
    await rt._notify_fired("stop_grid_charge", "wylacz_ladowanie_siec", "05:00", 60.0)
    check("koniec ładowania z sieci + poniżej celu (60 < 80 − 5)", len(pn(hass, "bms_grid_charge")) == 1 and len(pn(hass, "bms_grid_charge_target")) == 1)
    clear(hass); await rt._notify_fired("stop_grid_charge", "wylacz_ladowanie_siec", "05:00", 77.0)
    check("w granicy tolerancji: bez alarmu celu", not pn(hass, "bms_grid_charge_target"))
    await rt._notify_fired("bateria_sprzedaz_start_2", "sprzedaz_6000w", "19:00", 90.0)
    check("start sprzedaży (zestaw 2)", any("zestaw 2" in x[2]["message"] for x in pn(hass, "bms_sale")))
    rt._remember_grid_target({"generated_at": "x", "curve": {"grid": [0, 1, 1, 0], "target": [None, 70, 85, None]}})
    check("cel ładowania zapamiętany z planu (ostatnia godzina)", rt.state["grid_target_plan"]["target"] == 85.0)
    rt._log_skip("start_grid_charge", "02:00", "SOC za wysoki"); await settle(hass)
    check("pominięty start → powiadomienie", len(pn(hass, "bms_schedule_skipped")) == 1)
    # niepotwierdzona komenda
    hass.services.ignore.add("select.inverter_work_mode")
    S.set("select.inverter_work_mode", "Zero Export To Load", {"options": ["Selling First", "Zero Export To Load"]})
    await rt._verify("sprzedaz_6000w", "Sprzedaż", [("select", "select.inverter_work_mode", "Selling First")], rt._cmd_gen)
    check("falownik nie potwierdził komendy", len(pn(hass, "bms_command_unconfirmed")) == 1)
    # auto-stosowanie i propozycja przez konfigurator
    hass, c, opt, rt = env()
    setcfg(rt, {"proposal": {"phone": True}})
    async def sug(): return {"proposals": {"bateria_sprzedaz_start": {"label": "Start", "current": "18:00", "proposed": "19:00", "skip": False}}}
    opt.suggest = sug
    await automation.async_daily_suggest(rt, hass, opt)
    check("propozycja z 16:00 przez konfigurator (telefon włączony)", len(pn(hass, "bms_proposal")) == 1 and len(push(hass)) == 1)
    hass, c, opt, rt = env()
    await automation.async_daily_suggest(rt, hass, opt := types.SimpleNamespace(suggest=sug))
    check("propozycja: domyślnie tylko w HA (jak dotąd)", len(pn(hass, "bms_proposal")) == 1 and not push(hass))

    # ---------- 5. podsumowania
    hass, c, opt, rt = env()
    setcfg(rt, {"summary_daily": {"on": True}, "summary_weekly": {"on": True}}, {"daily": {"time": "21:00"}, "weekly": {"weekday": 6, "time": "20:00"}})
    for i in range(14):
        d = date(2026, 11, 8) - timedelta(days=i)
        rt.ledger.days[d.isoformat()] = {"export_kwh": 5.0, "import_kwh": 3.0, "revenue": 2.0 + i * 0.1, "cost": 1.0, "neg_export_kwh": 0.0}
        rt.stats.days[d.isoformat()] = {"pv": 20.0, "load": 12.0, "exp": 5.0, "imp": 3.0, "chg": 6.0, "dis": 5.0}
    rt.state["soc_day"] = {"date": "2026-11-08", "min": 21.0, "max": 98.0}
    await rt.monitor._summaries(at(2026, 11, 7, 20, 30))
    check("tygodniowe: nie w sobotę (ustawiona niedziela)", not pn(hass, "bms_summary_weekly"))
    hass.services.calls.clear(); rt.state["summary_sent"] = {}
    at(2026, 11, 8, 19, 0); rt.log.add("command", "Sprzedaż 6000W (harmonogram bateria_sprzedaz_start 19:00)", "ok")
    await rt.monitor._summaries(at(2026, 11, 8, 20, 59))
    check("dzienne: nie przed 21:00", not pn(hass, "bms_summary_daily"))
    await rt.monitor._summaries(at(2026, 11, 8, 21, 0)); await rt.monitor._summaries(at(2026, 11, 8, 21, 30))
    dsum = pn(hass, "bms_summary_daily")
    check("dzienne: raz o 21:00", len(dsum) == 1, dsum)
    m = dsum[0][2]["message"] if dsum else ""
    check("dzienne: bilans, energia, SOC, wykonane", "+1,00 zł" in m and "PV 20,0 kWh" in m and "min 21%, max 98%" in m and "Sprzedaż 6000W" in m, m)
    wsum = pn(hass, "bms_summary_weekly")
    check("tygodniowe: w niedzielę po 20:00, raz", len(wsum) == 1, wsum)
    w = wsum[0][2]["message"] if wsum else ""
    check("tygodniowe: sumy 7 dni i porównanie z poprzednim tygodniem", "02.11–08.11" in w and "+9,10 zł" in w and "Względem poprzedniego tygodnia: -4,90 zł" in w, w)
    # 0.8.6: błąd w liczeniu treści nie gubi podsumowania (wiadomość i tak wychodzi, błąd w dzienniku)
    hass, c, opt, rt = env()
    setcfg(rt, {"summary_daily": {"on": True}}, {"daily": {"time": "21:00"}})
    def boom(kind, day): raise ValueError("zepsute dane")
    rt.summary_text = boom
    await rt.monitor._summaries(at(2026, 11, 8, 21, 0)); await settle(hass)
    ds = pn(hass, "bms_summary_daily")
    check("dzienne: wyjątek w treści → wiadomość i tak wychodzi", len(ds) == 1 and "zepsute dane" in ds[0][2]["message"], ds)
    check("dzienne: błąd trafia do dziennika", any("nie udało się policzyć" in e["msg"] for e in rt.log.last(10)), rt.log.last(4))
    check("dzienne: po błędzie nie ponawia co 10 s", (await rt.monitor._summaries(at(2026, 11, 8, 21, 1))) is None and len(pn(hass, "bms_summary_daily")) == 1)
    hass, c, opt, rt = env()
    await rt.monitor._summaries(at(2026, 11, 8, 21, 30))
    check("dzienne domyślnie WŁĄCZONE: przychodzi po 21:00 bez ruszania konfiguratora", len(pn(hass, "bms_summary_daily")) == 1)
    check("tygodniowe domyślnie włączone: niedziela po 20:00", len(pn(hass, "bms_summary_weekly")) == 1)
    hass, c, opt, rt = env()
    await rt.monitor._summaries(at(2026, 11, 7, 21, 30))     # sobota
    check("domyślnie: sobota — dzienne tak, tygodniowego jeszcze nie", len(pn(hass, "bms_summary_daily")) == 1 and not pn(hass, "bms_summary_weekly"))
    hass, c, opt, rt = env()
    await rt.monitor._summaries(at(2026, 11, 8, 20, 59))
    check("domyślnie: przed 21:00 dzienne nie wychodzi", not pn(hass, "bms_summary_daily"))
    # miesięczne: dzień i godzina z konfiguratora
    setcfg(rt, {}, {"monthly": {"day": 3, "time": "10:00"}})
    rt.ledger.days["2026-10-15"] = {"export_kwh": 5.0, "import_kwh": 3.0, "revenue": 2.0, "cost": 1.0, "neg_export_kwh": 0.0}
    rt.ledger.days["2026-09-15"] = {"export_kwh": 5.0, "import_kwh": 3.0, "revenue": 0.5, "cost": 1.0, "neg_export_kwh": 0.0}
    await rt.report_tick(at(2026, 11, 1, 11, 0))
    check("miesięczne: nie 1. dnia, gdy ustawiono 3.", not pn(hass, "bms_summary_monthly"))
    await rt.report_tick(at(2026, 11, 3, 9, 59))
    check("miesięczne: nie przed 10:00", not pn(hass, "bms_summary_monthly"))
    await rt.report_tick(at(2026, 11, 3, 10, 0))
    ms = pn(hass, "bms_summary_monthly")
    check("miesięczne: 3. dnia o 10:00 z porównaniem", len(ms) == 1 and "Względem poprzedniego miesiąca" in ms[0][2]["message"], ms)

    # ---------- 6. usługi
    hass, c, opt, rt = env()
    hass.auth = types.SimpleNamespace(async_get_user=lambda uid: _u(uid))
    async def _u(uid): return types.SimpleNamespace(is_admin=(uid == "admin"))
    globals()["_u"] = _u
    common.pkg._register_services(hass)
    hass.data = {"bms_komp_dec": {"e": c}}
    c.__class__ = type("C", (c.__class__, pkg.BmsCoordinator), {}) if False else c.__class__
    pkg._get_runtime = lambda h: rt
    H = {n: h for (d, n), (h, _r) in hass.services.handlers.items() if d == "bms_komp_dec"}
    call = lambda data, uid="admin": types.SimpleNamespace(data=data, context=types.SimpleNamespace(user_id=uid))
    r = await H["notify_settings_get"](call({}))
    check("usługa: odczyt ustawień i katalogu", "settings" in r and len(r["catalog"]) == len(N.CATALOG) and r["notify_service"] == "notify.mobile_app_tel")
    r = await H["notify_settings_set"](call({"settings": {"kinds": {"sale": {"on": True}}, "sched": {"quiet": {"on": True}}}}))
    check("usługa: zapis ustawień", rt.state["notify_cfg"]["kinds"]["sale"]["on"] and rt.state["notify_cfg"]["sched"]["quiet"]["on"])
    try:
        await H["notify_settings_set"](call({"settings": "x"})); bad = False
    except HomeAssistantError: bad = True
    check("usługa: zły format → błąd", bad)
    try:
        await H["notify_settings_set"](call({"settings": {}}, uid="user")); denied = False
    except Exception as e_: denied = "Unauthorized" in type(e_).__name__
    check("usługa: zwykły użytkownik nie zapisze", denied)
    clear(hass); await H["notify_test"](call({}))
    check("usługa: wiadomość testowa na telefon", len(push(hass)) == 1)

    print(f"NOTIFY PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)
asyncio.run(main())
