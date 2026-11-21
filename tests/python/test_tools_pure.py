"""Czysta logika nowych narzędzi: deeds (co EMS zrobił), outage (test zaniku sieci), sunny, adviser, expand."""
import sys
from datetime import date, timedelta
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import deeds as D, outage as O, sunny as SU, adviser as AD, expand as EX

TODAY = date(2026, 11, 20)


def deeds_part():
    E = lambda kind, level, msg: {"kind": kind, "level": level, "msg": msg}
    check("deeds: zablokowany zapis", D.classify(E("guard", "warn", "Sprzedaż (auto) ZABLOKOWANA: SOC")) == "blocked")
    check("deeds: zatrzymanie sprzedaży", D.classify(E("guard", "warn", "Zatrzymuję sprzedaż: import")) == "sale_stop")
    check("deeds: inne zabezpieczenie (warn)", D.classify(E("guard", "warn", "Rozjazd: falownik ładuje")) == "guard")
    check("deeds: guard info/ok nie liczy się", D.classify(E("guard", "ok", "Samokontrola: zgodny")) is None and D.classify(E("guard", "info", "x")) is None)
    check("deeds: automat", D.classify(E("auto", "ok", "Auto-zastosowano 2 zmian(y)")) == "auto" and D.classify(E("auto", "warn", "Auto-zastosowano")) is None and D.classify(E("auto", "ok", "inne")) is None)
    check("deeds: komenda ok", D.classify(E("command", "ok", "Sprzedaż 6000W")) == "commands" and D.classify(E("command", "error", "x")) is None)
    for bad in (None, 5, "x", [], {}, {"kind": 3, "level": None}):
        check(f"deeds: śmieci ({str(bad)[:12]})", D.classify(bad) is None)
    st = {}
    for cat in ("blocked", "blocked", "commands", "nieznana"):
        st = D.bump(st, "2026-11", cat)
    check("deeds: zliczanie, nieznana kategoria ignorowana", st == {"2026-11": {"blocked": 2, "commands": 1}}, st)
    for i in range(20):
        st = D.bump(st, f"2025-{(i % 12) + 1:02d}" if i < 12 else f"2026-{(i % 12) + 1:02d}", "guard")
    check("deeds: maks. 13 miesięcy", len(st) <= D.KEEP_MONTHS, len(st))
    check("deeds: zły miesiąc nie dopisuje", D.bump({}, "zły", "guard") == {} and D.bump({}, None, "guard") == {})
    dirty = D.clean({"2026-11": {"blocked": "x", "guard": -1, "auto": float("nan"), "commands": True, "sale_stop": 3.7}, "zły": {"guard": 1}, "2026-10": 5, 7: {}})
    check("deeds: clean usuwa śmieci, zostawia poprawne liczby całkowite", dirty == {"2026-11": {"sale_stop": 3}, } or dirty.get("2026-11") == {"sale_stop": 3}, dirty)
    check("deeds: clean na nie-słowniku", D.clean(None) == {} and D.clean("x") == {} and D.clean([1]) == {})
    s = D.summary({"2026-11": {"blocked": 2, "commands": 14, "auto": 1}}, "2026-11")
    check("deeds: tekst z licznikami", "2× zablokował" in s["text"] and "14 wykonał komend" in s["text"] and "1× zastosował" in s["text"] and s["total"] == 17, s)
    check("deeds: pusty miesiąc → pusty tekst", D.summary({}, "2026-11")["text"] == "" and D.summary(None, "2026-11")["total"] == 0)


def outage_part():
    sc = O.scenarios(80, 15, 10.0, 2500, [("Bojler", 2000.0), ("Pralka", 300.0)])
    ids = [x["id"] for x in sc]
    check("outage: cztery warianty", ids == ["now", "no_top", "essential", "full"], ids)
    h = {x["id"]: x["hours"] for x in sc}
    check("outage: bez największego odbiornika dłużej, podstawa jeszcze dłużej, pełna bateria dłużej niż teraz", h["now"] < h["no_top"] and h["now"] < h["essential"] and h["full"] > h["now"], h)
    check("outage: etykieta z nazwą i mocą odbiornika", "Bojler" in sc[1]["label"] and "2,0 kW" in sc[1]["label"], sc[1]["label"])
    check("outage: tekst czasu", all(isinstance(x["text"], str) and x["text"] for x in sc))
    sc2 = O.scenarios(100, 15, 10.0, 100, None)
    check("outage: pełna bateria i mały pobór — bez zbędnych wariantów", [x["id"] for x in sc2] == ["now"], [x["id"] for x in sc2])
    sc3 = O.scenarios(80, 15, 10.0, 500, [("x", 0), ("y", float("nan")), (5, 100), "z"])
    check("outage: śmieci w liście odbiorników pomijane", [x["id"] for x in sc3] == ["now", "essential", "full"], [x["id"] for x in sc3])
    check("outage: brak danych → pusto", O.scenarios(None, 15, 10, 500) == [] and O.scenarios(80, 15, 0, 500) == [] and O.scenarios(80, 15, 10, None) == [])
    check("outage: SOC poniżej progu → 0 h bez wyjątku", O.scenarios(10, 15, 10.0, 500)[0]["hours"] == 0.0)


