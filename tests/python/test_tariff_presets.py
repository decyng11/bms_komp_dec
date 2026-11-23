"""Gotowe taryfy w polu godzin szczytu: g12w, g12r, g13 (sezonowo)."""
import sys
from datetime import date, datetime
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec import tariff as T

fails = 0
def check(c, name):
    global fails
    print(("ok   " if c else "FAIL ") + name)
    if not c: fails += 1

w, s = date(2026, 11, 24), date(2026, 7, 15)
check(T.parse_peaks("g12r") == (((7, 13), (16, 22)), None), "g12r: 7–13 i 16–22")
check(T.parse_peaks("G12W") == (((6, 13), (15, 22)), None), "g12w (wielkość liter bez znaczenia)")
check(T.parse_peaks("g13", w) == (((7, 13), (16, 21)), None), "g13 zimą: 7–13 i 16–21")
check(T.parse_peaks("g13", s) == (((7, 13), (19, 22)), None), "g13 latem: 7–13 i 19–22")
check(T.parse_peaks("g13", date(2026, 3, 31))[0] == ((7, 13), (16, 21)) and T.parse_peaks("g13", date(2026, 4, 1))[0] == ((7, 13), (19, 22)), "granica sezonu 31.III / 1.IV")
check(T.parse_peaks("g13", date(2026, 9, 30))[0] == ((7, 13), (19, 22)) and T.parse_peaks("g13", date(2026, 10, 1))[0] == ((7, 13), (16, 21)), "granica sezonu 30.IX / 1.X")
check(T.parse_peaks("6-13,15-22")[0] == ((6, 13), (15, 22)) and T.parse_peaks("brak")[0] == (), "dotychczasowe formaty bez zmian")
check(T.parse_peaks("g14")[0] is None, "nieznane słowo: błąd")
p = T.TariffProfile(T.parse_peaks("g13", w)[0], True, True)
sat, mon = datetime(2026, 11, 28, 17, 0), datetime(2026, 11, 23, 17, 0)
check(not p.is_peak(sat) and p.is_peak(mon) and not p.is_peak(datetime(2026, 11, 23, 14, 0)), "G13: sobota tania, pn 17:00 szczyt, pn 14:00 tania dolina")
print("TARIFF PRESETS FAILS", fails)
raise SystemExit(1 if fails else 0)
