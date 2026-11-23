"""Okna cenowe doby (pricewin.py) i ich użycie w powiadomieniu „plan na jutro”."""
import sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import pricewin as pw, tomorrowplan as tp


def main():
    day = [0.6] * 24
    for h in (12, 13):
        day[h] = 0.3
    for h in (18, 19, 20):
        day[h] = 1.5
    lo = pw.best_block(day, 2, True)
    check("najtańszy blok 2 h = 12–14, śr. 0,30", lo == {"start": 12, "end": 14, "avg": 0.3}, lo)
    hi = pw.best_block(day, 2, False)
    check("najdroższy blok 2 h = 18–20 (pierwszy z równych)", hi["start"] == 18 and hi["avg"] == 1.5, hi)
    check("blok 3 h najdroższy = 18–21", pw.best_block(day, 3, False)["start"] == 18)
    check("za mało cen → None", pw.best_block([0.5] * 10, 2) is None and pw.best_block(None, 2) is None)
    holes = list(day); holes[12] = None
    check("dziura w najtańszym bloku → blok obok, nie przez dziurę", pw.best_block(holes, 2, True)["start"] != 12)
    check("zły rozmiar bloku → None", pw.best_block(day, 0) is None and pw.best_block(day, 25) is None)
    neg = list(day)
    for h in (11, 12, 13, 16):
        neg[h] = -0.05
    check("godziny ujemne", pw.negative_hours(neg) == [11, 12, 13, 16], pw.negative_hours(neg))
    check("zapis przedziałów", pw.spans([11, 12, 13, 16]) == "11–14, 16–17" and pw.spans([]) == "", pw.spans([11, 12, 13, 16]))
    check("brak ujemnych", pw.negative_hours(day) == [] and pw.negative_hours(None) == [])
    t = pw.windows_text(day)
    check("zdanie o oknach", t and "Najtaniej 12–14" in t and "0,30" in t and "najdrożej 18–20" in t and "1,50" in t, t)
    msg = tp.message({"charges": [], "sales": [], "windows": t})
    check("plan na jutro: zawiera okna cenowe", "Najtaniej 12–14" in msg and "pralkę" in msg, msg)
    check("plan na jutro bez okien: bez zmian", "Najtaniej" not in tp.message({"charges": [], "sales": []}))
    print(f"PRICEWIN PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)
main()
