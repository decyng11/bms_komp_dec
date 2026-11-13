"""Nowości po 0.8.8: koszt bez PV i baterii, skąd energia dla domu, pobór w drogich godzinach, okno arbitrażu,
podsumowanie dnia z telefonem (domyślna konfiguracja)."""
import asyncio
from datetime import date, datetime
from common import *   # noqa
import common
from custom_components.bms_komp_dec import money as M, ledger as LG, monitor as mon

def at(y, m, d, hh, mm=0):
    stubs.CLOCK["now"] = datetime(y, m, d, hh, mm, tzinfo=stubs.TZ); return stubs.CLOCK["now"]

class _Stats: pass
def mk_ledger():
    L = LG.Ledger(stubs.FakeHass())
    L.days = {
        "2026-11-06": {"export_kwh": 3.0, "import_kwh": 4.0, "revenue": 1.5, "cost": 2.8, "neg_export_kwh": 0.0, "peak_import_kwh": 3.0},
        "2026-11-07": {"export_kwh": 2.8, "import_kwh": 3.5, "revenue": 1.15, "cost": 2.38, "neg_export_kwh": 0.0, "peak_import_kwh": 1.0}}
    return L
def mk_stats():
    S = _Stats()
    S.days = {"2026-11-06": {"pv": 20.0, "load": 18.0, "imp": 4.0, "exp": 3.0, "chg": 6.0, "dis": 5.0},
              "2026-11-07": {"pv": 19.2, "load": 16.4, "imp": 3.5, "exp": 2.8, "chg": 13.3, "dis": 11.4}}
    return S

def main():
    L, S = mk_ledger(), mk_stats(); d = date(2026, 11, 7)
    sv = M.savings(L, S, d, "day")
    # średnia cena zakupu z dnia: 2,38/3,5 = 0,68; bez systemu 16,4 × 0,68 = 11,15; koszt netto 2,38 − 1,15 = 1,23 → oszczędność 9,92
    check("savings day: bez systemu 16,4 kWh × 0,68", abs(sv["without_cost"] - 11.15) < 0.02 and abs(sv["actual_cost"] - 1.23) < 1e-6 and abs(sv["saving"] - 9.92) < 0.03, sv)
    sm = M.savings(L, S, d, "month")
    check("savings month: suma obu dni", abs(sm["load_kwh"] - 34.4) < 1e-6 and sm["saving"] > 0, sm)
    # dziś bez importu → cena z miesiąca
    L2 = mk_ledger(); L2.days["2026-11-07"].update({"import_kwh": 0.0, "cost": 0.0})
    s0 = M.savings(L2, S, d, "day")
    check("savings: brak importu dziś → średnia z miesiąca", s0["avg_buy"] is not None and s0["saving"] is not None, s0)
    L3 = LG.Ledger(stubs.FakeHass()); S3 = _Stats(); S3.days = {"2026-11-07": {"load": 5.0}}
    check("savings: brak jakiejkolwiek ceny → None, bez błędu", M.savings(L3, S3, d, "day")["saving"] is None)

    sp = M.split(S, d, "day")
    check("split: sieć 3,5, bateria 11,4 → PV bezpośrednio 1,5 z 16,4", sp["grid_kwh"] == 3.5 and sp["battery_kwh"] == 11.4 and abs(sp["pv_kwh"] - 1.5) < 0.01, sp)
    check("split: procenty sumują się do 100", sp["grid_pct"] + sp["battery_pct"] + sp["pv_pct"] == 100, sp)
    S4 = _Stats(); S4.days = {"2026-11-07": {"load": 5.0, "imp": 9.0, "dis": 9.0}}
    sp4 = M.split(S4, d, "day")
    check("split: import i bateria większe niż zużycie → przycięte do 100%", sp4["grid_kwh"] == 5.0 and sp4["battery_kwh"] == 0.0 and sp4["grid_pct"] == 100, sp4)
    check("split: brak zużycia → None", M.split(_Stats.__new__(_Stats) if False else type("X", (), {"days": {}})(), d, "day") is None)

    tf = M.tariff_split(L, d, "day")
    check("taryfa dziś: 1,0 z 3,5 kWh w drogich (29%)", tf["peak_kwh"] == 1.0 and tf["peak_pct"] == 29 and tf["offpeak_pct"] == 71, tf)
    tfm = M.tariff_split(L, d, "month")
    check("taryfa miesiąc: 4,0 z 7,5 kWh", abs(tfm["peak_kwh"] - 4.0) < 1e-6 and tfm["peak_pct"] == 53, tfm)
    check("taryfa: stare dni bez pola peak_import_kwh liczą się jako tanie (bez błędu)", M.tariff_split({"days": {}} if False else type("X", (), {"days": {"2026-11-07": {"import_kwh": 2.0}}})(), d, "day")["peak_kwh"] == 0)

    ls = M.lines(L, S, d, "day")
    check("lines: trzy linie bez zbędnych kropek", len(ls) == 3 and "około 11,15 zł" in ls[0] and "PV 9%" in ls[1] and "(29%)" in ls[2] and not any(", zł" in x for x in ls), ls)
    wk = M.lines(L, S, d, "week", date(2026, 11, 1))
    check("lines: tydzień obejmuje oba dni", wk and "34,4 kWh" in wk[1], wk)

    # ---- księga zapisuje pobór w drogich godzinach
    LL = LG.Ledger(stubs.FakeHass())
    t0 = at(2026, 11, 7, 10, 0); LL.update(t0, 1000.0, 0.3, 0.8, True)
    t1 = at(2026, 11, 7, 10, 1); LL.update(t1, 3600.0, 0.3, 0.8, True)
    t2 = at(2026, 11, 7, 10, 2); LL.update(t2, 3600.0, 0.3, 0.2, False)
    day = LL.days["2026-11-07"]
    check("ledger: peak_import_kwh tylko dla poboru w szczycie", abs(day["peak_import_kwh"] - 0.06) < 0.001 and abs(day["import_kwh"] - 0.12) < 0.001, day)
    LL.update(at(2026, 11, 7, 10, 3), -3600.0, 0.3, 0.2, True)
    check("ledger: eksport w szczycie nie zwiększa peak_import_kwh", abs(LL.days["2026-11-07"]["peak_import_kwh"] - 0.06) < 0.001)
    check("ledger: sums zawiera peak_import_kwh", "peak_import_kwh" in LL.sums(date(2026, 11, 7), "day"))

    asyncio.run(notify_part())
    asyncio.run(daily_block_part())
    print(f"MONEY PASS={common.PASS} FAIL={common.FAIL}")

