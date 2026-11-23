"""Korekta dalszego dnia tylko gdy w teście „na przód” zmniejsza błąd; miara WAPE."""
import sys
from datetime import date, timedelta
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec import insights as I

fails = 0
def check(c, name):
    global fails
    print(("ok   " if c else "FAIL ") + name)
    if not c: fails += 1

ins = I.Insights.__new__(I.Insights)
ins.hass = None; ins.fc = {}; ins.hours = {}
today = date(2026, 11, 20)
import random
random.seed(3)
def fill(h, noisy):
    for i in range(1, 31):
        d = (today - timedelta(days=i)).isoformat()
        act = 5.0 + (i % 5)
        f = act * (0.6 if not noisy else random.choice([0.8, 1.25]))
        ins.fc.setdefault(d, {}).setdefault("pv_fc_by_h", {})[str(h)] = f
        ins.fc[d]["pv_act"] = act
        ins.fc[d]["pv_fc"] = f if h == 0 else ins.fc[d].get("pv_fc", f)
fill(0, False)
check(ins.pv_correction_helps(0, today, 30, "median") is True, "stały błąd ×0,6: korekta pomaga")
ins.fc = {}; random.seed(5); fill(2, True)
res = ins.pv_correction_helps(2, today, 30, "median")
check(res is False, f"losowy szum: korekta nie pomaga → {res}")
fac, n, med = ins.pv_horizon_factor(2, today)
check(fac == 1.0, f"dalszy dzień bez poprawy: współczynnik 1,0 (jest {fac})")
check(I._wape([(2.0, 1.0), (10.0, 10.0)]) == round(100 * 1 / 11, 1), "WAPE")
print("HORIZON GUARD FAILS", fails)
raise SystemExit(1 if fails else 0)
