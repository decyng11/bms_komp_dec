"""Podsumowania w tabeli: formatowanie liczb, wyrównanie kolumn, dzień / tydzień / miesiąc, braki danych, śmieci."""
import sys
from datetime import date
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import summtable as S, report as R

T = lambda net, pv=10.0, load=8.0, imp=2.0, exp=4.0, chg=3.0, dis=2.5, sc=60: {"days": 1, "net": net, "pv_kwh": pv, "load_kwh": load, "import_kwh": imp, "export_kwh": exp, "chg_kwh": chg, "dis_kwh": dis, "self_consumption_pct": sc}
EMPTY = {"days": 0}


def main():
    f = S.fmt
    check("fmt: przecinek i znak", f(4.8, 2, True) == "+4,80" and f(-1.234, 2, True) == "-1,23" and f(12.34) == "12,3", (f(4.8, 2, True), f(-1.234, 2, True)))
    check("fmt: zero bez minusa", f(-0.001, 2, True) == "+0,00" and f(-0.04, 1) == "0,0", (f(-0.001, 2, True), f(-0.04, 1)))
    check("fmt: brak danych i śmieci → myślnik", all(f(x) == "—" for x in (None, "x", float("nan"), float("inf"), True, [])))
    check("fmt: jednostka", f(85, 0, unit="%") == "85%")

    # render: wyrównanie
    rows = S.render(["", "a", "bb"], [["Długa etykieta", "1", "22"], ["K", "333", "4"]])
    check("render: równa szerokość wierszy z pierwszą kolumną do lewej", len({len(r) for r in rows}) <= 2 and rows[1].startswith("Długa etykieta") and "│" in rows[1], rows)
    check("render: wartości do prawej", rows[1].endswith("22") and rows[2].endswith("4") and rows[2].rstrip().endswith("4"), rows)
    check("render: pusty zestaw", S.render(["x"], []) == ["x"])
    check("render: wiersze o różnej liczbie kolumn", len(S.render(["", "a", "b"], [["x"], ["y", "1", "2", "3"]])) == 3)

    # dzień
    d = "\n".join(S.day_lines(T(4.82), T(3.10)))
    check("dzień: nagłówek dziś/wczoraj i bilans z znakiem", "dziś" in d and "wczoraj" in d and "+4,82" in d and "+3,10" in d, d)
    check("dzień: bateria ↑↓ i autokonsumpcja", "↑3,0 ↓2,5" in d and "60%" in d, d)
    d2 = "\n".join(S.day_lines(T(4.82), EMPTY))
    check("dzień: brak wczoraj → myślniki, bez wyjątku", "—" in d2 and "+4,82" in d2, d2)
    d3 = "\n".join(S.day_lines(T(1.0, pv=None, load=None, chg=None, dis=None, sc=None), None))
    check("dzień: brak PV/dom/bateria → myślniki; bez wiersza autokonsumpcji", d3.count("—") >= 6 and "Autokonsumpcja" not in d3, d3)
    check("dzień: wartości ujemne", "-2,50" in "\n".join(S.day_lines(T(-2.5), T(0.0))))

    # tydzień
    base = date(2026, 11, 14)
    days = [(date(2026, 11, 14 + i), T(1.0 + i * 0.5)) for i in range(7)]
    w = S.week_lines(days, prev_net=2.0)
    wt = "\n".join(w)
    check("tydzień: 7 wierszy dni + nagłówek + razem + poprzedni", len(w) == 1 + 7 + 1 + 1, len(w))
    check("tydzień: skróty dni tygodnia (14.11.2026 to sobota)", "So 14.11" in wt and "Nd 15.11" in wt and "Pt 20.11" in wt, wt)
    check("tydzień: ▲ przy najlepszym, ▼ przy najsłabszym", "Pt 20.11 ▲" in wt and "So 14.11 ▼" in wt, wt)
    check("tydzień: suma bilansu", "Razem" in wt and "+17,50" in wt, wt)
    check("tydzień: poprzedni tydzień", "Poprz. tydz." in wt and "+2,00" in wt)
    gaps = [(date(2026, 11, 14 + i), T(1.0) if i in (0, 3) else EMPTY) for i in range(7)]
    wg = "\n".join(S.week_lines(gaps, None))
    check("tydzień z dziurami: brakujące dni jako myślniki, suma tylko z dni z danymi", wg.count("—") >= 5 * 4 and "+2,00" in wg and "Poprz." not in wg, wg)
    one = "\n".join(S.week_lines([(date(2026, 11, 14), T(1.0))], None))
    check("tydzień z jednym dniem: bez ▲▼", "▲" not in one and "▼" not in one)
    tie = "\n".join(S.week_lines([(date(2026, 11, 14 + i), T(1.0)) for i in range(3)], None))
    check("tydzień z remisem: nie wywala (jeden ▲ i jeden ▼)", tie.count("▲") <= 1 and tie.count("▼") <= 1, tie)
    none = S.week_lines([(date(2026, 11, 14 + i), EMPTY) for i in range(7)], None)
    check("tydzień bez danych: tylko nagłówek i wiersze z myślnikami, bez „Razem”", not any(r.startswith("Razem") for r in none), none)
    check("tydzień: śmieci w danych dnia", len(S.week_lines([(date(2026, 11, 14), None), (date(2026, 11, 15), "x")], None)) == 3)

    # miesiąc
    cur = {"title": "Listopad 2026", "days_with_data": 30, "net": 120.5, "export_kwh": 300.0, "import_kwh": 80.0, "pv_kwh": 410.0, "load_kwh": 250.0,
           "self_consumption_pct": 70.0, "saving_estimate": 310.0}
    prv = dict(cur, title="Październik 2026", net=90.0, pv_kwh=300.0)
    m = "\n".join(S.month_lines(cur, prv))
    check("miesiąc: tytuły kolumn i wartości obok siebie", "Listopad 2026" in m and "Październik 2026" in m and "+120,50" in m and "+90,00" in m and "410" in m and "300" in m, m)
    check("miesiąc: oszczędność z gwiazdką", "Oszczędność zł*" in m and "310" in m)
    m2 = "\n".join(S.month_lines(cur, None))
    check("miesiąc bez poprzedniego: „poprzedni” i myślniki", "poprzedni" in m2 and "—" in m2, m2)
    m3 = "\n".join(S.month_lines({"title": None, "net": None}, {"days_with_data": 0}))
    check("miesiąc: śmieci nie wywalają", "Bilans" in m3, m3)

    # raport do powiadomienia
    rep = dict(cur, revenue=200.0, cost=79.5, days_in_month=30, best_day={"date": "2026-11-12", "net": 9.5}, worst_day=None)
    txt = R.report_table_text(rep, prv)
    check("raport: tytuł, tabela, porównanie, objaśnienie gwiazdki, najlepszy dzień", txt.startswith("Raport EMS — Listopad 2026") and "│" in txt and "Względem poprzedniego miesiąca: +30,50" in txt and "* oszczędność" in txt and "Najlepszy dzień: 2026-11-12 (+9,50 zł)" in txt, txt)
    part = R.report_table_text(dict(rep, days_with_data=10), None)
    check("raport: niepełny miesiąc oznaczony", "Uwaga: dane z 10 z 30 dni." in part, part)
    short = R.report_table_text(rep, prv)
    check("raport: nie dłuższy niż 16 wierszy", len(short.splitlines()) <= 16, len(short.splitlines()))


main()
print(f"SUMMTABLE PASS={common.PASS} FAIL={common.FAIL}")
