"""Czy większa bateria się opłaca (analysis.battery_size)."""
import sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import analysis, insights as ins


def day(pv_kwh_noon=12.0, load=0.5):
    """24 koszyki: PV 8–15, stałe zużycie, ceny 1,0 zakup / 0,2 sprzedaż; bateria ma co ładować z nadwyżki PV."""
    out = []
    for h in range(24):
        pv = pv_kwh_noon / 8 if 8 <= h < 16 else 0.0
        out.append([load, pv, 0, 0, 0, 0, 1.0 * 3600, 3600, 0.2 * 3600, 3600, 50.0])
    return out


def main():
    bk = {f"2026-11-{d:02d}": day() for d in range(1, 11)}
    params = {"cap": 5.0, "eff": 0.9, "floor": 10.0, "max_chg_kw": 5.0, "max_dis_kw": 5.0}
    r = analysis.battery_size(bk, params, {}, ins.day_costs)
    check("wynik dla 10 dób, dwa warianty", r and r["days"] == 10 and len(r["rows"]) == 2 and r["cap_kwh"] == 5.0, r)
    s5, s10 = r["rows"][0]["saving_year"], r["rows"][1]["saving_year"]
    check("większa bateria = więcej oszczędności, malejące przyrosty", s5 > 0 and s10 >= s5 and (s10 - s5) <= s5 * 1.01, (s5, s10))
    # 12 kWh PV − 4 kWh zużycia (8 h × 0,5) − 4 kWh wieczorem… nadwyżka jest, więc pojemność 5 → 10 zwiększa autokonsumpcję
    check("brak ceny kWh → brak zwrotu", "payback_years" not in r["rows"][0])
    r2 = analysis.battery_size(bk, params, {"batt_zl_kwh": 1500}, ins.day_costs)
    pb = r2["rows"][0].get("payback_years")
    check("zwrot = cena × kWh / oszczędność roczna", pb is not None and abs(pb - 1500 * 5 / r2["rows"][0]["saving_year"]) < 0.06, r2["rows"][0])
    check("ekstrapolacja zaznaczona (10 dób < roku)", r["extrapolated"] is True and "sezonowość" in r["note"], r["note"])
    check("za mało dób → None", analysis.battery_size({k: bk[k] for k in list(bk)[:3]}, params, {}, ins.day_costs) is None)
    check("zła pojemność → None", analysis.battery_size(bk, {"cap": 0}, {}, ins.day_costs) is None and analysis.battery_size(bk, {"cap": "x"}, {}, ins.day_costs) is None)
    full = {k: v for k, v in bk.items()}
    full["2026-11-11"] = [None] * 24
    check("dzień bez danych pomijany", analysis.battery_size(full, params, {}, ins.day_costs)["days"] == 10)
    check("cfg: cena za kWh przechodzi walidację, śmieci nie", analysis.clean_cfg({"batt_zl_kwh": 1800})["batt_zl_kwh"] == 1800 and "batt_zl_kwh" not in analysis.clean_cfg({"batt_zl_kwh": 1e9}))
    # bateria już większa niż nadwyżka PV: dalsze powiększanie nic nie daje
    r3 = analysis.battery_size(bk, dict(params, cap=40.0), {}, ins.day_costs)
    check("ogromna bateria: przyrost ≈ 0", r3 and abs(r3["rows"][0]["saving_year"]) < 1.0, r3 and r3["rows"])
    print(f"BATTSIZE PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)
main()
