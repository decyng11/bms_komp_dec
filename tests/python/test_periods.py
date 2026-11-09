"""0.9.3: księga rozliczeń — tydzień (od poniedziałku), poprzedni miesiąc (też przez styczeń), rok."""
import sys
from common import *   # noqa
import common
from datetime import date
from custom_components.bms_komp_dec import ledger as ldg, money

def day(rev, cost): return {"export_kwh": 1.0, "import_kwh": 1.0, "revenue": rev, "cost": cost, "neg_export_kwh": 0.0, "peak_import_kwh": 0.0}
L = ldg.Ledger(stubs.FakeHass())
L.days = {"2025-12-30": day(5, 1), "2026-01-15": day(2, 1),
          "2026-10-31": day(7, 2), "2026-11-01": day(1, 1), "2026-11-02": day(2, 1),   # niedziela, poniedziałek
          "2026-11-08": day(3, 1), "2026-11-09": day(4, 1)}
d = date(2026, 11, 9)   # poniedziałek
w = L.sums(d, "week")
check("tydzień od poniedziałku: tylko 9.11", abs(w["revenue"] - 4) < 1e-6, w)
w2 = L.sums(date(2026, 11, 11), "week")
check("w środę: od poniedziałku 9.11 (bez 8.11)", abs(w2["revenue"] - 4) < 1e-6, w2)
check("tydzień kończący niedzielą 8.11: od 2.11", abs(L.sums(date(2026, 11, 8), "week")["revenue"] - (2 + 3)) < 1e-6)
pm = L.sums(d, "prev_month")
check("poprzedni miesiąc = październik", abs(pm["revenue"] - 7) < 1e-6, pm)
check("poprzedni miesiąc w styczniu = grudzień", abs(L.sums(date(2026, 1, 20), "prev_month")["revenue"] - 5) < 1e-6)
yr = L.sums(d, "year")
check("rok bieżący (bez grudnia 2025)", abs(yr["revenue"] - (2 + 7 + 1 + 2 + 3 + 4)) < 1e-6, yr)
check("miesiąc bez zmian", abs(L.sums(d, "month")["revenue"] - 10) < 1e-6)
check("razem bez zmian", abs(L.sums(d, "total")["revenue"] - 24) < 1e-6)
# szacunki (money): te same zakresy
class St: pass
stt = St(); stt.days = {k: {"load": 10.0, "imp": 1.0, "exp": 1.0, "pv": 0, "chg": 0, "dis": 0} for k in L.days}
b = money.bundle(L, stt, d)
check("bundle ma wszystkie okresy", set(b) == {"day", "week", "month", "prev_month", "year", "total"}, list(b))
check("szacunek: tydzień liczy 1 dzień zużycia (10 kWh)", b["week"]["savings"]["load_kwh"] == 10.0, b["week"]["savings"])
check("szacunek: poprzedni miesiąc = 1 dzień (31.10)", b["prev_month"]["savings"]["load_kwh"] == 10.0, b["prev_month"]["savings"])
check("szacunek: rok = 6 dni", b["year"]["savings"]["load_kwh"] == 60.0, b["year"]["savings"])
print(f"PERIODS PASS={common.PASS} FAIL={common.FAIL}"); sys.exit(1 if common.FAIL else 0)
