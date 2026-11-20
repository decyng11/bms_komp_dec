"""Dowód zakazu arbitrażu: dzienne liczniki z sieci do baterii / z baterii do sieci / z sieci sprzedane, werdykt, podsumowania, alarm."""
import asyncio, json, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import arbproof as AP, issues as ISS, state_guard, tariff as tar
from homeassistant.util import dt as dt_util


def run(rt, c, S, t, minutes, chg_w, grid_w):
    sign = 1 if int(rt.battery_sign()["sign"]) >= 0 else -1
    c.data = dict(c.data or {}); c.data["battery_power"] = chg_w * sign
    S.set(c.config["grid_power"], grid_w)
    for _ in range(minutes * 6):
        t += timedelta(seconds=10)
        rt._track_grid_batt(t)
    return t


def today(rt, t):
    return dt_util.as_local(t).date().isoformat()


def pure():
    st = {}
    AP.add(st, "2026-11-19", 2.0, 3.0, 0.0)
    AP.add(st, "2026-11-19", 1.0, 0.0, 0.0)
    check("add: dolicza do doby", st["2026-11-19"] == {"in": 3.0, "out": 3.0, "leak": 0.0}, st)
    AP.add(st, "2026-11-19", -5, float("nan"), True)
    check("add: ujemne, nan i bool nie psują liczników", st["2026-11-19"] == {"in": 3.0, "out": 3.0, "leak": 0.0}, st)
    for i in range(40):
        AP.add(st, f"2026-10-{i % 28 + 1:02d}", 1.0)
    check("add: przycina do 30 dób", len(st) <= AP.KEEP_DAYS, len(st))

    check("clean: śmieci odrzucone, wartości ograniczone",
          AP.clean({"2026-11-19": {"in": "x", "out": -4, "leak": 1e9}, "zła": {"in": 1}, 5: {}, "2026-11-18": 7})
          == {"2026-11-19": {"in": 0.0, "out": 0.0, "leak": AP.MAX_KWH}}, AP.clean({"2026-11-19": {"in": "x", "out": -4, "leak": 1e9}}))
    check("clean: nie-słownik → pusto", AP.clean(None) == {} and AP.clean([1]) == {})

    v = lambda i, o, l, tol=0.5: AP.verdict({"in": i, "out": o, "leak": l}, tol)["level"]  # noqa: E731
    check("werdykt: doba bez arbitrażu → idle", v(0, 0, 0) == "idle")
    check("werdykt: ładowanie z sieci i sprzedaż, leak 0 → ok", v(3, 4, 0) == "ok")
    check("werdykt: leak w granicach tolerancji → ok z adnotacją", v(3, 4, 0.3) == "ok" and "tolerancji" in AP.verdict({"in": 3, "out": 4, "leak": 0.3}, 0.5)["text"])
    check("werdykt: leak ponad tolerancję → bad", v(3, 4, 2.0) == "bad")
    check("werdykt: blokada wyłączona i leak → warn", v(3, 4, 2.0, 0) == "warn")
    check("werdykt: tylko PV (in 0) i sprzedaż → ok", v(0, 5, 0) == "ok")

    rows = AP.rows({"2026-11-18": {"in": 1, "out": 2, "leak": 0}, "2026-11-19": {"in": 3, "out": 4, "leak": 0}}, 1, 0.5)
    check("rows: najnowsze pierwsze, limit", len(rows) == 1 and rows[0]["date"] == "2026-11-19" and rows[0]["in"] == 3.0, rows)
    ln = AP.line(rows[0])
    check("line: 19.11", AP.line(rows[0]).startswith("Arbitraż 19.11:"), AP.line(rows[0]))
    check("line: opis po polsku z liczbami", "z sieci do baterii 3,0 kWh" in ln and "z baterii do sieci 4,0 kWh" in ln and "z sieci sprzedane 0,0 kWh" in ln and "zakaz dotrzymany" in ln, ln)
    wl = AP.week_line({"2026-11-18": {"in": 1, "out": 2, "leak": 0}, "2026-11-19": {"in": 3, "out": 4, "leak": 0}, "2026-11-01": {"in": 9, "out": 9, "leak": 9}},
                      "2026-11-14", "2026-11-20", 0.5)
    check("week_line: suma za okres, bez dni spoza okresu", wl and "(2 dób)" in wl and "4,0 kWh" in wl and "9,0" not in wl and "zakaz dotrzymany" in wl, wl)
    wl = AP.week_line({"2026-11-19": {"in": 3, "out": 4, "leak": 2}}, "2026-11-14", "2026-11-20", 0.5)
    check("week_line: UWAGA przy możliwym arbitrażu", wl and "UWAGA" in wl, wl)
    check("week_line: brak ruchu → None", AP.week_line({}, "a", "b", 0.5) is None
          and AP.week_line({"2026-11-19": {"in": 0, "out": 0, "leak": 0}}, "2026-11-14", "2026-11-20", 0.5) is None)


