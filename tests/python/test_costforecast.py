"""Prognoza kosztu dnia i miesiąca (costforecast.py)."""
import sys
from common import *   # noqa
import common
from datetime import date, timedelta
from custom_components.bms_komp_dec import costforecast as cf


def main():
    today = date(2026, 11, 10)
    led = {(today - timedelta(days=i)).isoformat(): {"revenue": 1.0, "cost": 6.0} for i in range(1, 10)}
    led[today.isoformat()] = {"revenue": 0.5, "cost": 2.5}                  # dziś dotąd 2 zł
    rows = [{"day": today.isoformat(), "cost": 1.0}] * 8 + [{"day": (today + timedelta(days=1)).isoformat(), "cost": 0.5}] * 24
    r = cf.forecast(led, rows, today)
    check("dziś: dotąd 2,00 + reszta planu 8,00 = 10,00", r["today"]["so_far"] == 2.0 and r["today"]["rest_plan"] == 8.0 and r["today"]["total"] == 10.0, r["today"])
    check("jutro z planu: 24 h × 0,50 = 12,00", r["tomorrow"]["plan"] == 12.0, r["tomorrow"])
    r2 = cf.forecast(led, rows[:8] + [{"day": (today + timedelta(days=1)).isoformat(), "cost": 0.5}] * 10, today)
    check("jutro: plan niepełny (10 h) → brak sumy", r2["tomorrow"]["plan"] is None and r2["tomorrow"]["plan_hours"] == 10, r2["tomorrow"])
    r3 = cf.forecast(led, [], today)
    check("bez planu: dziś bez sumy, dotąd nadal liczone", r3["today"]["total"] is None and r3["today"]["so_far"] == 2.0 and r3["tomorrow"]["plan"] is None, r3)
    r4 = cf.forecast({}, rows, today)
    check("pusta księga: dotąd 0, plan liczony", r4["today"]["so_far"] == 0.0 and r4["today"]["total"] == 8.0, r4["today"])
    check("zła księga/plan → bez błędu", cf.forecast(None, None, today)["today"]["total"] is None and cf.forecast({"x": 1}, [1, {"day": "x"}, {"day": today.isoformat(), "cost": "abc"}], today)["today"]["total"] is None)
    neg = [{"day": today.isoformat(), "cost": -2.0}] * 4
    check("zysk z planu: ujemny koszt", cf.forecast({today.isoformat(): {"revenue": 3.0, "cost": 1.0}}, neg, today)["today"]["total"] == -10.0)
    print(f"COSTFC PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)
main()
