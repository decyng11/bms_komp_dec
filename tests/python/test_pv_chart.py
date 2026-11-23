"""Wykres produkcji PV z historią: doba wstecz (rzeczywista + poranna prognoza), jutro (prognoza planera), zakres dni."""
import asyncio, sys
from datetime import date, timedelta
from common import *   # noqa
import common

def run():
    at(2026, 11, 23, 14, 5)
    hass, c, opt, rt = build()
    today = date(2026, 11, 23)
    y = today - timedelta(days=1)
    for h in range(24):
        b = [0.0] * 11
        b[1] = round(max(0.0, 0.8 - abs(h - 12) * 0.15), 3)     # PV
        rt.insights.hours[f"{y.isoformat()}T{h:02d}"] = b
    rt.insights.fc[y.isoformat()] = {"pv_fc": 6.0, "pv_fc_h": [round(max(0.0, 1.0 - abs(h - 12) * 0.2), 3) for h in range(24)]}
    for i in range(2, 8):
        d = today - timedelta(days=i)
        rt.insights.fc[d.isoformat()] = {"pv_fc": 5.0, "pv_act": 3.0 if i % 2 else 4.0}
    r = rt.pv_chart("day", y.isoformat())
    check("wczoraj: 24 godziny rzeczywiste i prognoza", r["kind"] == "past" and len(r["actual"]) == 24 and len(r["forecast"]) == 24, r)
    check("wczoraj: sumy zgodne z danymi", abs(r["sum_act"] - sum(r["actual"])) < 0.01 and r["sum_fc"] > 0)
    r2 = rt.pv_chart("day", (today - timedelta(days=30)).isoformat())
    check("dzień bez zapisów: brak wykresu i wyjaśnienie", r2["actual"] is None and r2["forecast"] is None and r2["note"], r2)
    r3 = rt.pv_chart("day", (today - timedelta(days=200)).isoformat())
    check("zbyt dawno: komunikat o zakresie", r3["actual"] is None and "62 dni" in r3["note"], r3)
    r4 = rt.pv_chart("day", (today + timedelta(days=5)).isoformat())
    check("za daleko w przyszłość: komunikat", r4["actual"] is None and r4["note"], r4)
    rt.optimizer._read_pv_hourly = lambda off=0, fallback=False: [0.0] * 8 + [0.5] * 6 + [0.0] * 10
    r5 = rt.pv_chart("day", (today + timedelta(days=1)).isoformat())
    check("jutro: tylko prognoza z planera", r5["kind"] == "future" and r5["actual"] is None and r5["forecast"][9] == 0.5 and abs(r5["sum_fc"] - 3.0) < 1e-6, r5)
    g = rt.pv_chart("range", None, 7)
    check("zakres 7 dni: 7 wierszy, sumy i błąd prognozy", len(g["rows"]) == 7 and g["sum_fc"] > 0 and g["sum_act"] > 0 and g["err_pct"] is not None, g)
    check("zakres: ostatni wiersz = wczoraj", g["rows"][-1]["date"] == y.isoformat(), g["rows"][-1])
    check("zakres: wczoraj bez pv_act liczy sumę z godzin", g["rows"][-1]["pv_act"] and g["rows"][-1]["pv_act"] > 3, g["rows"][-1])
    check("zakres: 1000 dni jest przycięte do 90", len(rt.pv_chart("range", None, 1000)["rows"]) == 90)
    check("zła data nie wywala", rt.pv_chart("day", "xx")["kind"] == "today")
    print(f"PV-CHART PASS={common.PASS} FAIL={common.FAIL}")
run()
sys.exit(1 if common.FAIL else 0)