async def runtime_part():
    tar.set_profile(tar.make_profile({"tariff_mode": "zone"}, prices_fn=lambda d: None, eff_fn=lambda: 0.9, source=""))

    # ---------- uczciwy scenariusz: noc z sieci → dom zużywa → po południu sprzedaż z PV
    hass, c, opt, rt = build(); S = hass.states
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0}
    t = dt_util.now().replace(microsecond=0)
    rt._track_grid_batt(t)
    t = run(rt, c, S, t, 60, 2500, 2700)                 # 1 h z sieci → ~2,4 kWh
    t = run(rt, c, S, t, 150, -1000, 0)                  # dom zużywa z baterii ponad 2,4 kWh
    t = run(rt, c, S, t, 120, 3000, 60)                  # ładowanie z PV
    S.set("number.bms_grid_arbitrage_block_kwh", 0.5)
    t = run(rt, c, S, t, 60, -3000, -3000)               # sprzedaż do sieci 3 kWh
    rows = rt.arb_proof(3)
    r = rows[0]
    check("uczciwy dzień: z sieci do baterii ~2,4 kWh", abs(r["in"] - 2.4) < 0.2, r)
    check("uczciwy dzień: z baterii do sieci ~3 kWh", abs(r["out"] - 3.0) < 0.2, r)
    check("uczciwy dzień: z sieci sprzedane 0", r["leak"] <= AP.LEAK_OK and r["level"] == "ok", r)
    check("uczciwy dzień: brak alarmu w liście problemów", "arbitrage" not in [i["id"] for i in ISS.collect(rt, t)], ISS.collect(rt, t))

    # ---------- naruszenie: ładowanie z sieci i od razu sprzedaż (symulacja obejścia blokady)
    hass, c, opt, rt = build(); S = hass.states
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0}
    t = dt_util.now().replace(microsecond=0)
    rt._track_grid_batt(t)
    t = run(rt, c, S, t, 60, 2500, 2700)
    t = run(rt, c, S, t, 60, -3000, -3000)
    r = rt.arb_proof(1)[0]
    check("naruszenie: z sieci sprzedane ~2,4 kWh (górna granica) i werdykt bad", 2.0 < r["leak"] <= 2.6 and r["level"] == "bad", r)
    got = ISS.collect(rt, t)
    check("naruszenie: błąd na liście „co nie działa”", any(i["id"] == "arbitrage" and i["level"] == "error" for i in got), got)
    S.set("number.bms_grid_arbitrage_block_kwh", 0)
    check("blokada wyłączona: werdykt warn zamiast bad", rt.arb_proof(1)[0]["level"] == "warn", rt.arb_proof(1)[0])
    S.set("number.bms_grid_arbitrage_block_kwh", 0.5)

    # ---------- podsumowanie dnia i tygodnia + wpis w dzienniku przy zamknięciu doby
    day = dt_util.as_local(t).date()
    txt = rt.summary_text("day", day)
    check("podsumowanie dnia zawiera wiersz o arbitrażu", "z sieci sprzedane" in txt and "Arbitraż" in txt, txt)
    txt = rt.summary_text("week", day)
    check("raport tygodniowy zawiera sumę arbitrażu", "Arbitraż (1 dób)" in txt and "UWAGA" in txt, txt)
    rt._sale_report(day)
    ents = [e for e in rt.log.last(20) if str(e.get("msg", "")).startswith("Arbitraż")]
    check("zamknięcie doby: wpis w dzienniku (ostrzeżenie przy naruszeniu)", ents and ents[0]["level"] == "warn", ents)

    # ---------- doba bez ruchu: brak wiersza
    hass, c, opt, rt = build()
    check("brak ruchu: brak wierszy i linii w podsumowaniu", rt.arb_proof() == [] and "Arbitraż" not in rt.summary_text("day", date(2026, 11, 19)))

    # ---------- restart: pula startuje od licznika (najgorszy przypadek), nie od zera
    hass, c, opt, rt = build(); S = hass.states
    c.data = {"energy_battery_charge_today": 0.0, "energy_pv_today": 30.0}
    rt.state["grid_batt"] = {"kwh": 2.0, "saved": 2.0}
    t = dt_util.now().replace(microsecond=0)
    rt._track_grid_batt(t)
    t = run(rt, c, S, t, 30, -4000, -4000)
    r = rt.arb_proof(1)[0]
    check("po restarcie z 2 kWh z sieci w baterii: sprzedaż liczona jako możliwy arbitraż", 1.5 < r["leak"] <= 2.0, r)

    # ---------- state_guard
    st = {"arb_proof": {"2026-11-19": {"in": 1, "out": 2, "leak": 0}, "zła": 5, "2026-11-18": {"in": "x"}}}
    fixed = state_guard.sanitize(st)
    check("state_guard: arb_proof oczyszczony", "arb_proof" in fixed and st["arb_proof"]["2026-11-18"] == {"in": 0.0, "out": 0.0, "leak": 0.0} and "zła" not in st["arb_proof"], (st, fixed))
    st = {"arb_proof": [1]}
    state_guard.sanitize(st)
    check("state_guard: zły typ → pusty słownik", st["arb_proof"] == {})
    st = {"arb_proof": {"2026-11-19": {"in": 1.0, "out": 2.0, "leak": 0.0}}}
    check("state_guard: poprawny wpis bez zmian", state_guard.sanitize(st) == [])


async def main():
    pure()
    await runtime_part()


asyncio.run(main())
print(f"ARBPROOF PASS={common.PASS} FAIL={common.FAIL}")