def mkenv():
    hass, c, opt, rt = build()
    c.config["notify_service"] = "notify.mobile_app_tel"
    hass.states.set("switch.bms_notifications_enabled", "on")
    return hass, c, opt, rt
def push(h): return [c for c in h.services.calls if c[0] == "notify"]

async def notify_part():
    # ---- podsumowanie dnia z domyślnej konfiguracji trafia na telefon i zawiera nowe linie
    hass, c, opt, rt = mkenv()
    rt.ledger.days["2026-11-07"] = {"export_kwh": 2.8, "import_kwh": 3.5, "revenue": 1.15, "cost": 2.38, "neg_export_kwh": 0.0, "peak_import_kwh": 1.0}
    rt.stats.days["2026-11-07"] = {"pv": 19.2, "load": 16.4, "imp": 3.5, "exp": 2.8, "chg": 13.3, "dis": 11.4}
    await rt.monitor._summaries(at(2026, 11, 7, 21, 5))
    p = push(hass)
    check("podsumowanie dnia: trafiło na telefon przy domyślnej konfiguracji", len(p) == 1 and "podsumowanie dnia" in p[0][2]["title"], [x[2].get("title") for x in p])
    msg = p[0][2]["message"] if p else ""
    check("podsumowanie dnia: bilans, oszczędność, skąd energia, taryfa", "Bilans z siecią" in msg and "Bez PV i baterii" in msg and "Skąd energia" in msg and "drogie godziny" in msg, msg)
    # po wyłączeniu: komunikat w dzienniku zamiast ciszy
    hass, c, opt, rt = mkenv()
    rt.state["notify_cfg"] = __import__("custom_components.bms_komp_dec.notify_cfg", fromlist=["x"]).effective({"kinds": {"summary_daily": {"on": False}}})
    await rt.monitor._summaries(at(2026, 11, 7, 21, 5))
    check("wyłączone: nic na telefon, ale wpis w dzienniku mówi dlaczego", not push(hass) and any("wyłączone w konfiguratorze" in e["msg"] for e in rt.log.last(10)), rt.log.last(3))

    # ---- powiadomienie „okno arbitrażu” usunięte: EMS nie podpowiada „kup tanio z sieci → sprzedaj drogo” (niedozwolone)
    hass, c, opt, rt = mkenv()
    sell = [0.30] * 24; sell[19] = 0.95
    buy = [0.70] * 24; buy[3] = 0.20
    opt._read_rce_arrays = lambda: {"2026-11-08": sell}
    opt.buy_hourly_for = lambda d: buy if d.isoformat() == "2026-11-08" else None
    await rt.monitor._prices_tomorrow(at(2026, 11, 7, 15, 0))
    check("arbitraż: brak powiadomienia nawet przy dużym spreadzie", not [x for x in push(hass) if "arbitraż" in x[2]["title"]])
    from custom_components.bms_komp_dec import notify_cfg as _nc
    check("arbitraż: rodzaj usunięty z katalogu powiadomień", "arbitrage_window" not in _nc.CATALOG)

