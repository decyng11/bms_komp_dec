"""Tabela „Wczoraj” z rzeczywistych koszyków Insights."""
import sys
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import planview as PV

fails = 0
def check(c, name):
    global fails
    print(("ok   " if c else "FAIL ") + name)
    if not c: fails += 1

b = [None] * 24
b[2] = [1.0, 0, 1.5, 0, 1.2, 0, 0.6, 1, 0, 0, 50.0]
b[12] = [0.5, 2.0, 0, 1.2, 0, 0, 0, 0, 1.0, 1, 60.0]
r = PV.yesterday_rows(b, "2026-11-27")
check(len(r["rows"]) == 2, "tylko godziny z danymi")
check(r["rows"][0]["action"] == "grid" and r["rows"][0]["buy"] == 0.6, "ładowanie z sieci rozpoznane")
check(abs(r["rows"][0]["cost"] - 0.9) < 1e-6 and r["rows"][1]["cost"] < 0, "koszt i przychód godziny")
check(PV.yesterday_rows(None, "x") == {"rows": [], "totals": None}, "brak danych = pusta tabela")
print(f"WCZORAJ PASS FAIL={fails}")
sys.exit(1 if fails else 0)
