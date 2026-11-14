"""Tabela planu, „Dlaczego?”, historia SOC, nadpisania planu, koniec ładowania po celu, porównanie taryf, symulacja roczna, test sterowania."""
import asyncio, sys
from datetime import date, datetime, timedelta, timezone
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import planview, overrides, analysis, ctltest, scheduler
from homeassistant.util import dt as dt_util


def logs(rt):
    ents = list(rt.log.entries.values()) if isinstance(rt.log.entries, dict) else list(rt.log.entries)
    return [e["msg"] for e in ents]


def curve():
    t0 = dt_util.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    n = 6
    return {"start": t0.isoformat(), "hours": n, "soc_now": 50.0,
            "soc": [60, 80, 80, 80, 60, 40],                  # 10 kWh: +1, +2, 0, 0, −2, −2 kWh
            "pv": [0, 0, 0, 0, 0, 0], "load": [0.5] * 6,
            "buy": [0.7, 0.7, 1.1, 1.1, 1.1, 1.1], "sell": [0.3, 0.3, 0.4, 0.4, 0.9, 0.9],
            "peak": [0, 0, 1, 1, 1, 1], "grid": [1, 1, 0, 0, 0, 0], "sale": [0, 0, 0, 0, 1, 1], "floor": [20] * 6}


