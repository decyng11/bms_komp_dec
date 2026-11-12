"""Plan sprzedaży vs faktyczny eksport w oknach sprzedaży: zapis planu, całkowanie, wpis w dzienniku następnego dnia."""
import asyncio, sys
import common
sys.path.insert(0, ".")
from common import *   # noqa
from datetime import datetime, timedelta, date
from custom_components.bms_komp_dec import automation


def sale(kwh, gross, net, day=0):
    return {"skip": False, "proposed": "18:00", "current": "00:00", "confidence": "high", "reason": "x",
            "sale_kwh": kwh, "sale_gross_pln": gross, "gain_pln": net, "sale_day": day}


async def main():
    hass, c, opt, rt = build()
    at(2026, 11, 12, 16)
    # --- zapis planu: wieczorne okno dziś + poranne jutro; ponowne odświeżenie nie kasuje dnia, zestawy osobno
    automation._store_sale_plan(rt, {"bateria_sprzedaz_start_2": sale(4.2, 3.36, 1.51, 0), "bateria_sprzedaz_start": sale(2.0, 1.4, 0.4, 1)})
    sp = rt.state["sale_plan"]
    d0, d1 = "2026-11-12", "2026-11-13"
    check("plan: dziś wieczorne okno", sp[d0]["kwh"] == 4.2 and sp[d0]["gross"] == 3.36 and sp[d0]["net"] == 1.51, sp.get(d0))
    check("plan: jutro poranne okno", sp[d1]["kwh"] == 2.0, sp.get(d1))
    automation._store_sale_plan(rt, {"bateria_sprzedaz_start": sale(1.5, 1.0, 0.3, 0)})     # kolejnego dnia „dziś” = poranne okno
    check("plan: zestawy sumują się, nie kasują siebie", sp[d0]["kwh"] == 5.7 and set(sp[d0]["sets"]) == {"bateria_sprzedaz_start_2", "bateria_sprzedaz_start"}, sp[d0])
    automation._store_sale_plan(rt, {"bateria_sprzedaz_start_2": {"skip": True}})
    check("plan: pominięte propozycje nic nie zmieniają", sp[d0]["kwh"] == 5.7)

    # --- całkowanie faktycznego eksportu tylko w trybie sprzedaży
    rt.grid_power = lambda: -3000.0
    rt.is_selling = lambda: True
    rt.sell_price = lambda: 0.5
    t0 = datetime(2026, 11, 12, 18, 0, 0, tzinfo=TZ)
    rt._sale_ts = None
    rt.state["sale_report_done"] = d0
    rt._track_sale(t0)
    for i in range(1, 361):                       # 1 h co 10 s
        rt._track_sale(t0 + timedelta(seconds=10 * i))
    act = rt.state["sale_actual"][d0]
    check("faktyczny eksport w oknie: ~3 kWh", abs(act["kwh"] - 3.0) < 0.02, act)
    check("faktyczny przychód: ~1,50 zł", abs(act["rev"] - 1.5) < 0.02, act)
    rt.is_selling = lambda: False
    before = act["kwh"]
    rt._track_sale(t0 + timedelta(hours=1, seconds=10)); rt._track_sale(t0 + timedelta(hours=1, seconds=20))
    check("poza sprzedażą nic nie dolicza", rt.state["sale_actual"][d0]["kwh"] == before)

    # --- podsumowanie dnia po północy trafia do dziennika
    n = len(rt.log.entries)
    rt._track_sale(datetime(2026, 11, 13, 0, 0, 5, tzinfo=t0.tzinfo))
    msgs = [e["msg"] for e in list(rt.log.entries)[n:]]
    check("po północy: wpis z planem i faktem", any("Sprzedaż 2026-11-12" in m and "plan ~5.7 kWh" in m and "3.0 kWh" in m for m in msgs), msgs)
    check("po północy: tylko jeden wpis na dobę", sum("Sprzedaż 2026-11-12" in m for m in msgs) == 1)
    rt._track_sale(datetime(2026, 11, 13, 0, 0, 15, tzinfo=t0.tzinfo))
    check("drugi tik tej samej doby nie dubluje wpisu", sum("Sprzedaż 2026-11-12" in e["msg"] for e in rt.log.entries) == 1)
    # plan, a sprzedaży nie było → ostrzeżenie
    rt.state["sale_plan"]["2026-11-13"] = {"kwh": 4.0, "gross": 3.0, "net": 1.0}
    n = len(rt.log.entries)
    rt._sale_report(date(2026, 11, 13))
    last = list(rt.log.entries)[-1]
    check("zaplanowano, a nie sprzedano: ostrzeżenie", last["level"] == "warn" and "Sprzedaż 2026-11-13" in last["msg"], last)
    print(f"SALEREPORT PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
