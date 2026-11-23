"""Oś decyzji planu (6/12/18), miara stabilności, zużycie baterii w zł."""
import sys
from datetime import date
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec import planstory as PS

fails = 0
def check(c, name):
    global fails
    print(("ok   " if c else "FAIL ") + name)
    if not c: fails += 1

G = (("ładowanie", "s1", "e1"),)
def props(s, e, skip=False): return {"s1": {"proposed": s, "skip": skip}, "e1": {"proposed": e}}
snaps = {}; d = date(2026, 11, 24)
check(PS.take(snaps, d, 5, props("02:00", "04:00"), G) is False, "przed 6:00: bez zapisu")
check(PS.take(snaps, d, 7, props("02:00", "04:00"), G) is True, "po 6:00: zapis")
check(PS.take(snaps, d, 8, props("03:00", "05:00"), G) is False, "ten sam slot: bez drugiego zapisu")
check(PS.take(snaps, d, 13, props("03:00", "05:00"), G) is True, "po 12:00: zapis")
check(PS.take(snaps, d, 19, props("03:00", "05:00", skip=True), G) is True, "po 18:00: zapis (pomijam)")
v = PS.view(snaps, d)
check(v["compared"] == 2 and v["changes"] == 2 and v["changed_pct"] == 100, f"zmiany liczone między slotami: {v['changes']}/{v['compared']}")
check("często" in v["text"], "opis: plan zmienia decyzje często")
check(PS.view({}, d)["changed_pct"] is None, "brak danych: bez wniosku")
old = {(date(2026, 11, 1)).isoformat(): {"6": {}}}
PS.take(old, d, 7, props("1:00", "2:00"), G)
check(len(old) <= PS.KEEP_DAYS and date(2026, 11, 1).isoformat() in old, "przycinanie starszych niż 14 dni działa tylko przy nadmiarze")
w = PS.wear_days({"2026-11-24": {"revenue": 5.0, "cost": 2.0}}, {"2026-11-24": {"dis": 10.0}}, d, 0.2)
check(w["days"][0]["wear_pln"] == 2.0 and w["days"][0]["net_after"] == 1.0, "zużycie: 10 kWh × 0,20 zł = 2 zł, po zużyciu 1 zł")
check(PS.wear_days({}, {}, d, 0.2)["days"] == [], "brak danych: pusto")
print("PLANSTORY FAILS", fails)
raise SystemExit(1 if fails else 0)