async def daily_block_part():
    # ---- blokada sprzedaży według energii pobranej z sieci w ciągu dnia
    from homeassistant.util import dt as dt_util
    hass, c, opt, rt = mkenv()
    c.data = dict(c.data or {}); c.data["energy_grid_import_today"] = 3.4
    check("domyślnie: 3,4 kWh dziś > limit 3,0 → sprzedaż zablokowana", (rt.sell_block_reason() or "").startswith("dziś pobrano z sieci 3.4 kWh"), rt.sell_block_reason())
    c.data["energy_grid_import_today"] = 2.9
    check("2,9 kWh < 3,0 → brak blokady", rt.sell_block_reason() is None, rt.sell_block_reason())
    hass.states.set("number.bms_grid_import_sell_block_kwh", "2.5")
    check("limit z ustawień (2,5): 2,9 kWh blokuje", "limit 2.5" in (rt.sell_block_reason() or ""), rt.sell_block_reason())
    hass.states.set("number.bms_grid_import_sell_block_kwh", "0")
    check("limit 0 = wyłączone", rt.sell_block_reason() is None)
    hass.states.set("number.bms_grid_import_sell_block_kwh", "3")
    c.data["energy_grid_import_today"] = None
    rt.ledger.days[dt_util.now().date().isoformat()] = {"export_kwh": 0.0, "import_kwh": 4.0, "revenue": 0.0, "cost": 1.0, "neg_export_kwh": 0.0, "peak_import_kwh": 0.0}
    check("brak licznika falownika: liczy się z księgi rozliczeń (4,0 kWh)", "4.0 kWh" in (rt.sell_block_reason() or ""), rt.sell_block_reason())
    try:
        await rt.run_command("sprzedaz_6000w", source="ręcznie")
        blocked = False
    except Exception as err:  # noqa: BLE001
        blocked = "Sprzedaż zablokowana" in str(err)
    check("przycisk „Sprzedaż 6000W” zablokowany przy imporcie dziś ponad limit", blocked)

    # plan nie obiecuje sprzedaży, którą blokada i tak zatrzyma
    async def fake_suggest():
        return {"generated_at": "x", "mode": "normal", "curve": [], "assumptions": {},
                "proposals": {"bateria_sprzedaz_start_2": {"proposed": "16:00", "current": "00:00", "skip": False, "label": "Sprzedaż wieczorna", "reason": "Najlepsze okno 16–17."},
                              "start_grid_charge": {"proposed": "02:00", "current": "00:00", "skip": False, "label": "Ładowanie", "reason": "tanio"}}}
    rt.optimizer.suggest = fake_suggest
    plan = await rt.refresh_plan(force=True)
    pr = plan["proposals"]
    check("plan: sprzedaż oznaczona jako pominięta z powodem blokady", pr["bateria_sprzedaz_start_2"]["skip"] is True and "Blokada sprzedaży: dziś pobrano z sieci 4.0 kWh" in pr["bateria_sprzedaz_start_2"]["reason"], pr["bateria_sprzedaz_start_2"])
    check("plan: ładowanie z sieci bez zmian", pr["start_grid_charge"]["skip"] is False)

main()