def sunny_part():
    base = {(TODAY - timedelta(days=i)).isoformat(): 14.0 for i in range(2, 20)}
    dull = {**base, TODAY.isoformat(): 2.0, (TODAY - timedelta(days=1)).isoformat(): 3.5}
    r = SU.evaluate(dull, 12.0, TODAY)
    check("sunny: dwa pochmurne dni, jutro słonecznie → powiadomienie z liczbami", r and r["tomorrow"] == 12.0 and r["best"] == 14.0 and "dziś 2,0 kWh" in r["text"] and "wczoraj 3,5 kWh" in r["text"], r)
    check("sunny: jutro też słabo → cisza", SU.evaluate(dull, 6.0, TODAY) is None)
    check("sunny: tylko dziś pochmurno, wczoraj dobrze → cisza", SU.evaluate({**dull, (TODAY - timedelta(days=1)).isoformat(): 13.0}, 12.0, TODAY) is None)
    check("sunny: brak wczorajszego odczytu → cisza", SU.evaluate({k: v for k, v in dull.items() if k != (TODAY - timedelta(days=1)).isoformat()}, 12.0, TODAY) is None)
    check("sunny: za krótka historia → cisza", SU.evaluate({TODAY.isoformat(): 2.0, (TODAY - timedelta(days=1)).isoformat(): 2.0, (TODAY - timedelta(days=2)).isoformat(): 14.0}, 12.0, TODAY) is None)
    check("sunny: najlepszy dzień < 3 kWh (zima / awaria licznika) → cisza", SU.evaluate({k: 2.0 for k in dull}, 2.0, TODAY) is None)
    check("sunny: brak prognozy → cisza", SU.evaluate(dull, None, TODAY) is None and SU.evaluate(dull, "x", TODAY) is None)
    check("sunny: absurdalna prognoza (≥1000) → cisza", SU.evaluate(dull, 5000, TODAY) is None)
    for bad in (None, 5, "x", [], {"zła": 1}):
        check(f"sunny: śmieci ({str(bad)[:10]})", SU.evaluate(bad, 10, TODAY) is None)
    check("sunny: zły dzień", SU.evaluate(dull, 12.0, "2026-11-20") is None)
    old = {(TODAY - timedelta(days=i)).isoformat(): 14.0 for i in range(40, 60)}
    check("sunny: dane starsze niż 30 dni nie liczą się", SU.evaluate({**old, TODAY.isoformat(): 1.0, (TODAY - timedelta(days=1)).isoformat(): 1.0}, 12.0, TODAY) is None)


def adviser_part():
    ok = {"reserve_pct": 35, "soc_min": 50, "soc_days": 14, "cap_conf": 10.0, "cap_est": 10.4, "cap_samples": 12, "battery_price": 20000, "sell_windows_on": True}
    check("adviser: zdrowa konfiguracja → brak porad", AD.advise(ok) == [])
    a = AD.advise({**ok, "reserve_pct": 40, "soc_min": 75})
    check("adviser: rezerwa za wysoka, z liczbami i propozycją", len(a) == 1 and a[0]["id"] == "reserve_high" and "40%" in a[0]["text"] and "75%" in a[0]["text"] and "do 30%" in a[0]["text"], a)
    check("adviser: rezerwa blisko użycia → bez porady", AD.advise({**ok, "reserve_pct": 40, "soc_min": 50}) == [])
    check("adviser: za mało dób SOC → bez porady", AD.advise({**ok, "reserve_pct": 40, "soc_min": 75, "soc_days": 3}) == [])
    check("adviser: rezerwa 0 → bez porady", AD.advise({**ok, "reserve_pct": 0, "soc_min": 75}) == [])
    check("adviser: niska rezerwa (<20%) → bez porady", AD.advise({**ok, "reserve_pct": 15, "soc_min": 80}) == [])
    c = AD.advise({**ok, "cap_est": 7.0})
    check("adviser: pojemność zmierzona ≠ ustawiona", len(c) == 1 and c[0]["id"] == "capacity_mismatch" and c[0]["level"] == "warn" and "10,0" in c[0]["text"].replace(".", ","), c)
    check("adviser: mała różnica pojemności → cisza", AD.advise({**ok, "cap_est": 9.0}) == [])
    check("adviser: za mało próbek pojemności → cisza", AD.advise({**ok, "cap_est": 5.0, "cap_samples": 2}) == [])
    w = AD.advise({**ok, "battery_price": 0})
    check("adviser: koszt zużycia 0 przy włączonej sprzedaży", len(w) == 1 and w[0]["id"] == "wear_zero", w)
    check("adviser: koszt zużycia 0, ale sprzedaż wyłączona → cisza", AD.advise({**ok, "battery_price": 0, "sell_windows_on": False}) == [])
    allp = AD.advise({"reserve_pct": 40, "soc_min": 75, "soc_days": 14, "cap_conf": 10.0, "cap_est": 7.0, "cap_samples": 9, "battery_price": 0, "sell_windows_on": True})
    check("adviser: trzy porady naraz, w stałej kolejności", [x["id"] for x in allp] == ["reserve_high", "capacity_mismatch", "wear_zero"], [x["id"] for x in allp])
    for bad in (None, 5, "x", [], {}, {"reserve_pct": "x", "soc_min": float("nan")}):
        check(f"adviser: śmieci ({str(bad)[:12]})", AD.advise(bad) == [])


