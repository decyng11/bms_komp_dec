"""Automatyczne stawki do porównania taryf (strefowa, narzut dynamicznej) z własnych danych."""
import sys
from datetime import date, timedelta
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec import analysis as A

def bucket(buy, sell, imp=1.0):
    # indeksy jak w analysis: IMP, BUY_S/BUY_T, SELL_S/SELL_T
    b = [0.0] * 20
    b[A._IMP] = imp; b[A._BUY_T] = 3600.0; b[A._BUY_S] = buy * 3600.0; b[A._SELL_T] = 3600.0; b[A._SELL_S] = sell * 3600.0
    return b

days = {}
for i in range(1, 8):
    d = date(2026, 11, 2) + timedelta(days=i)          # wt–pn (dni robocze nie wszystkie, ale większość)
    days[d.isoformat()] = [bucket(1.29 if (6 <= h < 13 or 15 <= h < 22) else 0.62, 0.30) for h in range(24)]
a = A.auto_cfg(days, "6-13,15-22")
check("strefowa: szczyt ≈ 1,29", a.get("zone") and abs(a["zone"]["peak"] - 1.29) < 1e-6, a)
check("strefowa: poza ≈ 0,62", a.get("zone") and abs(a["zone"]["off"] - 0.62) < 1e-6, a)
check("narzut dynamicznej = mediana(zakup − sprzedaż)", "dyn_markup" in a and 0.3 < a["dyn_markup"] < 1.1, a)
check("za mało danych: brak pól", A.auto_cfg({}, "6-13,15-22") == {})
flat = {k: [bucket(0.8, 0.3) for _ in range(24)] for k in list(days)}
check("płaska cena: brak stawki strefowej", "zone" not in A.auto_cfg(flat, "6-13,15-22"))
check("złe okna: bez błędu", isinstance(A.auto_cfg(days, "xx"), dict))
print(f"AUTOCFG PASS={common.PASS} FAIL={common.FAIL}")
sys.exit(1 if common.FAIL else 0)
