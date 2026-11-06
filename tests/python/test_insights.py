"""0.8.5: oszczędności (3 warianty), trafność prognoz, korekta PV, koszt zużycia baterii, zapis stanu po restarcie."""
import asyncio, sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import insights as I, helpers as HP

PROGS = [("00:00", 25, "Allow Grid"), ("05:00", 25, "Allow Grid"), ("06:00", 25, "Disabled"), ("13:00", 25, "Disabled"), ("15:00", 25, "Disabled"), ("22:00", 25, "Allow Grid")]


def B(load=0.0, pv=0.0, imp=0.0, exp=0.0, buy=1.0, sell=0.3, soc=None):
    b = I._blank_bucket()
    b[I.LOAD], b[I.PV], b[I.IMP], b[I.EXP] = load, pv, imp, exp
    b[I.BUY_S], b[I.BUY_T], b[I.SELL_S], b[I.SELL_T] = buy * 3600, 3600, sell * 3600, 3600
    b[I.SOC] = soc
    return b


async def main():
    # ---------- 1. koszty dnia: 3 warianty
    # noc: dom 1 kWh/h, brak PV; dzień 10–14: PV 3 kWh/h, dom 1 kWh/h
    hrs = [B(load=1.0, imp=1.0) for _ in range(24)]
    for h in range(10, 14):
        hrs[h] = B(load=1.0, pv=3.0, exp=2.0)
    r = I.day_costs(hrs, cap_kwh=10, eff=1.0, floor_pct=0, max_chg_kw=5, max_dis_kw=5, soc0=0)
    check("rzeczywistość: 20 kWh × 1 zł − 8 kWh × 0,3 zł", abs(r["actual"] - (20 - 2.4)) < 1e-6, r)
    check("bez baterii = rzeczywistość, gdy bateria nie pracowała", abs(r["nobat"] - r["actual"]) < 1e-6, r)
    # bateria bez planera: 8 kWh nadwyżki → bateria (cap 10, sprawność 100%) → wieczór pokrywa 8 h
    check("bateria bez planera: nadwyżka PV zostaje w domu (12 kWh importu zamiast 20)", abs(r["simple_import_kwh"] - 12.0) < 1e-6, r["simple_import_kwh"])
    check("bateria bez planera taniej o 8 × (1 − 0,3)", abs((r["nobat"] - r["simple"]) - 8 * 0.7) < 1e-6, (r["nobat"], r["simple"]))
    check("komplet godzin", r["complete"] and r["hours"] == 24)
    # sprawność i limit mocy
    r2 = I.day_costs(hrs, cap_kwh=10, eff=0.81, floor_pct=0, max_chg_kw=1.0, max_dis_kw=5, soc0=0)
    check("limit mocy ładowania 1 kW → mniej energii w baterii", r2["simple_import_kwh"] > r["simple_import_kwh"] + 3, r2["simple_import_kwh"])
    r6 = I.day_costs(hrs, cap_kwh=20, eff=0.81, floor_pct=0, max_chg_kw=5, max_dis_kw=5, soc0=0)
    check("sprawność 81%: z 8 kWh nadwyżki do domu wraca 8 × 0,81 = 6,48 kWh", abs(r6["simple_import_kwh"] - (20 - 6.48)) < 1e-6, r6["simple_import_kwh"])
    r7 = I.day_costs(hrs, cap_kwh=20, eff=1.0, floor_pct=0, max_chg_kw=5, max_dis_kw=0.5, soc0=0)
    check("limit mocy rozładowania 0,5 kW: wieczorem bateria oddaje 10 × 0,5 kWh", abs(r7["simple_import_kwh"] - 15.0) < 1e-6, r7["simple_import_kwh"])
    r3 = I.day_costs(hrs, cap_kwh=10, eff=1.0, floor_pct=50, max_chg_kw=5, max_dis_kw=5, soc0=50)
    check("próg rozładowania 50%: bateria oddaje tylko to, co ponad próg", abs(r3["simple_import_kwh"] - 15.0) < 1e-6, r3["simple_import_kwh"])
    # rzeczywistość z baterią sterowaną planerem: import tylko w tanich godzinach
    hrs2 = [B(load=1.0, imp=0.0, buy=1.2) for _ in range(24)]
    for h in range(0, 6):
        hrs2[h] = B(load=1.0, imp=3.0, buy=0.6)        # ładowanie z sieci w nocy
    r4 = I.day_costs(hrs2, cap_kwh=20, eff=1.0, floor_pct=0, max_chg_kw=5, max_dis_kw=5, soc0=0)
    check("planer: kupuje 18 kWh po 0,6 zamiast 24 kWh, w tym 18 po 1,2", abs(r4["actual"] - 10.8) < 1e-6 and abs(r4["nobat"] - (6 * 0.6 + 18 * 1.2)) < 1e-6, r4)
    check("brak godzin z danymi → None", I.day_costs([None] * 24, cap_kwh=10, eff=0.9, floor_pct=10, max_chg_kw=5, max_dis_kw=5, soc0=50) is None)
    part = I.day_costs(hrs[:10] + [None] * 14, cap_kwh=10, eff=0.9, floor_pct=10, max_chg_kw=5, max_dis_kw=5, soc0=50)
    check("dzień niepełny oznaczony", part["hours"] == 10 and not part["complete"])
    # brak ceny w godzinie → średnia z dnia
    hrs3 = [B(load=1.0, imp=1.0, buy=2.0) for _ in range(24)]
    hrs3[5][I.BUY_T] = 0
    r5 = I.day_costs(hrs3, cap_kwh=10, eff=0.9, floor_pct=10, max_chg_kw=5, max_dis_kw=5, soc0=50)
    check("godzina bez ceny liczona po średniej dnia", abs(r5["actual"] - 48.0) < 1e-6, r5["actual"])

    # ---------- 2. korekta PV
    fc = {}
    today = date(2026, 11, 20)
    for i in range(1, 15):
        fc[(today - timedelta(days=i)).isoformat()] = {"pv_fc": 10.0, "pv_act": 8.0}
    c = I.pv_correction(fc, today)
    check("korekta PV: wykonanie 80% prognozy → 0,8", c["factor"] == 0.8 and c["days"] == 14, c)
    fc2 = {k: {"pv_fc": 10.0, "pv_act": 2.0} for k in fc}
    check("korekta ograniczona do 0,7", I.pv_correction(fc2, today)["factor"] == 0.7)
    fc3 = {k: {"pv_fc": 10.0, "pv_act": 20.0} for k in fc}
    check("korekta ograniczona do 1,2", I.pv_correction(fc3, today)["factor"] == 1.2)
    few = {k: v for k, v in list(fc.items())[:4]}
    check("za mało dni (4) → 1,0", I.pv_correction(few, today)["factor"] == 1.0)
    six = {k: v for k, v in list(fc.items())[:6]}
    check("6 dni → korekta ściągnięta do 1 (0,88)", I.pv_correction(six, today)["factor"] == 0.88, I.pv_correction(six, today))
    tiny = {k: {"pv_fc": 0.5, "pv_act": 0.1} for k in fc}
    check("dni z prognozą < 1 kWh pomijane", I.pv_correction(tiny, today)["factor"] == 1.0)

    # ---------- 3. Insights.update: całkowanie, zamknięcie dnia, prognoza poranna
    hass = stubs.FakeHass()
    ins = I.Insights(hass)
    ins.set_params(cap=10.0, eff=1.0, floor=0.0, max_chg_kw=5.0, max_dis_kw=5.0)
    t = at(2026, 11, 5, 10, 0)
    data = {"load_power": 1000.0, "pv_power": 3000.0, "grid_power": -2000.0, "battery_power": 0.0,
            "energy_pv_today": 5.0, "energy_load_today": 7.0}
    for i in range(361):                                  # 10:00–11:00 co 10 s
        ins.update(t + timedelta(seconds=10 * i), data, 0.9, 0.4, 1, 60.0)
    b = ins.hours["2026-11-05T10"]
    check("godzina: 1 kWh domu, 3 kWh PV, 2 kWh eksportu", abs(b[I.LOAD] - 1.0) < 0.01 and abs(b[I.PV] - 3.0) < 0.01 and abs(b[I.EXP] - 2.0) < 0.01, b[:4])
    check("średnie ceny godziny", abs(I.hour_prices(b)[0] - 0.9) < 1e-9 and abs(I.hour_prices(b)[1] - 0.4) < 1e-9)
    check("SOC na koniec godziny", ins.hours["2026-11-05T11"][I.SOC] == 60.0)
    # przerwa (restart) nie jest całkowana
    ins.update(t + timedelta(hours=3), data, 0.9, 0.4, 1, 60.0)
    check("przerwa > 2 min nie jest całkowana", ins.hours["2026-11-05T13"][I.LOAD] == 0.0)
    # bateria: znak ładowania ujemny (−1) → moc −2000 W to ładowanie
    ins.update(t + timedelta(hours=3, seconds=10), dict(data, battery_power=-2000.0), 0.9, 0.4, -1, 61.0)
    check("znak baterii: −2 kW przy znaku −1 = ładowanie", ins.hours["2026-11-05T13"][I.BCH] > 0 and ins.hours["2026-11-05T13"][I.BDIS] == 0)
    # poranna prognoza: przed 6:00 nic, potem raz
    plan = {"curve": {"start": "2026-11-05T14:00:00+01:00", "soc": [70, 72, 74, 73, 60, 50, 40, 35, 30, 28, 25, 22]}}
    check("prognoza przed 6:00 — bez zapisu", not ins.snapshot(at(2026, 11, 5, 5, 0), 8.0, [0.5] * 24, plan))
    check("prognoza po 6:00 — zapis", ins.snapshot(at(2026, 11, 5, 14, 5), 8.0, [0.5] * 24, plan))
    check("drugi raz tego dnia — bez zapisu", not ins.snapshot(at(2026, 11, 5, 15, 0), 9.0, [0.5] * 24, plan))
    rec = ins.fc["2026-11-05"]
    check("plan SOC zapisany dla godzin dnia (14..23)", rec["soc_plan"][14] == 70 and rec["soc_plan"][23] == 28 and rec["soc_plan"][13] is None, rec["soc_plan"])
    # licznik PV: odczyt tuż po północy z wczorajszą wartością nie liczy się do nowego dnia
    ins.update(at(2026, 11, 5, 23, 59, 50), dict(data, energy_pv_today=9.5), 0.9, 0.4, 1, 30.0)
    ins.update(at(2026, 11, 6, 0, 0, 5), dict(data, energy_pv_today=9.5), 0.9, 0.4, 1, 30.0)
    check("zamknięcie dnia: wykonanie PV z licznika (9,5)", ins.fc["2026-11-05"]["pv_act"] == 9.5, ins.fc["2026-11-05"])
    check("licznik z wczoraj po północy nie trafia do nowego dnia", "pv" not in (ins.counters.get("2026-11-06") or {}), ins.counters.get("2026-11-06"))
    check("zamknięcie dnia: wynik oszczędności zapisany", "2026-11-05" in ins.days and ins.days["2026-11-05"]["hours"] >= 2, ins.days.get("2026-11-05"))
    check("zamknięcie dnia: SOC rzeczywisty godzina po godzinie", isinstance(ins.fc["2026-11-05"].get("soc_act"), list) and ins.fc["2026-11-05"]["soc_act"][23] == 30.0)

    # ---------- 4. oszczędności i trafność (agregaty)
    ins2 = I.Insights(hass)
    for i in range(1, 31):
        d = (date(2026, 11, 20) - timedelta(days=i)).isoformat()
        ins2.days[d] = {"actual": 5.0, "nobat": 9.0, "simple": 7.0, "hours": 24, "complete": True}
        ins2.fc[d] = {"pv_fc": 10.0, "pv_act": 8.0, "soc_plan": [None] * 10 + [50.0] * 14, "soc_act": [None] * 10 + [45.0] * 14}
    ins2.days["2026-10-01"] = {"actual": 1.0, "nobat": 1.0, "simple": 1.0, "hours": 10, "complete": False}
    at(2026, 11, 20, 12, 0)
    sv = ins2.savings(date(2026, 11, 20))
    check("30 dni: 4 zł/dzień wobec braku baterii", sv["last30"]["vs_nobat"] == 30 * 4.0 - 4.0 or sv["last30"]["vs_nobat"] == 29 * 4.0, sv["last30"])
    check("miesiąc: dni listopada", sv["month"]["days"] == 19 and sv["month"]["vs_simple"] == 19 * 2.0, sv["month"])
    check("dzień niepełny z przeszłości nie liczy się do sum", sv["total"]["days"] == 30, sv["total"])
    check("historia miesięcy", any(m["month"] == "2026-11" for m in sv["months"]))

    class LF:
        days = {(date(2026, 11, 20) - timedelta(days=i)).isoformat(): 10.0 for i in range(1, 31)}
        forecast_history = {(date(2026, 11, 20) - timedelta(days=i)).isoformat(): 12.0 for i in range(1, 31)}
    ac = ins2.accuracy(LF(), date(2026, 11, 20))
    check("PV: błąd 25%, prognoza zawyżona o 25%", ac["pv"]["mape"] == 25.0 and ac["pv"]["bias"] == 25.0, ac["pv"])
    check("zużycie: błąd 20%, zawyżone o 20%", ac["load"]["mape"] == 20.0 and ac["load"]["bias"] == 20.0, ac["load"])
    check("plan SOC: średni błąd 5 pp", ac["soc"]["mae"] == 5.0, ac["soc"])
    check("korekta PV w raporcie trafności", ac["pv_correction"]["factor"] == 0.8)
    check("30 wierszy dni", len(ac["days"]) == 30)

    # ---------- 5. planer: korekta PV i koszt zużycia baterii
    pvt = lambda h: 1.5 if 9 <= h < 15 else 0.0
    hass, c, sched = await mk((2026, 11, 3, 21, 22), 45, shutdown=25, load=12, pvt=pvt, progs=PROGS)
    rt = rtm.BmsRuntime(hass, c, sched); c.runtime = rt
    today = date(2026, 11, 3)
    for i in range(1, 15):
        rt.insights.fc[(today - timedelta(days=i)).isoformat()] = {"pv_fc": 10.0, "pv_act": 8.0}
    res = await sched.suggest()
    a = res.get("assumptions") or {}
    check("planer: korekta PV 0,8 w „Plan zakłada”", a.get("pv_factor") == 0.8, a)
    pv_curve = res["curve"]["pv"]
    check("planer: PV w krzywej przemnożone przez 0,8", any(abs(v - 1.2) < 0.01 for v in pv_curve), pv_curve[:20])
    hass.states.set("switch.bms_pv_forecast_correction", "off")
    res_off = await sched.suggest()
    check("korekta wyłączona przełącznikiem → 1,0", (res_off.get("assumptions") or {}).get("pv_factor") == 1.0 and any(abs(v - 1.5) < 0.01 for v in res_off["curve"]["pv"]))

    check("koszt zużycia: 0 bez ceny baterii", HP.wear_cost_per_kwh(hass, 10.0) == 0.0)
    hass.states.set("number.bms_battery_price_pln", 12000); hass.states.set("number.bms_battery_cycles", 6000)
    check("koszt zużycia: 12000 / (6000 × 10) = 0,20 zł/kWh", abs(HP.wear_cost_per_kwh(hass, 10.0) - 0.2) < 1e-9)
    hass.states.set("number.bms_battery_cycles", 0)
    check("koszt zużycia: 0 cykli → 0", HP.wear_cost_per_kwh(hass, 10.0) == 0.0)

    # ładowanie nocne G12w: z kosztem zużycia większym niż różnica cen — pominięte
    hass, c, sched = await mk((2026, 11, 3, 21, 22), 35, shutdown=25, load=14, pvt=lambda h: 0.4 if 9 <= h < 15 else 0.0, progs=PROGS)
    rt = rtm.BmsRuntime(hass, c, sched); c.runtime = rt
    sched.config[const.CONF_BATTERY_CAPACITY_KWH] = 10.0
    base = (await sched.suggest())["proposals"]["start_grid_charge"]
    check("bez kosztu zużycia: ładowanie nocne zaproponowane", not base["skip"], base["reason"])
    hass.states.set("number.bms_battery_price_pln", 30000); hass.states.set("number.bms_battery_cycles", 6000)   # 0,5 zł/kWh
    w = (await sched.suggest())
    P = w["proposals"]["start_grid_charge"]
    check("koszt zużycia 0,5 zł/kWh > różnica cen G12w → pominięte z wyjaśnieniem", P["skip"] and "zużycia baterii" in P["reason"], P["reason"])
    check("koszt zużycia w „Plan zakłada”", abs((w.get("assumptions") or {}).get("wear_cost", 0) - 0.5) < 1e-9, w.get("assumptions"))
    hass.states.set("number.bms_battery_price_pln", 3000)                 # 0,05 zł/kWh — nadal się opłaca
    P2 = (await sched.suggest())["proposals"]["start_grid_charge"]
    check("mały koszt zużycia: ładowanie nadal zaproponowane", not P2["skip"], P2["reason"])
    # opłacalność sprzedaży w runtime
    hass.states.set("number.bms_battery_price_pln", 30000)
    hass.states.set("sensor.rce_pse_cena", 0.9, hass.states.get("sensor.rce_pse_cena").attributes)
    ps = rt.profit_status()
    check("opłacalność sprzedaży uwzględnia zużycie baterii", ps.get("wear") and abs(ps["wear"] - 0.5) < 1e-9 and ps["net"] is not None
          and abs(ps["net"] - (ps["price"] * ps["eff"] - (ps["ref"] or 0.0) - 0.5)) < 1e-9, ps)

    # ---------- 6. stan runtime po restarcie: także klucze spoza wartości domyślnych
    hass, c, opt, rt = build()
    saved = {"notify_cfg": {"kinds": {"x": {"on": False}}}, "summary_sent": {"daily": "2026-11-05"}, "today_date": "2026-11-05"}
    async def fake_load(): return saved
    rt._state_store.async_load = fake_load
    await rt.async_load()
    check("po restarcie: ustawienia powiadomień zachowane", rt.state.get("notify_cfg") == saved["notify_cfg"], rt.state.get("notify_cfg"))
    check("po restarcie: znacznik wysłanego podsumowania zachowany", rt.state.get("summary_sent") == {"daily": "2026-11-05"})

    print(f"INSIGHTS PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
