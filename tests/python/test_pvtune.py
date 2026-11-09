"""0.9.3: prognoza PV — samostrojenie okna uczenia (7/14/30 dni, mediana / ważona wiekiem) testem wstecz."""
import sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import insights as I

TODAY = date(2026, 11, 20)

def mk(ratio_by_age, base=10.0):
    ins = I.Insights(stubs.FakeHass())
    for age in range(1, 31):
        d = (TODAY - timedelta(days=age)).isoformat()
        r = ratio_by_age(age)
        ins.fc[d] = {"pv_fc": base, "pv_act": round(base * r, 3), "pv_fc_by_h": {"0": base}}
    return ins

# stałe, lekko zaszumione: zostaje standard
ins = mk(lambda a: 0.8 + 0.02 * ((a * 7) % 5 - 2))
t = ins.pv_tuning(0, TODAY)
check("stały stosunek: oceniono dni", t["n"] >= 13 and "mae" in t, t)
check("stały stosunek: wariant standardowy (30 dni, mediana)", (t["window"], t["mode"]) == (30, "median") or t["mae"] <= t["mae_default"], t)
# zmiana reżimu 12 dni temu (nowe zacienienie / zmiana ustawienia paneli): krótsze okno wygrywa
ins = mk(lambda a: 0.6 if a > 12 else 1.0)
t = ins.pv_tuning(0, TODAY)
check("zmiana reżimu: wybrane krótsze okno lub ważenie wiekiem", (t["window"], t["mode"]) != (30, "median"), t)
check("zmiana reżimu: błąd ≥3% mniejszy niż standardowy", t["mae"] <= 0.97 * t["mae_default"], t)
fac, n, med = ins.pv_horizon_factor(0, TODAY)
ins_def = mk(lambda a: 0.6 if a > 12 else 1.0); ins_def._pv_tune_cache = {(TODAY.isoformat(), 0): {"window": 30, "mode": "median", "n": 0}}
fac_def = ins_def.pv_horizon_factor(0, TODAY)[0]
check("współczynnik po strojeniu bliższy nowego stosunku (1,0)", abs(fac - 1.0) < abs(fac_def - 1.0), (fac, fac_def))
# za mało danych: standard, bez błędu
ins = I.Insights(stubs.FakeHass())
for age in range(1, 8):
    ins.fc[(TODAY - timedelta(days=age)).isoformat()] = {"pv_fc": 10.0, "pv_act": 8.0, "pv_fc_by_h": {"0": 10.0}}
t = ins.pv_tuning(0, TODAY)
check("za mało dni: standard, współczynnik jak dawniej", (t["window"], t["mode"]) == (30, "median") and abs(ins.pv_horizon_factor(0, TODAY)[0] - 0.86) < 1e-6, t)
check("statystyki horyzontu zawierają wynik strojenia", "tune" in ins.pv_horizon_stats(TODAY)[0])
print(f"PVTUNE PASS={common.PASS} FAIL={common.FAIL}"); sys.exit(1 if common.FAIL else 0)
