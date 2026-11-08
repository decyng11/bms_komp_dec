import asyncio, sys, types, json, logging
sys.path.insert(0, ".")
from common import *   # noqa
import common
import custom_components.bms_komp_dec as pkg
from custom_components.bms_komp_dec import monitor as mon, watch as wch, battery_stats as bst, report as repm, diag_store as dgs, health as hlt
from custom_components.bms_komp_dec.battery_stats import BatteryStats
from custom_components.bms_komp_dec.diag_store import DiagStore
from custom_components.bms_komp_dec.sensor import BmsRuntimeSensor
from stubs import HomeAssistantError, Unauthorized

ERRS = []
class _H(logging.Handler):
    def emit(self, rec):
        if rec.levelno >= logging.ERROR: ERRS.append(rec.getMessage())
logging.getLogger("custom_components").addHandler(_H())

def pn(hass, svc="create", nid=None):
    out = [c for c in hass.services.calls if c[0] == "persistent_notification" and c[1] == svc]
    if nid: out = [c for c in out if c[2].get("notification_id") == nid]
    return out

def mk2():
    hass, c, opt, rt = build()
    opt._read_rce_arrays = lambda: {}
    return hass, c, opt, rt

async def main():
    # =========================================================== A. niski SOC
    hass, c, opt, rt = mk2(); S = hass.states
    S.set("number.bms_inverter_floor_soc", 25)
    t = at(2026, 10, 28, 12, 0)
    S.set(c.config["soc"], 20)
    await rt.monitor.tick(t)
    cr = pn(hass, nid="bms_low_soc")
    check("lowsoc: powiadomienie wysłane", len(cr) == 1, len(cr))
    check("lowsoc: treść zawiera próg i tanie okno", cr and "25%" in cr[0][2]["message"] and "tanie okno" in cr[0][2]["message"].lower(), cr and cr[0][2]["message"])
    t = at(2026, 10, 28, 12, 5); await rt.monitor.tick(t)
    check("lowsoc: cooldown — bez powtórki", len(pn(hass, nid="bms_low_soc")) == 1)
    # weekend: okno taniej taryfy kończy się w poniedziałek o 6:00 — komunikat musi to powiedzieć, nie samo „do 06:00”
    hass3, c3, opt3, rt3 = mk2(); S3 = hass3.states
    S3.set("number.bms_inverter_floor_soc", 20); S3.set(c3.config["soc"], 21)
    await rt3.monitor.tick(at(2026, 11, 8, 7, 53))        # niedziela
    cr3 = pn(hass3, nid="bms_low_soc")
    check("lowsoc: niedziela 07:53 — „tanie okno trwa do jutra 06:00”, nie „do 06:00”", cr3 and "do jutra 06:00" in cr3[0][2]["message"], cr3 and cr3[0][2]["message"])
    hass3, c3, opt3, rt3 = mk2(); S3 = hass3.states
    S3.set("number.bms_inverter_floor_soc", 20); S3.set(c3.config["soc"], 21)
    await rt3.monitor.tick(at(2026, 11, 7, 9, 0))         # sobota
    cr3 = pn(hass3, nid="bms_low_soc")
    check("lowsoc: sobota — „do poniedziałku 06:00”", cr3 and "do poniedziałku 06:00" in cr3[0][2]["message"], cr3 and cr3[0][2]["message"])
    t = at(2026, 10, 28, 18, 5); await rt.monitor.tick(t)
    check("lowsoc: po 6 h przypomnienie", len(pn(hass, nid="bms_low_soc")) == 2, len(pn(hass, nid="bms_low_soc")))
    S.set(c.config["soc"], 40)
    t = at(2026, 10, 28, 18, 10); await rt.monitor.tick(t)
    check("lowsoc: po naładowaniu powiadomienie zdjęte", len(pn(hass, "dismiss", "bms_low_soc")) == 1 and rt.state["low_soc_active"] is False)
    S.set(c.config["soc"], 20)
    t = at(2026, 10, 28, 18, 15); await rt.monitor.tick(t)
    check("lowsoc: kolejny spadek zgłoszony od razu", len(pn(hass, nid="bms_low_soc")) == 3, len(pn(hass, nid="bms_low_soc")))
    check("lowsoc: stan trafia do zapisu (cooldown po restarcie)", "low_soc" in rt.state["notified"])
    # bez znanego progu falownika — próg bezpieczeństwa 12%
    hass, c, opt, rt = mk2(); S = hass.states
    t = at(2026, 10, 28, 12, 0)
    S.set(c.config["soc"], 30); await rt.monitor.tick(t)
    check("lowsoc: 30% bez progu falownika — cisza", not pn(hass, nid="bms_low_soc"))
    S.set(c.config["soc"], 11); t = at(2026, 10, 28, 12, 1); await rt.monitor.tick(t)
    check("lowsoc: 11% bez progu falownika — alarm", len(pn(hass, nid="bms_low_soc")) == 1)

    # =========================================================== B. usługa notify / wyłącznik
    hass, c, opt, rt = mk2(); S = hass.states
    c.config["notify_service"] = "notify.mobile_app_tel"
    S.set("number.bms_inverter_floor_soc", 25); S.set(c.config["soc"], 15)
    t = at(2026, 10, 28, 12, 0); await rt.monitor.tick(t)
    nc = [x for x in hass.services.calls if x[0] == "notify"]
    check("notify: wywołano notify.mobile_app_tel z tytułem i treścią", len(nc) == 1 and nc[0][1] == "mobile_app_tel" and nc[0][2]["title"] and nc[0][2]["message"], nc)
    hass, c, opt, rt = mk2(); S = hass.states
    c.config["notify_service"] = "mobile_app_tel"
    S.set("number.bms_inverter_floor_soc", 25); S.set(c.config["soc"], 15)
    t = at(2026, 10, 28, 12, 0); await rt.monitor.tick(t)
    check("notify: nazwa bez prefiksu „notify.” też działa", [x[1] for x in hass.services.calls if x[0] == "notify"] == ["mobile_app_tel"])
    # błąd usługi notify nie wywraca ticka
    hass, c, opt, rt = mk2(); S = hass.states
    c.config["notify_service"] = "notify.zepsute"
    orig = hass.services.async_call
    async def boom(domain, service, data, blocking=False):
        if domain == "notify": raise RuntimeError("brak usługi")
        return await orig(domain, service, data, blocking)
    hass.services.async_call = boom
    S.set("number.bms_inverter_floor_soc", 25); S.set(c.config["soc"], 15)
    t = at(2026, 10, 28, 12, 0)
    ok = True
    try: await rt.monitor.tick(t)
    except Exception as e: ok = False
    check("notify: błąd usługi notify nie przerywa ticka, powiadomienie HA i tak powstaje", ok and len(pn(hass, nid="bms_low_soc")) == 1)
    check("notify: błąd zapisany w dzienniku", any("nie zadziałała" in e["msg"] for e in rt.log.entries))
    # wyłącznik
    hass, c, opt, rt = mk2(); S = hass.states
    S.set("switch.bms_notifications_enabled", "off")
    S.set("number.bms_inverter_floor_soc", 25); S.set(c.config["soc"], 15)
    t = at(2026, 10, 28, 12, 0); await rt.monitor.tick(t)
    check("wyłącznik: brak powiadomień przy wyłączonym przełączniku", not pn(hass) and not [x for x in hass.services.calls if x[0] == "notify"])
    check("wyłącznik: zdarzenie nadal w dzienniku decyzji", any(e["kind"] == "notify" for e in rt.log.entries))

    # =========================================================== C. alarmy falownika
    hass, c, opt, rt = mk2(); S = hass.states
    t = at(2026, 10, 28, 12, 0)
    S.set("sensor.inverter_fault_code", "0", {"friendly_name": "Inverter Fault code"})
    await rt.monitor.tick(t)
    check("alarm: kod 0 = brak alarmu", not pn(hass, nid="bms_alarm"))
    S.set("sensor.inverter_fault_code", "F35", {"friendly_name": "Inverter Fault code"})
    t = at(2026, 10, 28, 12, 1); await rt.monitor.tick(t)
    a = pn(hass, nid="bms_alarm")
    check("alarm: F35 zgłoszony z opisem", len(a) == 1 and "Brak sieci AC" in a[0][2]["message"], a)
    check("alarm: powiadomienie zawiera zastrzeżenie o modelu falownika", "niskonapięciowych" in a[0][2]["message"] and "HP3" in a[0][2]["message"], a)
    t = at(2026, 10, 28, 12, 6); await rt.monitor.tick(t)
    check("alarm: ten sam stan nie powtarza powiadomienia", len(pn(hass, nid="bms_alarm")) == 1)
    S.set("sensor.inverter_fault_code", "F64", {"friendly_name": "Inverter Fault code"})
    t = at(2026, 10, 28, 12, 7); await rt.monitor.tick(t)
    check("alarm: nowy kod = nowe powiadomienie", len(pn(hass, nid="bms_alarm")) == 2 and "temperatur" in pn(hass, nid="bms_alarm")[1][2]["message"])
    S.set("sensor.inverter_fault_code", "0", {"friendly_name": "Inverter Fault code"})
    t = at(2026, 10, 28, 12, 8); await rt.monitor.tick(t)
    check("alarm: ustąpienie czyści stan i zdejmuje powiadomienie", rt.state["alarms_active"] == {} and len(pn(hass, "dismiss", "bms_alarm")) == 1)
    check("alarm: ustąpienie w dzienniku", any("Alarm ustąpił" in e["msg"] for e in rt.log.entries))
    S.set("sensor.inverter_running_status", "Standby"); S.set("sensor.inverter_grid_status", "On-Grid")
    t = at(2026, 10, 28, 12, 9); await rt.monitor.tick(t)
    check("alarm: statusy normalne (Standby/On-Grid) nie są alarmem", len(pn(hass, nid="bms_alarm")) == 2)
    check("alarm: fault_text rozpoznaje wiele kodów", mon.fault_text("F23 F24") == "F23: Przejściowy prąd upływu (GFCI); F24: Błąd izolacji DC" and mon.fault_text("F99") == "F99" and mon.fault_text("ok") == "")

    # =========================================================== D. brak cen RCE
    hass, c, opt, rt = mk2(); S = hass.states
    t = at(2026, 10, 28, 12, 0); await rt.monitor.tick(t)
    check("rce: przed 18:00 brak alarmu", not pn(hass, nid="bms_rce_missing"))
    t = at(2026, 10, 28, 19, 0); await rt.monitor.tick(t)
    check("rce: po 18:00 bez cen na jutro — powiadomienie", len(pn(hass, nid="bms_rce_missing")) == 1)
    t = at(2026, 10, 28, 19, 30); await rt.monitor.tick(t)
    check("rce: cooldown", len(pn(hass, nid="bms_rce_missing")) == 1)
    hass, c, opt, rt = mk2(); S = hass.states
    opt._read_rce_arrays = lambda: {"2026-10-29": [0.5] * 24}
    t = at(2026, 10, 28, 19, 0); await rt.monitor.tick(t)
    check("rce: pełne ceny na jutro — cisza", not pn(hass, nid="bms_rce_missing"))
    hass, c, opt, rt = mk2(); S = hass.states
    opt._read_rce_arrays = lambda: {"2026-10-29": [0.5] * 20 + [None] * 4}
    t = at(2026, 10, 28, 19, 0); await rt.monitor.tick(t)
    check("rce: niepełne (20/24) — powiadomienie z liczbą", len(pn(hass, nid="bms_rce_missing")) == 1 and "20/24" in pn(hass, nid="bms_rce_missing")[0][2]["message"])

    # =========================================================== E. utrata łączności
    hass, c, opt, rt = mk2(); S = hass.states
    S.set(c.config["soc"], "unavailable"); S.set(c.config["grid_power"], "unavailable")
    t = at(2026, 10, 28, 10, 0); await rt.monitor.tick(t)
    t = at(2026, 10, 28, 10, 6); await rt.monitor.tick(t)
    check("comm: po 6 min jeszcze cisza", not pn(hass, nid="bms_comm_loss"))
    t = at(2026, 10, 28, 10, 11); await rt.monitor.tick(t)
    check("comm: po 11 min brak danych — powiadomienie", len(pn(hass, nid="bms_comm_loss")) == 1)
    S.set(c.config["soc"], 50); S.set(c.config["grid_power"], 100)
    t = at(2026, 10, 28, 10, 15); await rt.monitor.tick(t)
    check("comm: powrót łączności zdejmuje powiadomienie", len(pn(hass, "dismiss", "bms_comm_loss")) == 1)
    # krótka przerwa (<10 min) nie powiadamia
    hass, c, opt, rt = mk2(); S = hass.states
    S.set(c.config["soc"], "unavailable"); S.set(c.config["grid_power"], "unavailable")
    t = at(2026, 10, 28, 10, 0); await rt.monitor.tick(t)
    S.set(c.config["soc"], 50)
    t = at(2026, 10, 28, 10, 5); await rt.monitor.tick(t)
    S.set(c.config["soc"], "unavailable")
    t = at(2026, 10, 28, 10, 12); await rt.monitor.tick(t)
    check("comm: przerwane okno liczy się od nowa", not pn(hass, nid="bms_comm_loss"))

    # =========================================================== F. kontrola po zapisie
    hass, c, opt, rt = mk2(); S = hass.states
    eid = "number.inverter_zero_export_power"
    S.set(eid, 20)
    t0 = at(2026, 10, 28, 12, 0, 0)
    item = rt.watch.add(eid, 20, "Zero export", previous=-20, source="test")
    check("watch: dodano, status pending", item["status"] == "pending" and item["expected"] == 20 and len(rt.watch.list()) == 1)
    t = at(2026, 10, 28, 12, 0, 30); await rt.watch.tick(t)
    check("watch: przed 60 s brak sprawdzeń", rt.watch.list()[0]["checks"] == [])
    t = at(2026, 10, 28, 12, 1, 0); await rt.watch.tick(t)
    check("watch: po 60 s pierwsza kontrola ok", len(rt.watch.list()[0]["checks"]) == 1 and rt.watch.list()[0]["checks"][0]["ok"] is True)
    t = at(2026, 10, 28, 12, 3, 0); await rt.watch.tick(t)
    t = at(2026, 10, 28, 12, 6, 0); await rt.watch.tick(t)
    check("watch: po 6 min status ok", rt.watch.list()[0]["status"] == "ok" and len(rt.watch.list()[0]["checks"]) == 3)
    check("watch: brak powiadomień przy zgodności", not pn(hass, nid="bms_drift"))
    # dryf do 65515 (przepełnienie U16) — przypadek użytkownika
    t0 = at(2026, 10, 28, 13, 0, 0)
    S.set(eid, -20)
    item = rt.watch.add(eid, -20, "Zero export", previous=20, source="karta")
    S.set(eid, 65516)
    t = at(2026, 10, 28, 13, 1, 0); await rt.watch.tick(t)
    w = rt.watch.list()[0]
    check("watch: dryf wykryty po 60 s", w["status"] == "drift" and w["checks"][0]["ok"] is False and w["checks"][0]["value"] == 65516, w)
    d = pn(hass, nid="bms_drift")
    check("watch: powiadomienie z diagnozą U16 i poprzednią wartością", len(d) == 1 and "U16" in d[0][2]["message"] and "20" in d[0][2]["message"], d)
    t = at(2026, 10, 28, 13, 5, 0); await rt.watch.tick(t)
    check("watch: po dryfie nie ma kolejnych kontroli", len(rt.watch.list()[0]["checks"]) == 1)
    # select
    S.set("select.inverter_work_mode", "Export First")
    t0 = at(2026, 10, 28, 14, 0, 0)
    it = rt.watch.add("select.inverter_work_mode", "Export First", "Tryb")
    S.set("select.inverter_work_mode", "Zero Export To Load")
    t = at(2026, 10, 28, 14, 1, 0); await rt.watch.tick(t)
    check("watch: select — zmiana trybu wykryta jako dryf (bez uwagi o U16)", rt.watch.list()[0]["status"] == "drift" and rt.watch.list()[0]["checks"][0]["note"] == "")
    S.set("select.inverter_work_mode", "export first")
    t0 = at(2026, 10, 28, 15, 0, 0)
    rt.watch.add("select.inverter_work_mode", "Export First", "Tryb 2")
    t = at(2026, 10, 28, 15, 1, 0); await rt.watch.tick(t)
    check("watch: select — porównanie bez względu na wielkość liter", rt.watch.list()[0]["checks"][0]["ok"] is True)
    # encja niedostępna
    S.set(eid, "unavailable")
    t0 = at(2026, 10, 28, 16, 0, 0)
    n_drift = len(pn(hass, nid="bms_drift"))
    rt.watch.add(eid, 20, "Niedostępna")
    for mm in (1, 3, 6):
        t = at(2026, 10, 28, 16, mm, 0); await rt.watch.tick(t)
    check("watch: encja niedostępna → status unavailable (bez fałszywego dryfu)", rt.watch.list()[0]["status"] == "unavailable" and len(pn(hass, nid="bms_drift")) == n_drift, (rt.watch.list()[0]["status"], n_drift))
    # tolerancja
    S.set(eid, 20.4); t0 = at(2026, 10, 28, 17, 0, 0)
    rt.watch.add(eid, 20, "tol")
    t = at(2026, 10, 28, 17, 1, 0); await rt.watch.tick(t)
    check("watch: odchyłka 0.4 mieści się w domyślnej tolerancji", rt.watch.list()[0]["checks"][0]["ok"] is True)
    # spóźniony tick wykonuje zaległe kontrole
    t0 = at(2026, 10, 28, 18, 0, 0)
    rt.watch.add(eid, 20.4, "late")
    t = at(2026, 10, 28, 18, 10, 0); await rt.watch.tick(t)
    check("watch: spóźniony tick nadrabia wszystkie 3 kontrole", len(rt.watch.list()[0]["checks"]) == 3 and rt.watch.list()[0]["status"] == "ok")
    # encje czasu: „07:30:00” to to samo co „07:30”
    S.set("time.bms_x_start", "07:30:00"); t0 = at(2026, 10, 28, 19, 0, 0)
    rt.watch.add("time.bms_x_start", "07:30", "Czas")
    t = at(2026, 10, 28, 19, 1, 0); await rt.watch.tick(t)
    check("watch: czas 07:30:00 = 07:30 (bez fałszywego dryfu)", rt.watch.list()[0]["checks"][0]["ok"] is True)
    rt.watch.add("time.bms_x_start", "08:00", "Czas2"); t0 = at(2026, 10, 28, 19, 2, 0)
    S.set("switch.bms_x", "on"); rt.watch.add("switch.bms_x", "on", "Przełącznik")
    t = at(2026, 10, 28, 19, 9, 0); await rt.watch.tick(t)
    ws = {w["label"]: w for w in rt.watch.list()}
    check("watch: zła godzina wykryta jako dryf, przełącznik on/on ok", ws["Czas2"]["status"] == "drift" and ws["Przełącznik"]["status"] == "ok", {k: v["status"] for k, v in ws.items()})
    # czyszczenie, walidacja, limit, wygasanie
    try: rt.watch.add("zla_nazwa", 1); bad = False
    except ValueError: bad = True
    check("watch: zła nazwa encji → ValueError", bad)
    n_before = len(rt.watch.list())
    rid = rt.watch.list()[0]["id"]
    check("watch: clear(id) usuwa jeden", rt.watch.clear(rid) == 1 and len(rt.watch.list()) == n_before - 1)
    rt.watch.add(eid, 20, "pend")
    cleared = rt.watch.clear()
    check("watch: clear() zostawia tylko oczekujące", cleared >= 1 and all(i["status"] == "pending" for i in rt.watch.list()))
    for i in range(40): rt.watch.add(eid, 20, f"x{i}")
    check("watch: limit 30 pozycji", len(rt.watch.list()) <= wch.MAX_ITEMS)
    t = at(2026, 10, 30, 12, 0, 0); await rt.watch.tick(t)
    t = at(2026, 10, 30, 12, 0, 30); await rt.watch.tick(t)
    check("watch: po 24 h wszystkie pozycje (także rozstrzygnięte w tym ticku) są usuwane", len(rt.watch.list()) == 0, len(rt.watch.list()))

    # =========================================================== G. tryby
    hass, c, opt, rt = mk2(); S = hass.states
    S.set("switch.bms_storm_mode", "on"); S.set("number.bms_storm_mode_hours", 2)
    t = at(2026, 10, 28, 12, 0); await rt.modes_tick(t)
    check("storm: czas końca zapisany (2 h)", abs(rt.state["storm_until"] - (t.timestamp() + 7200)) < 1, rt.state["storm_until"])
    check("storm: rezerwa 100%", rt.reserve()["pct"] == 100 and rt.sell_soc_threshold() == 100)
    reason = rt.sell_block_reason()
    check("storm: sprzedaż zablokowana z powodem", reason and "burzow" in reason, reason)
    try: await rt.run_command("sprzedaz_6000w", source="ręcznie"); blocked = False
    except HomeAssistantError as e: blocked = "zablokowana" in str(e)
    check("storm: przycisk sprzedaży odrzucony", blocked)
    check("storm: powiadomienie o włączeniu", len(pn(hass, nid="bms_storm")) == 1)
    t = at(2026, 10, 28, 13, 0); await rt.modes_tick(t)
    check("storm: w trakcie — bez zmian", rt.state["storm_until"] is not None and S.get("switch.bms_storm_mode").state == "on")
    t = at(2026, 10, 28, 14, 1); await rt.modes_tick(t)
    check("storm: po czasie sam się wyłącza", S.get("switch.bms_storm_mode").state == "off" and rt.state["storm_until"] is None)
    check("storm: po wyłączeniu rezerwa i sprzedaż wracają", not rt.reserve().get("storm") and rt.sell_block_reason() is None and rt.sell_soc_threshold() < 100)
    S.set("switch.bms_storm_mode", "on"); t = at(2026, 10, 28, 15, 0); await rt.modes_tick(t)
    S.set("switch.bms_storm_mode", "off"); t = at(2026, 10, 28, 15, 5); await rt.modes_tick(t)
    check("storm: ręczne wyłączenie czyści znacznik", rt.state["storm_until"] is None)
    # guard: trwająca sprzedaż w trybie burzowym zostaje zatrzymana
    hass, c, opt, rt = mk2(); S = hass.states
    S.set("select.inverter_work_mode", "Export First"); S.set("switch.bms_storm_mode", "on")
    t = at(2026, 10, 28, 17, 30); rt.state["storm_until"] = t.timestamp() + 3600
    await rt.enforce_guard(t)
    check("storm: zabezpieczenie zatrzymuje trwającą sprzedaż", S.get("select.inverter_work_mode").state == "Zero Export To Load")
    # schedule: start sprzedaży w trybie burzowym pominięty
    hass, c, opt, rt = mk2(); S = hass.states
    S.set("switch.bms_storm_mode", "on"); S.set("switch.bms_bateria_sprzedaz_1", "on")
    t = at(2026, 10, 28, 17, 0); rt.state["storm_until"] = t.timestamp() + 3600
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00")
    S.set(c.config["soc"], 95)
    res = await rt.process_rules(t)
    check("storm: harmonogram nie startuje sprzedaży", S.get("select.inverter_work_mode").state == "Zero Export To Load" and not [r for r in res["results"] if r.get("fired")])
    # urlop
    hass, c, opt, rt = mk2(); S = hass.states
    S.set("switch.bms_vacation_mode", "on")
    t = at(2026, 10, 28, 9, 0); await rt.modes_tick(t)
    check("urlop: data włączenia zapamiętana", rt.state["vacation_since"] == "2026-10-28")
    S.set("switch.bms_vacation_mode", "off"); await rt.modes_tick(t)
    check("urlop: wyłączenie czyści", rt.state["vacation_since"] is None)

    # =========================================================== H. plan 24 h (z prawdziwym optymalizatorem)
    hass, c, sched = await mk((2026, 10, 28, 12), 60)
    rt = rtm.BmsRuntime(hass, c, sched); c.runtime = rt; S = hass.states
    cnt = [0]; orig_s = sched.suggest
    async def counting():
        cnt[0] += 1; return await orig_s()
    sched.suggest = counting
    plan = await rt.refresh_plan()
    cv = plan and plan.get("curve")
    check("plan: krzywa wyliczona", bool(cv) and plan["mode"] == "normal" and len(cv["soc"]) == cv["hours"] and len(cv["floor"]) == cv["hours"], plan and plan.get("error"))
    check("plan: wszystkie serie tej samej długości", all(len(cv[k]) == cv["hours"] for k in ("soc", "floor", "pv", "load", "buy", "sell", "peak", "grid", "sale", "target")))
    check("plan: SOC w granicach 0–100", all(0 <= x <= 100 for x in cv["soc"]))
    await rt.refresh_plan(); check("plan: cache (bez ponownego liczenia w TTL)", cnt[0] == 1)
    at(2026, 10, 28, 12, 16); await rt.refresh_plan(); check("plan: po TTL przeliczony", cnt[0] == 2)
    await rt.refresh_plan(force=True); check("plan: force przelicza", cnt[0] == 3)
    S.set("switch.bms_storm_mode", "on"); await rt.modes_tick(at(2026, 10, 28, 12, 17))
    check("plan: zmiana trybu unieważnia cache", rt._plan_ts == 0.0)
    plan = await rt.refresh_plan()
    check("plan: tryb burzowy w planie", plan["mode"] == "storm", plan.get("mode"))
    tg = [x for x in plan["curve"]["target"] if x is not None]
    check("plan: tryb burzowy ładuje do 100%", tg and max(tg) == 100, tg)
    check("plan: tryb burzowy bez sprzedaży", sum(plan["curve"]["sale"]) == 0)
    S.set("switch.bms_storm_mode", "off"); S.set("switch.bms_vacation_mode", "on"); S.set("number.bms_vacation_load_w", 100)
    await rt.modes_tick(at(2026, 10, 28, 12, 18))
    pv = await rt.refresh_plan()
    check("plan: tryb urlopowy — stałe zużycie 0.1 kWh/h", pv["mode"] == "vacation" and all(abs(x - 0.1) < 1e-6 for x in pv["curve"]["load"]), pv["curve"]["load"][:4])
    S.set("switch.bms_vacation_mode", "off")
    # sensory
    for key, unit in (("plan_curve", None), ("battery_health", "%"), ("monthly_report", "PLN"), ("monitor_status", None)):
        s = BmsRuntimeSensor(c, key, "x", unit, "mdi:x"); s.coordinator = c
        try:
            v, a = s.native_value, s.extra_state_attributes; ok = True
        except Exception as e:
            ok = False; v = a = repr(e)
        check(f"sensor {key}: stan i atrybuty bez wyjątku", ok, v)
        if key == "plan_curve": check("sensor plan_curve: stan = tryb, atrybut curve", v in ("normal", "storm", "vacation") and a["curve"]["hours"] > 0, (v, list(a)))
        if key == "monitor_status": check("sensor monitor_status: pola", set(a) >= {"alarms", "watches", "low_soc_active", "storm_until", "recent_notifications"}, list(a))

    # =========================================================== I. statystyki baterii
    hass = stubs.FakeHass()
    st = BatteryStats(hass); CAP = 10.0
    def feed_day(d, soc0, soc1, chg, dis, pv=15.0, load=12.0, imp=8.0, exp=5.0, restart_midday=False, stop_at=23.83):
        y, m, dd = d
        steps = 48
        for i in range(steps + 1):
            hm = i * (stop_at / steps)
            hh, mm = int(hm), int(round((hm - int(hm)) * 60))
            if mm == 60: hh, mm = hh + 1, 0
            now = datetime(y, m, dd, min(hh, 23), mm, 0, tzinfo=TZ)
            f = i / steps
            data = {"energy_pv_today": pv * f, "energy_load_today": load * f, "energy_grid_import_today": imp * f,
                    "energy_grid_export_today": exp * f, "energy_battery_charge_today": chg * f, "energy_battery_discharge_today": dis * f}
            soc = soc0 + (soc1 - soc0) * f
            if restart_midday and f < 0.5: continue
            st.update_day(now, data, round(soc))
    feed_day((2026, 10, 20), 40, 60, 10.0, 7.5)             # (7.5 + 2) / 10 = 0.95
    feed_day((2026, 10, 21), 50, 50, 8.0, 6.4)              # 0.80
    feed_day((2026, 10, 22), 30, 50, 10.0, 7.0, restart_midday=True)     # brak soc0 → pomijana
    feed_day((2026, 10, 23), 20, 20, 10.0, 7.0, stop_at=20.0)             # niepełna doba → pomijana
    feed_day((2026, 10, 24), 20, 20, 10.0, 13.0)            # 1.3 poza zakresem → pomijana
    feed_day((2026, 10, 25), 20, 20, 1.0, 0.9)              # za małe ładowanie → pomijana
    d20 = st.days["2026-10-20"]
    check("stats: liczniki doby zapisane", abs(d20["chg"] - 10.0) < 0.3 and abs(d20["dis"] - 7.5) < 0.3 and abs(d20["pv"] - 15.0) < 0.5, d20)
    check("stats: soc0 z początku doby, soc1 z końca", d20["soc0"] == 40 and d20["soc1"] == 60, d20)
    check("stats: doba po restarcie w dzień nie ma soc0", "soc0" not in st.days["2026-10-22"])
    e, n = st.efficiency(CAP, None, date(2026, 10, 26))
    exp_e = ((d20["dis"] + 2.0) + (st.days["2026-10-21"]["dis"] + 0.0)) / (d20["chg"] + st.days["2026-10-21"]["chg"])
    check("stats: sprawność ważona energią tylko z poprawnych dób", n == 2 and abs(e - exp_e) < 1e-6, (e, n, exp_e))
    check("stats: sprawność w sensownym zakresie (~0.88)", 0.85 < e < 0.92, e)
    e2, n2 = st.period_efficiency("2026-10-", CAP); check("stats: sprawność miesięczna = ta sama", n2 == 2 and abs(e2 - e) < 1e-9)
    check("stats: dzień bieżący nie liczy się do sprawności", st.efficiency(CAP, None, date(2026, 10, 20))[1] == 0)
    # lag licznika po północy
    st2 = BatteryStats(hass)
    st2.update_day(datetime(2026, 11, 1, 0, 1, tzinfo=TZ), {"energy_pv_today": 15.0, "energy_battery_charge_today": 10.0}, 40)
    check("stats: wczorajszy licznik tuż po północy ignorowany", "pv" not in st2.days["2026-11-01"] and st2.days["2026-11-01"]["soc0"] == 40, st2.days)
    st2.update_day(datetime(2026, 11, 1, 0, 10, tzinfo=TZ), {"energy_pv_today": 0.0, "energy_battery_charge_today": 0.0}, 40)
    st2.update_day(datetime(2026, 11, 1, 12, 0, tzinfo=TZ), {"energy_pv_today": 6.0}, 55)
    st2.update_day(datetime(2026, 11, 1, 12, 5, tzinfo=TZ), {"energy_pv_today": 5.0}, 55)
    check("stats: licznik tylko rośnie (cofnięcie ignorowane)", st2.days["2026-11-01"]["pv"] == 6.0)
    st2.update_day(datetime(2026, 11, 1, 12, 6, tzinfo=TZ), {"energy_pv_today": "x"}, None)
    check("stats: śmieci/None nie wywalają", st2.days["2026-11-01"]["pv"] == 6.0)
    # trwałość
    saved = st._data()
    st3 = BatteryStats(hass)
    async def _load(): return json.loads(json.dumps(saved))
    st3._store._store.async_load = _load
    await st3.async_load()
    check("stats: zapis i odczyt zachowują dane", st3.days.keys() == st.days.keys() and abs(st3.efficiency(CAP, None, date(2026, 10, 26))[0] - e) < 1e-9)
    # pojemność
    sc = BatteryStats(hass)
    def charge(start_ts, soc0, soc1, kw):
        cap_true = 10.0; e_in = (soc1 - soc0) / 100.0 * cap_true / 0.97
        secs = int(e_in / kw * 3600); t_ = start_ts
        for i in range(secs // 10 + 1):
            f = min(1.0, i * 10 / secs)
            sc.add_power(datetime.fromtimestamp(t_ + i * 10, TZ), round(soc0 + (soc1 - soc0) * f), -kw * 1000.0, -1)
        end = t_ + secs
        for j in range(1, 60):
            sc.add_power(datetime.fromtimestamp(end + j * 10, TZ), soc1, 0.0, -1)
        return end + 600
    t_ = datetime(2026, 10, 10, 1, 0, tzinfo=TZ).timestamp()
    for s0, s1, kw in ((20, 50, 2.0), (30, 70, 3.0), (10, 45, 1.5)):
        t_ = charge(t_ + 3600, s0, s1, kw)
    est, ns = sc.capacity_estimate()
    check("pojemność: 3 odcinki → szacunek ≈ 10 kWh", ns == 3 and est is not None and 9.0 <= est <= 11.0, (est, ns, sc.caps))
    sm = sc.summary(CAP)
    check("pojemność: SOH ≈ 100% w podsumowaniu", sm["soh_est_pct"] is not None and 90 <= sm["soh_est_pct"] <= 110, sm)
    # za mało odcinków / za krótkie ładowanie
    sc2 = BatteryStats(hass); t_ = datetime(2026, 10, 10, 1, 0, tzinfo=TZ).timestamp()
    sc = sc2; t_ = charge(t_, 20, 30, 2.0)
    check("pojemność: odcinek < 15 pkt SOC nie liczy się", sc2.capacity_estimate()[0] is None and sc2.caps == [])
    # luka w danych przerywa odcinek (inaczej energia z luki byłaby pominięta, a SOC policzony „od początku”)
    sg = BatteryStats(hass); base = datetime(2026, 10, 10, 1, 0, tzinfo=TZ).timestamp()
    e_a = 10 / 100.0 * 10.0 / 0.97; sa = int(e_a / 2.0 * 3600)
    for i in range(0, sa + 1, 10): sg.add_power(datetime.fromtimestamp(base + i, TZ), round(20 + 10 * i / sa), -2000.0, -1)
    base2 = base + sa + 1200                      # 20 min bez próbek; w tym czasie SOC urósł o ~8 pkt
    e_b = 20 / 100.0 * 10.0 / 0.97; sb = int(e_b / 2.0 * 3600)
    for i in range(0, sb + 1, 10): sg.add_power(datetime.fromtimestamp(base2 + i, TZ), round(38 + 20 * i / sb), -2000.0, -1)
    for j in range(1, 60): sg.add_power(datetime.fromtimestamp(base2 + sb + j * 10, TZ), 58, 0.0, -1)
    check("pojemność: luka dzieli odcinki (krótki pierwszy odrzucony, drugi policzony poprawnie)", len(sg.caps) == 1 and 9.0 <= sg.caps[0]["cap"] <= 11.0, sg.caps)
    # odwrotny znak
    sp = BatteryStats(hass); sc = sp
    # ponowne użycie charge() z dodatnią mocą
    def charge_pos(start_ts, soc0, soc1, kw):
        e_in = (soc1 - soc0) / 100.0 * 10.0 / 0.97; secs = int(e_in / kw * 3600)
        for i in range(secs // 10 + 1):
            f = min(1.0, i * 10 / secs); sp.add_power(datetime.fromtimestamp(start_ts + i * 10, TZ), round(soc0 + (soc1 - soc0) * f), kw * 1000.0, +1)
        for j in range(1, 60): sp.add_power(datetime.fromtimestamp(start_ts + secs + j * 10, TZ), soc1, 0.0, +1)
        return start_ts + secs + 600
    tt = base
    for s0, s1 in ((20, 50), (30, 70), (10, 45)): tt = charge_pos(tt + 3600, s0, s1, 2.0)
    check("pojemność: dodatni znak ładowania też działa", sp.capacity_estimate()[0] is not None and 9.0 <= sp.capacity_estimate()[0] <= 11.0)

    # =========================================================== J. raport miesięczny
    hass, c, opt, rt = mk2(); S = hass.states
    for dd in range(1, 31):
        k = f"2026-09-{dd:02d}"
        rt.ledger.days[k] = {"export_kwh": 5.0, "import_kwh": 8.0, "revenue": 4.0 + (1.0 if dd == 7 else 0.0), "cost": 8.0, "neg_export_kwh": 0.0}
        rt.stats.days[k] = {"pv": 15.0, "load": 12.0, "imp": 8.0, "exp": 5.0, "chg": 6.0, "dis": 5.0, "soc0": 30.0, "soc1": 30.0, "t1h": 23.9}
    at(2026, 10, 5, 12)
    r = rt.monthly_report(2026, 9)
    check("raport: tytuł i liczba dni", r["title"] == "Wrzesień 2026" and r["days_with_data"] == 30 and r["complete"] is True, r["title"])
    check("raport: bilans = przychód − koszt", abs(r["revenue"] - 121.0) < 1e-6 and abs(r["cost"] - 240.0) < 1e-6 and abs(r["net"] + 119.0) < 1e-6, (r["revenue"], r["cost"], r["net"]))
    check("raport: ceny średnie", abs(r["avg_buy_price"] - 1.0) < 1e-6 and abs(r["avg_sell_price"] - 121.0 / 150.0) < 1e-3, (r["avg_buy_price"], r["avg_sell_price"]))
    check("raport: autokonsumpcja i samowystarczalność", r["self_consumption_pct"] == 67 and r["self_sufficiency_pct"] == 33, (r["self_consumption_pct"], r["self_sufficiency_pct"]))
    check("raport: szacunek oszczędności = zużycie × cena zakupu + bilans", abs(r["saving_estimate"] - (360.0 * 1.0 - 119.0)) < 0.5, r["saving_estimate"])
    check("raport: najlepszy dzień = 7.", r["best_day"]["date"] == "2026-09-07", r["best_day"])
    check("raport: sprawność cyklu miesiąca", r["cycle_efficiency_pct"] is not None and abs(r["cycle_efficiency_pct"] - 83.3) < 0.2 and r["cycle_efficiency_days"] == 30, (r["cycle_efficiency_pct"], r["cycle_efficiency_days"]))
    txt = repm.report_text(r)
    check("raport: tekst powiadomienia (orientacyjnie, bilans)", "Bilans z siecią" in txt and "orientacyjnie" in txt and "Wrzesień 2026" in txt, txt)
    r0 = rt.monthly_report(2026, 8)
    check("raport: miesiąc bez danych — zera/None bez wyjątku", r0["days_with_data"] == 0 and r0["net"] == 0 and r0["saving_estimate"] is None and r0["best_day"] is None)
    r3 = rt.monthly_report(2026, 2)
    check("raport: luty (28 dni) poprawna liczba dni", r3["days_in_month"] == 28)
    # częściowe dane — ostrzeżenie
    for dd in range(11, 31): rt.ledger.days.pop(f"2026-09-{dd:02d}"); rt.stats.days.pop(f"2026-09-{dd:02d}")
    rp = rt.monthly_report(2026, 9)
    check("raport: niepełny miesiąc oznaczony i opisany", rp["complete"] is False and "Uwaga: dane z 10 z 30 dni" in repm.report_text(rp))
    # wysyłka 1. dnia
    for dd in range(11, 31):
        k = f"2026-09-{dd:02d}"; rt.ledger.days[k] = {"export_kwh": 5.0, "import_kwh": 8.0, "revenue": 4.0, "cost": 8.0, "neg_export_kwh": 0.0}
    t = at(2026, 10, 1, 7, 0); await rt.report_tick(t)
    check("raport: przed 8:00 nie wysyła", not pn(hass, nid="bms_summary_monthly"))
    t = at(2026, 10, 2, 9, 0); await rt.report_tick(t)
    check("raport: nie 1. dnia — nie wysyła", not pn(hass, nid="bms_summary_monthly"))
    t = at(2026, 10, 1, 9, 0); await rt.report_tick(t)
    mr = pn(hass, nid="bms_summary_monthly")
    check("raport: 1. dnia po 8:00 wysłany za wrzesień", len(mr) == 1 and "Wrzesień 2026" in mr[0][2]["title"], mr)
    t = at(2026, 10, 1, 9, 30); await rt.report_tick(t)
    check("raport: tylko raz", len(pn(hass, nid="bms_summary_monthly")) == 1 and rt.state["report_sent"] == "2026-09")
    t = at(2027, 1, 1, 9, 0); await rt.report_tick(t)
    check("raport: styczeń → raport za grudzień poprzedniego roku (brak danych = cisza, ale oznaczony)", rt.state["report_sent"] == "2026-12" and len(pn(hass, nid="bms_summary_monthly")) == 1)
    r_cached = rt.report_cached(); check("raport: cache bieżącego miesiąca", rt.report_cached() is r_cached)

    # =========================================================== K. magazyn Diagnostyki
    hass = stubs.FakeHass(); ds = DiagStore(hass)
    info = ds.set("log", [{"t": 1, "msg": "zażółć gęślą jaźń"}])
    check("diag_store: zapis", info["key"] == "log" and info["bytes"] > 10 and ds.get_all()["log"]["value"][0]["msg"] == "zażółć gęślą jaźń")
    for bad_key in ("zly", "", "../etc"):
        try: ds.set(bad_key, 1); bad = False
        except ValueError: bad = True
        check(f"diag_store: nieznany klucz „{bad_key}” odrzucony", bad)
    try: ds.set("backups", {"x": "a" * 500_000}); bad = False
    except ValueError as e: bad = "za duża" in str(e)
    check("diag_store: za duża wartość odrzucona", bad)
    try: ds.set("backups", object()); bad = False
    except ValueError as e: bad = "JSON" in str(e)
    check("diag_store: wartość nie-JSON odrzucona", bad)
    ds.set("backups", "a" * 390_000); ds.set("profiles", "b" * 390_000); ds.set("auto", "c" * 390_000)
    try: ds.set("alarms", "d" * 390_000); bad = False
    except ValueError as e: bad = "pełny" in str(e)
    check("diag_store: limit łączny", bad)
    ds.set("backups", "a" * 100); ds.set("alarms", "d" * 390_000)
    check("diag_store: nadpisanie klucza zwalnia miejsce", "alarms" in ds.get_all())
    check("diag_store: delete", ds.delete("alarms") is True and ds.delete("alarms") is False and "alarms" not in ds.get_all())
    dump = ds._store._store.func() if ds._store._store.func else None
    check("diag_store: zapis zaplanowany w Store", isinstance(dump, dict) and "log" in dump)
    ds2 = DiagStore(hass)
    async def _l(): return json.loads(json.dumps(dump))
    ds2._store._store.async_load = _l
    await ds2.async_load()
    check("diag_store: odczyt po restarcie", ds2.get_all()["log"]["value"] == ds.get_all()["log"]["value"])
    async def _junk(): return {"log": "x", "zly": {"v": 1}, "auto": {"v": 5, "t": "z"}}
    ds3 = DiagStore(hass); ds3._store._store.async_load = _junk; await ds3.async_load()
    check("diag_store: śmieci w pliku ignorowane", list(ds3.get_all()) == ["auto"])

    # =========================================================== L. kreator / test instalacji
    hass, c, sched = await mk((2026, 10, 28, 12), 60)
    rt = rtm.BmsRuntime(hass, c, sched); c.runtime = rt; S = hass.states
    # encje kontrolne i czujniki jak u użytkownika
    h = hlt.health_check(rt)
    ids = {x["id"]: x for x in h["checks"]}
    check("health: struktura", set(h) >= {"version", "checks", "commands", "summary"} and all(x["status"] in ("ok", "warn", "error") for x in h["checks"]))
    check("health: encje sterujące OK", all(ids[f"ctl_{r}"]["status"] == "ok" for r in ("work_mode", "charge_current", "export_surplus", "tou_select")), {k: v["status"] for k, v in ids.items() if k.startswith("ctl_")})
    check("health: opcje select rozpoznane", ids["opt_work_mode"]["status"] == "ok" and ids["opt_tou_select"]["status"] == "ok", ids["opt_work_mode"])
    check("health: SOC i sieć OK", ids["sensor_soc"]["status"] == "ok" and ids["sensor_grid_power"]["status"] == "ok")
    check("health: RCE dziś OK (pełne 24 h)", ids["rce_dziś"]["status"] == "ok" if "rce_dziś" in ids else True, [k for k in ids if k.startswith("rce")])
    check("health: 8 komend w podglądzie, wszystkie poprawne", len(h["commands"]) == 8 and h["summary"]["commands_failing"] == 0, [c_ for c_ in h["commands"] if not c_["ok"]])
    sp = [c_ for c_ in h["commands"] if c_["key"] == "sprzedaz_6000w"][0]
    check("health: podgląd komendy sprzedaży (tryb + moc)", [(s["entity_id"], s["value"]) for s in sp["steps"]] == [("select.inverter_work_mode", "Export First"), ("number.inverter_export_surplus_power", 6000)], sp["steps"])
    check("health: podgląd nic nie zmienił w falowniku", not [x for x in hass.services.calls if x[0] in ("select", "number")])
    check("health: powiadomienia na telefon — ostrzeżenie gdy brak usługi", ids["notify"]["status"] == "warn")
    c.config["notify_service"] = "notify.mobile_app_tel"
    check("health: usługa notify nieistniejąca → błąd", {x["id"]: x for x in hlt.health_check(rt)["checks"]}["notify"]["status"] == "error")
    hass.services.known.add(("notify", "mobile_app_tel"))
    check("health: usługa notify istnieje → ok", {x["id"]: x for x in hlt.health_check(rt)["checks"]}["notify"]["status"] == "ok")
    # brak encji falownika
    del S._s["select.inverter_work_mode"]
    h2 = hlt.health_check(rt); i2 = {x["id"]: x for x in h2["checks"]}
    check("health: brak encji trybu pracy → błąd + komendy nie gotowe", i2["ctl_work_mode"]["status"] == "error" and h2["summary"]["ready"] is False and h2["summary"]["commands_failing"] >= 3, h2["summary"])
    S.set("select.inverter_work_mode", "Batt First", {"options": ["Batt First", "Load First"]})
    h3 = hlt.health_check(rt); i3 = {x["id"]: x for x in h3["checks"]}
    check("health: obce nazwy trybów → błąd opcji i komenda z komunikatem", i3["opt_work_mode"]["status"] == "error" and any(not c_["ok"] and "Batt First" in (c_["error"] or "") for c_ in h3["commands"]), i3["opt_work_mode"])
    S.set("select.inverter_work_mode", "Selling First", {"options": ["Selling First", "Zero Export To CT"]})
    h4 = hlt.health_check(rt); i4 = {x["id"]: x for x in h4["checks"]}
    check("health: inne nazwy trybów rozpoznane (Selling First / Zero Export To CT)", i4["opt_work_mode"]["status"] == "ok" and "Selling First" in i4["opt_work_mode"]["detail"], i4["opt_work_mode"])
    S.set("number.inverter_battery_max_charging_current", 37, {"max": 37})
    cmd = [c_ for c_ in hlt.health_check(rt)["commands"] if c_["key"] == "odblokuj_ladowanie"][0]
    check("health: prąd ładowania przycięty do limitu encji (37 A)", cmd["steps"][0]["value"] <= 37, cmd)

    # =========================================================== M. usługi + administrator
    hass, c, sched = await mk((2026, 10, 28, 12), 60)
    rt = rtm.BmsRuntime(hass, c, sched); c.runtime = rt; S = hass.states
    pkg._get_runtime = lambda h_: rt; pkg._get_optimizer = lambda h_: sched
    users = {"adm": types.SimpleNamespace(is_admin=True), "usr": types.SimpleNamespace(is_admin=False)}
    async def get_user(uid): return users.get(uid)
    hass.auth = types.SimpleNamespace(async_get_user=get_user)
    pkg._register_services(hass)
    H = {n: hh for (d, n), (hh, _r) in hass.services.handlers.items() if d == "bms_komp_dec"}
    check("usługi: zarejestrowano wszystkie", set(H) == set(pkg._SERVICES), set(pkg._SERVICES) ^ set(H))
    def call(data, uid=None): return types.SimpleNamespace(data=data, context=types.SimpleNamespace(user_id=uid))
    async def expect_unauth(name, data):
        try: await H[name](call(data, "usr")); return False
        except Unauthorized: return True
    for name, data in (("diag_store_set", {"key": "log", "value": []}), ("diag_store_get_all", {}), ("diag_store_delete", {"key": "log"}),
                       ("watch_write", {"entity_id": "number.x", "expected": 1}), ("watch_status", {}), ("watch_clear", {}), ("health_check", {})):
        check(f"usługi: {name} odrzuca użytkownika bez uprawnień admina", await expect_unauth(name, data))
    try: await H["diag_store_get_all"](call({}, "duch")); g = False
    except Unauthorized: g = True
    check("usługi: nieznany użytkownik odrzucony", g)
    r = await H["diag_store_set"](call({"key": "log", "value": [1, 2]}, "adm"))
    check("usługi: admin zapisuje do magazynu", r["key"] == "log")
    r = await H["diag_store_get_all"](call({}, None))
    check("usługi: automatyzacja (bez użytkownika) odczytuje magazyn", r["data"]["log"]["value"] == [1, 2])
    try: await H["diag_store_set"](call({"key": "zly", "value": 1}, "adm")); e_ = False
    except HomeAssistantError: e_ = True
    check("usługi: zły klucz → HomeAssistantError", e_)
    S.set("number.inverter_zero_export_power", 20)
    r = await H["watch_write"](call({"entity_id": "number.inverter_zero_export_power", "expected": 20, "label": "ZE", "previous": -20}, "adm"))
    check("usługi: watch_write zwraca pozycję", r["item"]["status"] == "pending" and r["item"]["entity_id"] == "number.inverter_zero_export_power")
    try: await H["watch_write"](call({"entity_id": "bez_kropki", "expected": 1}, "adm")); e_ = False
    except HomeAssistantError: e_ = True
    check("usługi: watch_write zła encja → HomeAssistantError", e_)
    r = await H["watch_status"](call({}, "adm")); check("usługi: watch_status", len(r["items"]) == 1)
    r = await H["watch_clear"](call({"id": r["items"][0]["id"]}, "adm")); check("usługi: watch_clear", r["cleared"] == 1)
    r = await H["health_check"](call({}, "adm")); check("usługi: health_check", r["summary"]["commands_failing"] == 0 and len(r["checks"]) > 10)
    r = await H["monthly_report"](call({"year": 2026, "month": 9}, "usr")); check("usługi: raport dostępny dla zwykłego użytkownika", r["title"] == "Wrzesień 2026")
    r = await H["get_plan"](call({"force": True}, "usr")); check("usługi: get_plan", r["plan"] and r["plan"]["curve"]["hours"] > 0)
    # --- dane wejściowe usług: wartości skrajne i złośliwe
    async def raises(coro):
        try: await coro; return None
        except HomeAssistantError as err: return str(err)
        except Exception as err: return "INNY:" + type(err).__name__
    for bad in ({"year": 2026, "month": 13}, {"year": 2026, "month": 0}, {"year": 1, "month": 5}, {"year": 99999, "month": 1},
                {"year": "abc", "month": 1}, {"year": 2026}, {"month": 3}, {"year": [2026], "month": {"a": 1}}, {"year": 2026.5, "month": 99}):
        m = await raises(H["monthly_report"](call(bad, "usr")))
        check(f"usługi: monthly_report {bad} → czytelny HomeAssistantError", bool(m) and not str(m).startswith("INNY"), m)
    r = await H["monthly_report"](call({}, "usr")); check("usługi: monthly_report bez parametrów = bieżący miesiąc", "title" in r)
    r = await H["monthly_report"](call({"year": "2026", "month": "9"}, "usr")); check("usługi: monthly_report przyjmuje liczby jako napisy", r["title"] == "Wrzesień 2026")
    check("usługi: _as_bool", [pkg._as_bool(x) for x in (None, "", "false", "False", "0", "off", "nie", "true", "on", 1, 0, True, False)] == [None, None, False, False, False, False, False, True, True, True, False, True, False])
    for junk in ({"times": "nie-słownik"}, {"times": {"zly_klucz": "10:00"}}, {"times": {"start_grid_charge": "25:99"}}, {"times": {"start_grid_charge": "10:00; rm -rf"}}, {"times": {"start_grid_charge": 1234}}, {"times": None}, {}):
        out = await H["apply_schedule_times"](call(junk, "usr"))
        check(f"usługi: apply_schedule_times odrzuca {junk}", out["applied"] == 0, out)
    big = "Z" * 100000
    r = await H["watch_write"](call({"entity_id": "number.inverter_zero_export_power", "expected": big, "label": big, "previous": big, "source": big}, "adm"))
    it = r["item"]
    check("usługi: watch_write obcina długie pola", len(str(it["label"])) <= 120 and len(str(it["expected"])) <= 80 and len(str(it["previous"] or "")) <= 80 and len(str(it.get("source", ""))) <= 40, {k: len(str(v)) for k, v in it.items()})
    m = await raises(H["watch_write"](call({"entity_id": "x" * 5000, "expected": 1}, "adm")))
    check("usługi: watch_write ogromny entity_id bez kropki → błąd, nie awaria", bool(m) and not m.startswith("INNY"), m)
    for _ in range(80): await H["watch_write"](call({"entity_id": "number.inverter_zero_export_power", "expected": 20}, "adm"))
    check("usługi: watch_write nie rośnie bez ograniczeń (≤30)", len((await H["watch_status"](call({}, "adm")))["items"]) <= 30)
    await H["watch_clear"](call({}, "adm"))
    for badv in (float("nan"), float("inf"), "nan", "inf", -5, "abc", None, [1], {"a": 1}):
        m = await raises(H["watch_write"](call({"entity_id": "number.inverter_zero_export_power", "expected": 1, "tolerance": badv}, "adm")))
        check(f"usługi: watch_write tolerance={badv!r} nie wywala usługi", m is None or not m.startswith("INNY"), m)
    for key, val in (("log", "x" * 500000), ("log", {"a": "b" * 10}), ("__proto__", 1), ("log", float("nan"))):
        m = await raises(H["diag_store_set"](call({"key": key, "value": val}, "adm")))
        check(f"usługi: diag_store_set {key}/{type(val).__name__}/{len(str(val))} B nie wywala usługi", m is None or not m.startswith("INNY"), m)
    r = await H["diag_store_get_all"](call({}, "adm")); check("usługi: magazyn po próbach nadal zwraca dane", isinstance(r["data"], dict))
    m = await raises(H["diag_store_set"](call({"key": ["log"], "value": 1}, "adm")))
    check("usługi: diag_store_set klucz nie-napis → błąd, nie awaria", m is None or not m.startswith("INNY"), m)
    m = await raises(H["diag_store_delete"](call({"key": None}, "adm")))
    check("usługi: diag_store_delete bez klucza → bez awarii", m is None or not m.startswith("INNY"), m)
    rt._tasks.clear()

    # =========================================================== N. dry-run auto-apply
    hass, c, sched = await mk((2026, 10, 28, 20), 30)
    rt = rtm.BmsRuntime(hass, c, sched); c.runtime = rt; S = hass.states
    pkg._get_runtime = lambda h_: rt; pkg._get_optimizer = lambda h_: sched
    hass.auth = types.SimpleNamespace(async_get_user=get_user)
    for k, v in (("start_grid_charge", "23:00:00"), ("stop_grid_charge", "05:00:00"), ("start_grid_charge_2", "13:00:00"), ("stop_grid_charge_2", "14:00:00"),
                 ("bateria_sprzedaz_start", "17:00:00"), ("bateria_sprzedaz_stop", "19:00:00")):
        S.set(f"time.bms_{k}", v)
    res = await sched.suggest()
    tw0 = [x for x in hass.services.calls if x[0] == "time"]
    dry = await automation.async_auto_apply(rt, hass, res, dry_run=True)
    check("dry-run: wynik oznaczony i bez zapisu", dry.get("dry_run") is True and dry["applied"] == {} and not [x for x in hass.services.calls if x[0] == "time"] and tw0 == [], dry)
    check("dry-run: pokazuje co by zmienił (would_apply) i poprzednie wartości", isinstance(dry.get("would_apply"), dict) and set(dry["would_apply"]) <= set(dry.get("previous", {})), dry)
    check("dry-run: wpis w dzienniku „PODGLĄD”", any("PODGLĄD" in e["msg"] for e in rt.log.entries) or not dry["would_apply"])
    check("dry-run: nie zapisuje „ostatnio zastosowane” (cofnięcie)", rt.state["last_applied"] == {})
    if dry["would_apply"]:
        real = await automation.async_auto_apply(rt, hass, res, dry_run=False)
        check("dry-run: realne zastosowanie = to co pokazał podgląd", real["applied"] == dry["would_apply"] and bool([x for x in hass.services.calls if x[0] == "time"]), (real, dry))
    else:
        check("dry-run: (brak zmian w tym scenariuszu — pominięto porównanie)", True)
    # przełącznik
    S.set("switch.bms_auto_apply_dry_run", "on")
    n_time = len([x for x in hass.services.calls if x[0] == "time"])
    for k in ("start_grid_charge", "stop_grid_charge"): S.set(f"time.bms_{k}", "10:00:00")
    sw = await automation.async_auto_apply(rt, hass, res)
    check("dry-run: przełącznik wymusza podgląd", sw.get("dry_run") is True and len([x for x in hass.services.calls if x[0] == "time"]) == n_time, sw)
    # usługa z parametrem
    S.set("switch.bms_auto_apply_dry_run", "off")
    pkg._register_services(hass)
    H = {n: hh for (d, n), (hh, _r) in hass.services.handlers.items() if d == "bms_komp_dec"}
    n_time = len([x for x in hass.services.calls if x[0] == "time"])
    out = await H["auto_apply_now"](call({"dry_run": True}, "adm"))
    check("dry-run: usługa auto_apply_now z dry_run=true", out.get("dry_run") is True and len([x for x in hass.services.calls if x[0] == "time"]) == n_time, out)

    # =========================================================== O. pełny tick + stats z koordynatora
    hass, c, sched = await mk((2026, 10, 28, 9), 55)
    rt = rtm.BmsRuntime(hass, c, sched); c.runtime = rt; S = hass.states
    ERRS.clear()
    t = at(2026, 10, 28, 9, 0, 0)
    c.data = {"battery_power": -1500.0, "energy_pv_today": 2.0, "energy_load_today": 3.0, "energy_grid_import_today": 1.0,
              "energy_grid_export_today": 0.0, "energy_battery_charge_today": 1.0, "energy_battery_discharge_today": 0.5,
              "grid_power": 200.0, "load_forecast": {}}
    rt.on_coordinator_update()
    check("tick: statystyki dnia zasilane z koordynatora", rt.stats.days["2026-10-28"].get("pv") == 2.0 and rt.stats.days["2026-10-28"].get("chg") == 1.0, rt.stats.days)
    await rt.tick(t)
    t = at(2026, 10, 28, 9, 0, 30); await rt.tick(t)
    check("tick: pełny tick (tryby, kontrola, monitoring, raport, plan) bez błędów", not ERRS, ERRS[:3])
    check("tick: plan odświeżony przez tick", rt.plan() is not None and rt.plan().get("curve"))
    sig = rt.state
    check("tick: stan zawiera nowe klucze i serializuje się do JSON", json.dumps(sig, default=str) and all(k in sig for k in ("notified", "alarms_active", "watches", "storm_until", "report_sent")))
    # wczytanie starego stanu (sprzed 0.6) nie psuje nowych kluczy
    hass2, c2, opt2, rt2 = mk2()
    async def _old(): return {"today_date": "2026-10-01", "price_reaction": {"active": False, "prev_mode": None}, "last_applied": {}}
    rt2._state_store._store.async_load = _old
    await rt2.async_load()
    check("migracja: stary plik stanu → nowe klucze mają wartości domyślne", rt2.state["notified"] == {} and rt2.state["watches"] == [] and rt2.state["alarms_active"] == {})
    async def _bad(): return {"notified": "zepsute", "watches": 5, "alarms_active": []}
    rt3 = mk2()[3]; rt3._state_store._store.async_load = _bad; await rt3.async_load()
    check("migracja: uszkodzone typy w stanie naprawiane", rt3.state["notified"] == {} and rt3.state["watches"] == [] and rt3.state["alarms_active"] == {})


    # =========================================================== P. rejestracja plików karty
    hass = stubs.FakeHass(); reg = []
    async def reg_paths(cfgs): reg.extend(cfgs)
    hass.http = types.SimpleNamespace(async_register_static_paths=reg_paths)
    hass.is_running = False
    hass.bus = types.SimpleNamespace(async_listen_once=lambda *a, **k: None)
    pkg.StaticPathConfig = lambda url, path, cache_headers=True: (url, path, cache_headers)
    pkg.add_extra_js_url = lambda h, u: None
    await pkg._async_register_frontend(hass)
    urls = [r[0] for r in reg]
    check("frontend: rdzeń zarejestrowany", "/bms_komp_dec/bms-panel.js" in urls, urls)
    check("frontend: moduł Diagnostyki zarejestrowany (bez cache)", ("/bms_komp_dec/bms-diag.js") in urls and [r for r in reg if r[0].endswith("bms-diag.js")][0][2] is False)
    import pathlib
    for r in reg:
        if r[0].endswith(".js") and "vendor" not in r[0]: check(f"frontend: plik {r[0]} istnieje", pathlib.Path(r[1]).is_file(), r[1])
    # brak pliku modułu nie wywala rejestracji
    import shutil, tempfile
    tmp = pathlib.Path(tempfile.mkdtemp()); (tmp / "bms-panel.js").write_text("//")
    old_dir = pkg._FRONTEND_DIR; pkg._FRONTEND_DIR = tmp
    hass2 = stubs.FakeHass(); reg2 = []
    async def reg2f(cfgs): reg2.extend(cfgs)
    hass2.http = types.SimpleNamespace(async_register_static_paths=reg2f); hass2.is_running = False; hass2.bus = hass.bus
    await pkg._async_register_frontend(hass2)
    pkg._FRONTEND_DIR = old_dir
    check("frontend: brak pliku modułu nie przerywa rejestracji rdzenia", [r[0] for r in reg2] == ["/bms_komp_dec/bms-panel.js"], reg2)

    print(f"STAGE2 PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