async def main():
    # ---------------------------------------------------------------- tabela planu (13)
    tb = planview.plan_table(curve(), 10.0)
    rows = tb["rows"]
    check("tabela: 6 wierszy", len(rows) == 6, len(rows))
    check("tabela: akcje ładuj/ładuj/bez zmian/sprzedaj", [r["action"] for r in rows[:2]] == ["grid", "grid"] and rows[4]["action"] == "sell", [r["action"] for r in rows])
    check("tabela: godzina 3 — bateria stoi, dom z sieci (PV 0)", rows[3]["action"] == "idle" and abs(rows[3]["import_kwh"] - 0.5) < 1e-6, rows[3])
    # godzina 0: ładowanie +1 kWh, dom 0,5 → import 1,5 kWh × 0,7 = 1,05 zł
    check("tabela: koszt ładowania z sieci = import × cena", abs(rows[0]["cost"] - 1.05) < 0.01, rows[0]["cost"])
    # godzina 4: bateria oddaje 2 kWh, dom 0,5 → eksport 1,5 kWh × 0,9 = 1,35 zł przychodu
    check("tabela: sprzedaż = ujemny koszt", abs(rows[4]["cost"] + 1.35) < 0.01 and rows[4]["export_kwh"] == 1.5, rows[4])
    check("tabela: sumy", tb["totals"]["grid_kwh"] == 3.0 and tb["totals"]["sell_kwh"] == 4.0, tb["totals"])
    check("tabela: brak krzywej → pusta", planview.plan_table(None, 10)["rows"] == [] and planview.plan_table({}, 10)["totals"] is None)

    # ---------------------------------------------------------------- historia SOC (20)
    today = date(2026, 11, 14)
    b = [None] * 24
    mk_b = lambda imp, exp, bch, bdis, pv, soc: [0.5, pv, imp, exp, bch, bdis, 0, 0, 0, 0, soc]
    b[2] = mk_b(1.5, 0, 1.2, 0, 0, 40.0)      # ładowanie z sieci
    b[18] = mk_b(0, 1.5, 0, 1.6, 0, 70.0)     # sprzedaż z baterii
    b[12] = mk_b(0, 2.0, 0, 0.5, 3.0, 90.0)   # eksport z PV — to nie sprzedaż z baterii
    h = planview.soc_history({today.isoformat(): b}, {today.isoformat(): [50.0] * 24}, 3, today)
    check("historia: 3 doby, dwie puste", len(h) == 3 and h[0]["empty"] and h[1]["empty"] and not h[2]["empty"])
    d = h[2]
    check("historia: ładowanie z sieci wykryte w godz. 2", d["grid"][2] == 1 and sum(d["grid"]) == 1, d["grid"])
    check("historia: sprzedaż wykryta w godz. 18, eksport PV nie", d["sale"][18] == 1 and d["sale"][12] == 0, d["sale"])
    check("historia: SOC i plan", d["soc"][18] == 70.0 and d["soc"][0] is None and d["plan"] == [50.0] * 24)

    # ---------------------------------------------------------------- nadpisania: moduł
    now = 1_000_000.0
    items = overrides.add([], "no_sell", now, now + 3600, now)
    check("nadpisanie: dodane i aktywne", len(items) == 1 and overrides.active(items, now + 10, "no_sell"))
    check("nadpisanie: po końcu wygasa", overrides.prune(items, now + 4000) == [])
    items = overrides.add(items, "charge", now, now + 7200, now, 80)
    items = overrides.add(items, "no_grid", now + 600, now + 1200, now)      # sprzeczne z „charge” → zastępuje je
    check("nadpisanie: nakładające się sprzeczne zastępuje stare", [o["kind"] for o in items] == ["no_sell", "no_grid"], items)
    for bad, msg in ((("x", now, now + 10), "nieznany"), (("charge", now, now - 5), "po początku"),
                     (("charge", now, now + 49 * 3600), "najwyżej"), (("charge", now - 7200, now - 3600), "minęło"),
                     (("charge", now + 50 * 3600, now + 51 * 3600), "do przodu")):
        try:
            overrides.add([], bad[0], bad[1], bad[2], now)
            check("nadpisanie: odrzucone " + msg, False)
        except overrides.OverrideError as err:
            check("nadpisanie: odrzucone " + msg, msg in str(err), str(err))
    try:
        overrides.add([], "charge", now, now + 3600, now, 3)
        check("nadpisanie: cel SOC poza zakresem", False)
    except overrides.OverrideError:
        check("nadpisanie: cel SOC poza zakresem", True)
    check("nadpisanie: usunięcie po id i wszystkich", len(overrides.remove(items, items[0]["id"])) == 1 and overrides.remove(items, None) == [])

    # ---------------------------------------------------------------- nadpisania w runtime
    t0 = at(2026, 11, 14, 17, 0)
    hass, c, opt, rt = build(); S = hass.states
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0}
    check("warunek: bez nadpisania sprzedaż dozwolona", rt.sell_block_reason() is None, rt.sell_block_reason())
    rt.override_add("no_sell", t0.timestamp(), t0.timestamp() + 7200)
    r = rt.sell_block_reason()
    check("nie sprzedawaj: powód blokady z godziną końca", r and "ręczne nadpisanie" in r and "19:00" in r, r)
    try:
        await rt.run_command("sprzedaz_6000w", source="ręcznie")
        check("nie sprzedawaj: ręczna sprzedaż zablokowana", False)
    except Exception:
        check("nie sprzedawaj: ręczna sprzedaż zablokowana", not rt.is_selling())
    # trwająca sprzedaż jest przerywana przez zabezpieczenie
    rt.override_remove(None)
    await rt.run_command("sprzedaz_6000w", source="ręcznie")
    check("warunek: sprzedaż trwa", rt.is_selling())
    rt.override_add("no_sell", t0.timestamp(), t0.timestamp() + 7200)
    await rt.enforce_guard(t0)
    check("nie sprzedawaj: trwająca sprzedaż zatrzymana", not rt.is_selling(), logs(rt)[-2:])
    at(2026, 11, 14, 19, 5)
    check("nadpisanie wygasa: blokada znika", rt.sell_block_reason() is None and rt.override_list() == [])

    # nie ładuj z sieci: start z harmonogramu pominięty, trwające ładowanie przerwane
    t0 = at(2026, 11, 14, 5, 0)
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_start_grid_charge", "05:00:00"); S.set("time.bms_stop_grid_charge", "06:00:00")
    S.set("switch.bms_ladowanie_z_sieci_1", "on")
    rt.override_add("no_grid", t0.timestamp(), t0.timestamp() + 3 * 3600)
    await rt.process_rules(t0)
    check("nie ładuj z sieci: start z harmonogramu pominięty", not rt.grid_charging_on(), logs(rt)[-2:])
    await rt.process_rules(t0 + timedelta(minutes=10))
    check("nie ładuj z sieci: nadrabianie okna też nie startuje", not rt.grid_charging_on())
    rt.override_remove(None)
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    rt.override_add("no_grid", t0.timestamp(), t0.timestamp() + 3600)
    await rt.override_tick(t0)
    check("nie ładuj z sieci: trwające ładowanie przerwane", not rt.grid_charging_on(), logs(rt)[-2:])

    # ładuj z sieci: start, cel SOC, koniec
    hass, c, opt, rt = build(); S = hass.states
    S.set(c.config["soc"], 40)
    rt.override_add("charge", t0.timestamp(), t0.timestamp() + 2 * 3600, 60)
    await rt.override_tick(t0)
    check("ładuj z sieci: ładowanie włączone", rt.grid_charging_on() and rt.state.get("ovr_charge_on"), logs(rt)[-2:])
    S.set(c.config["soc"], 55)
    await rt.override_tick(t0 + timedelta(minutes=30))
    check("ładuj z sieci: poniżej celu trwa", rt.grid_charging_on())
    S.set(c.config["soc"], 60)
    rt._guard_last.clear()
    await rt.override_tick(t0 + timedelta(minutes=60))
    check("ładuj z sieci: cel 60% osiągnięty → stop", not rt.grid_charging_on() and not rt.state.get("ovr_charge_on"), logs(rt)[-2:])
    await rt.override_tick(t0 + timedelta(minutes=61))
    check("ładuj z sieci: po osiągnięciu celu nie startuje ponownie", not rt.grid_charging_on())
    # wygaśnięcie okna kończy ładowanie
    hass, c, opt, rt = build(); S = hass.states
    S.set(c.config["soc"], 40)
    rt.override_add("charge", t0.timestamp(), t0.timestamp() + 3600)
    await rt.override_tick(t0)
    check("ładuj z sieci (bez celu): start", rt.grid_charging_on())
    at(2026, 11, 14, 6, 5)
    await rt.override_tick(at(2026, 11, 14, 6, 5))
    check("ładuj z sieci: wygaśnięcie okna kończy ładowanie", not rt.grid_charging_on() and not rt.state.get("ovr_charge_on"), logs(rt)[-2:])
    # w trakcie sprzedaży ładowanie się nie włącza
    t0 = at(2026, 11, 14, 17, 0)
    hass, c, opt, rt = build(); S = hass.states
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0}
    await rt.run_command("sprzedaz_6000w", source="ręcznie")
    rt.override_add("charge", t0.timestamp(), t0.timestamp() + 3600)
    await rt.override_tick(t0)
    check("ładuj z sieci: nie włącza się w trakcie sprzedaży", not rt.grid_charging_on())

    # propozycje planu: nadpisanie je pomija
    t0 = at(2026, 11, 14, 17, 0)
    hass, c, opt, rt = build()
    async def fake_suggest():
        return {"generated_at": t0.isoformat(), "mode": "normal", "curve": None, "assumptions": {},
                "proposals": {"bateria_sprzedaz_start": {"proposed": "18:00", "current": "17:00", "reason": "x", "label": "a"},
                              "bateria_sprzedaz_stop": {"proposed": "20:00", "current": "19:00", "reason": "x", "label": "b"},
                              "start_grid_charge": {"proposed": "01:00", "current": "02:00", "reason": "x", "label": "c"},
                              "stop_grid_charge": {"proposed": "05:00", "current": "05:00", "reason": "x", "label": "d"}}}
    opt.suggest = fake_suggest
    rt.override_add("no_sell", t0.timestamp(), t0.timestamp() + 3600)
    plan = await rt.refresh_plan(force=True)
    P = plan["proposals"]
    check("plan: nadpisanie „nie sprzedawaj” pomija propozycje sprzedaży, ładowanie zostaje",
          P["bateria_sprzedaz_start"]["skip"] and P["bateria_sprzedaz_stop"]["skip"] and not P["start_grid_charge"].get("skip"), P)
    rt.override_add("no_grid", t0.timestamp(), t0.timestamp() + 3600)
    plan = await rt.refresh_plan(force=True)
    P = plan["proposals"]
    check("plan: nadpisanie „nie ładuj z sieci” pomija propozycje ładowania (start i stop)",
          P["start_grid_charge"]["skip"] and P["stop_grid_charge"]["skip"], P)

    # ---------------------------------------------------------------- koniec ładowania po osiągnięciu celu (6)
    t0 = at(2026, 11, 14, 2, 0)
    def window(hass, rt, soc, target, age_min=10, charging=True, sw="on"):
        S = hass.states
        S.set("time.bms_start_grid_charge", "01:00:00"); S.set("time.bms_stop_grid_charge", "06:00:00")
        S.set("switch.bms_ladowanie_z_sieci_1", "on"); S.set(c.config["soc"], soc)
        S.set("switch.bms_grid_stop_at_target", sw)
        rt.state["grid_target_plan"] = {"target": target, "at": (t0 - timedelta(minutes=age_min)).isoformat()}
    hass, c, opt, rt = build()
    window(hass, rt, 59, 60)
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    await rt.enforce_guard(t0)
    check("cel: poniżej celu — ładowanie trwa", rt.grid_charging_on())
    hass.states.set(c.config["soc"], 60)
    await rt.enforce_guard(t0)
    check("cel: SOC ≥ cel — ładowanie zakończone przed STOP", not rt.grid_charging_on(), logs(rt)[-2:])
    check("cel: wpis w dzienniku z wartościami", any("Cel ładowania z sieci osiągnięty" in m and "60%" in m for m in logs(rt)))
    await rt.process_rules(t0 + timedelta(minutes=5))
    check("cel: nadrabianie okna nie wznawia ładowania", not rt.grid_charging_on(), logs(rt)[-2:])
    for label, kw in (("wyłączony przełącznik", dict(sw="off")), ("plan sprzed 7 h", dict(age_min=7 * 60)), ("cel 100% (bateria i tak się zapełni)", dict(target=100))):
        hass, c, opt, rt = build()
        args = dict(soc=70, target=60); args.update(kw)
        window(hass, rt, **args)
        await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
        await rt.enforce_guard(t0)
        check("cel: bez zatrzymania — " + label, rt.grid_charging_on())
    hass, c, opt, rt = build()
    window(hass, rt, 70, 60); hass.states.set("switch.bms_force_charge_battery", "on")
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    await rt.enforce_guard(t0)
    check("cel: „Wymuś ładowanie” nie jest przerywane", rt.grid_charging_on())
    hass, c, opt, rt = build()
    window(hass, rt, 70, 60)
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    at(2026, 11, 14, 8, 0)
    await rt.enforce_guard(at(2026, 11, 14, 8, 0))
    check("cel: poza oknem ładowania (ręczne) — bez ingerencji", rt.grid_charging_on())

    # ---------------------------------------------------------------- „Dlaczego?” (17)
    t0 = at(2026, 11, 14, 12, 0)
    hass, c, opt, rt = build(); S = hass.states
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0, "pv_power": 2500}
    S.set(c.config["soc"], 60)
    w = rt.why_now(t0)
    check("dlaczego: ładowanie z PV", w["kind"] == "pv" and "PV" in w["text"], w)
    S.set(c.config["soc"], 100); c.data["pv_power"] = 3000
    check("dlaczego: bateria pełna", rt.why_now(t0)["kind"] == "full")
    S.set(c.config["soc"], 60); c.data["pv_power"] = 0
    check("dlaczego: bateria zasila dom", rt.why_now(t0)["kind"] == "home")
    S.set("time.bms_bateria_sprzedaz_start", "18:00:00"); S.set("time.bms_bateria_sprzedaz_stop", "20:00:00"); S.set("switch.bms_bateria_sprzedaz_1", "on")
    check("dlaczego: wspomina najbliższe okno", any("18:00–20:00" in x for x in rt.why_now(t0)["details"]), rt.why_now(t0))
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    rt.state["grid_target_plan"] = {"target": 80, "at": t0.isoformat()}
    w = rt.why_now(t0)
    check("dlaczego: ładowanie z sieci z celem", w["kind"] == "grid" and "80%" in w["text"], w)
    await rt.run_command("wylacz_ladowanie_siec", source="ręcznie")
    await rt.run_command("sprzedaz_6000w", source="ręcznie")
    check("dlaczego: sprzedaż", rt.why_now(t0)["kind"] == "sell")
    await rt.run_command("nadwyzka_9700w", source="ręcznie")
    S.set("switch.bms_storm_mode", "on")
    check("dlaczego: tryb burzowy ma pierwszeństwo", rt.why_now(t0)["kind"] == "storm")
    S.set("switch.bms_storm_mode", "off")
    rt.override_add("no_sell", t0.timestamp(), t0.timestamp() + 3600)
    w = rt.why_now(t0)
    check("dlaczego: nadpisanie i powód blokady na liście", any("nadpisanie" in x for x in w["details"]) and any("Sprzedaż zablokowana" in x for x in w["details"]), w)
    rt.override_remove(None)
    rt.state["grid_batt"] = {"kwh": 2.4}
    w = rt.why_now(t0)
    check("dlaczego: energia z sieci w baterii", any("2.4" in x and "z sieci" in x for x in w["details"]) or any("Sprzedaż zablokowana" in x for x in w["details"]), w)

    # ---------------------------------------------------------------- porównanie taryf (11)
    today = date(2026, 11, 14)
    bk = {}
    for i in range(1, 11):
        d = (today - timedelta(days=i)).isoformat()
        day = [None] * 24
        for h in range(24):
            imp = 1.0 if h in (3, 4, 19, 20) else 0.0
            buy = 0.7 if h in (3, 4) else 1.1
            day[h] = [0.5, 0, imp, 0, 0, 0, buy * 3600, 3600, 0.4 * 3600, 3600, 50.0]    # BUY_S = cena × czas
        bk[d] = day
    r = analysis.tariff_compare(bk, {"g11": 0.9, "zone": {"peak": 1.2, "off": 0.6, "windows": "6-13,15-22"}}, today)
    act = {x["key"]: x for x in r["rows"]}
    check("taryfy: 10 dób, import 40 kWh", r["days"] == 10 and r["import_kwh"] == 40.0, (r["days"], r["import_kwh"]))
    check("taryfy: rzeczywisty koszt = 10 × (2×0,7 + 2×1,1)", abs(act["actual"]["cost"] - 36.0) < 0.01, act["actual"])
    check("taryfy: G11 = 40 × 0,9", abs(act["g11"]["cost"] - 36.0) < 0.01, act["g11"])
    # godziny 3,4 poza szczytem (0,6) i 19,20 szczyt (1,2) → 10 × (2×0,6 + 2×1,2) = 36,0 — w niedzielę/sobotę wszystko poza szczytem
    check("taryfy: strefowa liczona z oknami (weekendy poza szczytem)", 20 <= act["zone"]["cost"] <= 36.5, act["zone"])
    check("taryfy: przeliczenie na miesiąc (×3)", abs(act["actual"]["per_month"] - 108.0) < 0.05, act["actual"])
    r2 = analysis.tariff_compare(bk, {"dyn_markup": 0.5}, today)
    dyn = [x for x in r2["rows"] if x["key"] == "dyn"]
    check("taryfy: dynamiczna = (RCE 0,4 + narzut 0,5) × import", dyn and abs(dyn[0]["cost"] - 36.0) < 0.01, r2["rows"])
    r3 = analysis.tariff_compare({}, {"g11": 0.9}, today)
    check("taryfy: brak danych — bez błędu", r3["days"] == 0 and r3["rows"][0]["cost"] == 0.0)
    check("taryfy: błędne ustawienia odrzucone", analysis.clean_cfg({"g11": "abc", "zone": {"peak": 1, "off": 1, "windows": "xx"}, "invest_pv": -5}) == {})

    # ---------------------------------------------------------------- symulacja roczna i zwrot (12)
    days = {}
    for i in range(30):
        days[(today - timedelta(days=i + 1)).isoformat()] = {"complete": True, "nopv": 10.0, "nobat": 6.0, "simple": 4.0, "actual": 3.0, "load_kwh": 12.0, "pv_kwh": 5.0}
    sim = analysis.year_sim(days, {"invest_pv": 20000, "invest_batt": 15000}, 0.8)
    s = {x["key"]: x for x in sim["scenarios"]}
    check("symulacja: cztery scenariusze, rocznie = okres × 365/30", len(s) == 4 and abs(s["ems"]["year"] - 3.0 * 30 * 365 / 30) < 0.1, sim["scenarios"])
    sv = sim["savings_year"]
    check("symulacja: oszczędności PV / bateria / EMS", abs(sv["pv"] - 4 * 365) < 0.5 and abs(sv["battery"] - 2 * 365) < 0.5 and abs(sv["ems"] - 365) < 0.5 and abs(sv["total"] - 7 * 365) < 0.5, sv)
    check("symulacja: zwrot PV = 20000 / 1460 ≈ 13,7 lat", sim["payback"]["pv_years"] == 13.7, sim.get("payback"))
    check("symulacja: zwrot baterii = 15000 / (730+365) ≈ 13,7", sim["payback"]["battery_years"] == 13.7, sim.get("payback"))
    check("symulacja: mało danych oznaczone jako ekstrapolacja", sim["extrapolated"] is True and "sezonowość" in sim["note"])
    check("symulacja: poniżej 3 dób — brak wyniku", analysis.year_sim(dict(list(days.items())[:2]), {}, 0.8) is None)
    del days[(today - timedelta(days=1)).isoformat()]["nopv"]
    sim = analysis.year_sim(days, {}, 0.8)
    check("symulacja: brak pola nopv w starych dobach → szacunek z zużycia × średnia cena", sim and abs([x for x in sim["scenarios"] if x["key"] == "nopv"][0]["period"] - (29 * 10 + 12 * 0.8)) < 0.01, sim and sim["scenarios"][0])
    check("symulacja: bez nakładów — bez zwrotu", "payback" not in sim)
    check("symulacja: stare doby bez ceny → brak wyniku", analysis.year_sim({k: dict(v, nopv=None) for k, v in days.items()}, {}, None) is None)

    # analiza przez runtime: zapis ustawień
    hass, c, opt, rt = build()
    rt.analysis_set({"g11": 0.85, "invest_pv": 25000})
    check("analiza: ustawienia zapisane w stanie", rt.state["analysis_cfg"] == {"g11": 0.85, "invest_pv": 25000.0}, rt.state["analysis_cfg"])
    rt.analysis_set({"g11": None})
    check("analiza: pusta wartość usuwa ustawienie", "g11" not in rt.state["analysis_cfg"])
    pl = rt.analysis_payload()
    check("analiza: payload bez danych nie wywala", pl["sim"] is None and pl["tariff"]["days"] == 0)

    # ---------------------------------------------------------------- przełączniki trybu prostego: sprzedaż / ładowanie z sieci
    t0 = at(2026, 11, 14, 5, 0)
    hass, c, opt, rt = build(); S = hass.states
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0}
    check("przełączniki: domyślnie nic nie jest zablokowane", rt.blocked_kinds() == {})
    S.set("switch.bms_sell_enabled", "off")
    check("sprzedaż wyłączona: powód blokady", "wyłączona w ustawieniach" in (rt.sell_block_reason() or ""), rt.sell_block_reason())
    check("sprzedaż wyłączona: plan ją pomija", "sell" in rt.blocked_kinds())
    S.set("switch.bms_sell_enabled", "on"); S.set("switch.bms_grid_charge_enabled", "off")
    S.set("time.bms_start_grid_charge", "05:00:00"); S.set("time.bms_stop_grid_charge", "06:00:00"); S.set("switch.bms_ladowanie_z_sieci_1", "on")
    await rt.process_rules(t0)
    check("ładowanie z sieci wyłączone: start z harmonogramu pominięty", not rt.grid_charging_on() and "grid" in rt.blocked_kinds(), logs(rt)[-2:])
    await rt.run_command("wlacz_ladowanie_siec", source="ręcznie")
    check("ładowanie z sieci wyłączone: ręczne „Wymuś” nadal działa (świadoma decyzja)", rt.grid_charging_on())
    # planer: zablokowany rodzaj nie trafia do propozycji ani krzywej
    hass, c, sched = await mk((2026, 11, 14, 12), 60, load=8.0)
    res = await sched.suggest()
    check("warunek: bez blokady plan ładuje z sieci", not res["proposals"]["start_grid_charge"]["skip"] and sum(res["curve"]["grid"]) > 0)
    sched.block_fn = lambda: {"grid": "ładowanie z sieci wyłączone w ustawieniach"}
    res = await sched.suggest()
    check("planer: blokada ładowania — propozycje pominięte, krzywa bez ładowania",
          res["proposals"]["start_grid_charge"]["skip"] and "wyłączone w ustawieniach" in res["proposals"]["start_grid_charge"]["reason"] and sum(res["curve"]["grid"]) == 0, res["proposals"]["start_grid_charge"])
    ctx = {"sold": {40, 41}, "sale_windows": [{"a": 1}], "grid_hours": {1}, "grid_targets": {1: 80}, "grid_kwh": 3.0, "midday_hours": {13}}
    pr = {}
    sched.block_fn = lambda: {"sell": "x"}
    sched._apply_blocks(pr, ctx)
    check("planer: blokada sprzedaży czyści godziny i okna sprzedaży", ctx["sold"] == set() and ctx["sale_windows"] == [] and pr["bateria_sprzedaz_start"]["skip"] and ctx["grid_hours"] == {1})
    sched.block_fn = lambda: (_ for _ in ()).throw(RuntimeError("x"))
    sched._apply_blocks({}, dict(ctx))
    check("planer: błąd w block_fn nie psuje planu", True)

    # ---------------------------------------------------------------- test sterowania falownikiem (3)
    async def nosleep(s): pass
    hass, c, opt, rt = build(); S = hass.states
    eid = "number.inverter_battery_max_charging_current"
    S.set(eid, 100, {"min": 0, "max": 185, "step": 1})
    res = await ctltest.run(rt, nosleep)
    check("test sterowania: działa, wartość przywrócona", res["ok"] and float(S.get(eid).state) == 100 and res["to"] == 101, res)
    check("test sterowania: wynik zapisany w stanie i w dzienniku", rt.state["control_test"]["ok"] and any("Test sterowania" in m for m in logs(rt)))
    S.set(eid, 185, {"min": 0, "max": 185, "step": 1})
    res = await ctltest.run(rt, nosleep)
    check("test sterowania: na górnym końcu zakresu idzie w dół", res["ok"] and res["to"] == 184 and float(S.get(eid).state) == 185, res)
    hass.services.ignore.add(eid)                    # falownik „nie reaguje”
    ctltest.WAIT_S = 0.0
    res = await ctltest.run(rt, nosleep)
    check("test sterowania: brak reakcji falownika wykryty", not res["ok"] and "nie potwierdził" in res["detail"], res)
    hass.services.ignore.discard(eid); ctltest.WAIT_S = 30.0
    S.set(eid, 100, {"max": 185})
    res = await ctltest.run(rt, nosleep)
    check("test sterowania: brak zakresu encji — bezpieczna odmowa", not res["ok"] and "zakresu" in res["detail"] and float(S.get(eid).state) == 100, res)

    print(f"FEATURES PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
