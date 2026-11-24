"""Porównanie rok do roku (yoy.py)."""
import asyncio
from datetime import date, timedelta
from common import *   # noqa
import common
from custom_components.bms_komp_dec import yoy as Y


def days(start, n, rev, cost, imp=5.0, exp=3.0):
    return {(start + timedelta(days=i)).isoformat(): {"revenue": rev, "cost": cost, "import_kwh": imp, "export_kwh": exp} for i in range(n)}


today = date(2026, 11, 24)
# brak danych sprzed roku
d = days(today - timedelta(days=60), 61, 1.0, 2.0)
r = Y.compare(d, today)
check("brak danych sprzed roku → niedostępne z opisem", r["available"] is False and "Za mało danych" in r["note"] and r["ready_from"], r)
check("data gotowości = pierwszy dzień + rok + 15 dni", r["ready_from"] == (today - timedelta(days=60) + timedelta(days=365 + 15)).isoformat(), r["ready_from"])
# pełne dane
d = {**days(today - timedelta(days=29), 30, 2.0, 1.0), **days(today - timedelta(days=29 + 365), 30, 1.0, 3.0, imp=8.0, exp=1.0)}
r = Y.compare(d, today)
check("dwa pełne okresy → dostępne", r["available"] and r["cur_days"] == 30 and r["prev_days"] == 30, r)
check("sumy: saldo teraz 30, rok temu −60", r["cur"]["net"] == 30.0 and r["prev"]["net"] == -60.0, (r["cur"], r["prev"]))
check("różnica salda +90 zł", r["diff"]["net"] == 90.0, r["diff"])
check("procent: pobór z sieci spadł o 37,5%", r["pct"]["import_kwh"] == -37.5, r["pct"])
# częściowe dane rok temu (>= 15 dni) działają z uwagą w opisie
d = {**days(today - timedelta(days=29), 30, 2.0, 1.0), **days(today - timedelta(days=29 + 365), 16, 1.0, 1.0)}
r = Y.compare(d, today)
check("16 dni sprzed roku → dostępne, opis wspomina o brakach", r["available"] and "16/30" in r["note"], r["note"])
# pusta księga
r = Y.compare({}, today)
check("pusta księga nie wywala", r["available"] is False)
print(f"YOY PASS={common.PASS} FAIL={common.FAIL}")