def expand_part():
    days = [{"pv": 10.0, "exp": 4.0}] * 20
    b = EX.battery(days, 5, 1500, 0.9, 0.4, 0.1)
    # jednostkowa wartość: 0,9*0,9 − 0,4 − 0,1 = 0,31; przesunięte dziennie min(5,4)=4 → rocznie 1460 kWh, ×0,9 przesunięte
    check("battery: wartość 1 kWh i roczny zysk", b and b["unit_value"] == 0.31 and b["annual"] == round(4 * 365 * 0.31) and b["cost"] == 7500, b)
    check("battery: zwrot w latach", b["payback_years"] == round(7500 / (4 * 365 * 0.31), 1), b)
    check("battery: więcej baterii niż nadwyżki nie zwiększa zysku ponad nadwyżkę", EX.battery(days, 50, 1500, 0.9, 0.4, 0.1)["annual"] == b["annual"])
    n = EX.battery(days, 5, 1500, 0.5, 0.6, 0.1)
    check("battery: ujemna wartość → brak zwrotu i uwaga", n["unit_value"] < 0 and n["payback_years"] is None and n["note"], n)
    check("battery: za mało dób → None", EX.battery(days[:5], 5, 1500, 0.9, 0.4) is None)
    for bad in ((0, 1500), (-1, 1500), (5, -1), (5000, 1500), ("x", 1500), (None, None)):
        check(f"battery: złe parametry {bad}", EX.battery(days, bad[0], bad[1], 0.9, 0.4) is None)
    check("battery: brak cen → None", EX.battery(days, 5, 1500, None, 0.4) is None and EX.battery("x", 5, 1500, 0.9, 0.4) is None)
    p = EX.pv(days, 2, 5, 4500, 0.9, 0.4)
    # 10 kWh/dobę z 5 kWp → +2 kWp = +4 kWh/dobę = 1460 kWh/rok; część własna = 60%
    check("pv: dodatkowa produkcja proporcjonalna do mocy", p and p["extra_kwh_year"] == 1460 and p["self_share_pct"] == 60 and p["cost"] == 9000, p)
    check("pv: wartość 1 kWh to średnia ważona cen", p["unit_value"] == round(0.6 * 0.9 + 0.4 * 0.4, 2), p)
    check("pv: zysk i zwrot", p["annual"] == round(1460 * (0.6 * 0.9 + 0.4 * 0.4)) and p["payback_years"] == round(9000 / (1460 * 0.7), 1), p)
    check("pv: za mało dób / zerowa produkcja → None", EX.pv(days[:3], 2, 5, 4500, 0.9, 0.4) is None and EX.pv([{"pv": 0.0, "exp": 0.0}] * 20, 2, 5, 4500, 0.9, 0.4) is None)
    for bad in ((0, 5), (2, 0), (-1, 5), ("x", 5), (2, "x"), (2000, 5)):
        check(f"pv: złe parametry {bad}", EX.pv(days, bad[0], bad[1], 4500, 0.9, 0.4) is None)
    check("pv: dziwne dane dobowe nie wywalają", EX.pv([{"pv": "x"}, None, 5] + days, 2, 5, 4500, 0.9, 0.4) is not None)


deeds_part()
outage_part()
sunny_part()
adviser_part()
expand_part()
print(f"TOOLS_PURE PASS={common.PASS} FAIL={common.FAIL}")
