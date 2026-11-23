"""Stabilizacja planu: zamrożenie, potwierdzenie, duża poprawa, force."""
import sys
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec import planhold as ph

fails = 0
def check(c, name):
    global fails
    print(("ok   " if c else "FAIL ") + name)
    if not c: fails += 1

def plan(s, e, gain=1.0, skip=False):
    f = lambda t, g: {"proposed": t, "skip": skip, "label": "Ładowanie 1", "gain_pln": g}
    return {"proposals": {"start_grid_charge": f(s, gain), "stop_grid_charge": f(e, gain)}}

def got(p): return p["proposals"]["start_grid_charge"]["proposed"], p["proposals"]["stop_grid_charge"]["proposed"]

# zamrożenie: okno za 1 h nie zmienia godzin
hold = {}; n = plan("05:00", "06:00")
notes = ph.stabilize(plan("04:00", "05:00"), n, hold, 3 * 60)
check(got(n) == ("04:00", "05:00") and any("nie zmieniam" in x for x in notes), "zamrożenie okna za <2 h")
n = plan("05:00", "06:00"); notes2 = ph.stabilize(plan("04:00", "05:00"), n, hold, 3 * 60 + 15)
check(got(n) == ("04:00", "05:00") and not notes2, "zamrożenie: bez powtórek w dzienniku")
# potwierdzenie 2x
hold = {}; prev = plan("14:00", "15:00"); n = plan("15:00", "16:00")
ph.stabilize(prev, n, hold, 8 * 60)
check(got(n) == ("14:00", "15:00"), "1. przeliczenie: stare godziny")
n = plan("15:00", "16:00"); notes = ph.stabilize(prev, n, hold, 8 * 60 + 15)
check(got(n) == ("15:00", "16:00") and any("zmienione" in x for x in notes), "2. przeliczenie: nowe godziny + wpis")
# inny kandydat zeruje licznik
hold = {}; n = plan("15:00", "16:00"); ph.stabilize(prev, n, hold, 8 * 60)
n = plan("16:00", "17:00"); ph.stabilize(prev, n, hold, 8 * 60 + 15)
check(got(n) == ("14:00", "15:00"), "inny kandydat: licznik od nowa")
# duża poprawa od razu
hold = {}; n = plan("15:00", "16:00", gain=2.5); notes = ph.stabilize(plan("14:00", "15:00", gain=1.0), n, hold, 8 * 60)
check(got(n) == ("15:00", "16:00"), "zysk +1,5 zł: od razu")
# skip przechodzi, force przechodzi
n = plan("15:00", "16:00", skip=True); ph.stabilize(prev, n, {}, 8 * 60)
check(n["proposals"]["start_grid_charge"]["skip"] is True, "pominięcie okna bez zwłoki")
n = plan("15:00", "16:00"); ph.stabilize(prev, n, {}, 8 * 60, force=True)
check(got(n) == ("15:00", "16:00"), "force: bez stabilizacji")
n = plan("15:00", "16:00"); ph.stabilize(None, n, {}, 8 * 60)
check(got(n) == ("15:00", "16:00"), "brak poprzedniego planu")
print("PLANHOLD FAILS", fails)
raise SystemExit(1 if fails else 0)
