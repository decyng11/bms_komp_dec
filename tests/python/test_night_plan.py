"""Plan nocny: bateria nie może dojść do progu falownika przed szczytem porannym tylko dlatego, że noc nie została wliczona."""
import asyncio, sys
sys.path.insert(0, ".")
from common import *   # noqa
import common

PROGS = [("00:00", 25, "Allow Grid"), ("05:00", 25, "Allow Grid"), ("06:00", 25, "Disabled"), ("13:00", 25, "Disabled"), ("15:00", 25, "Disabled"), ("22:00", 25, "Allow Grid")]

async def plan(now, soc, load, pvpeak, cap=15.0, floor=25):
    pvt = lambda h: pvpeak if 9 <= h < 15 else (pvpeak * 0.4 if h in (8, 15) else 0.0)
    hass, c, sched = await mk(now, soc, shutdown=floor, load=load, pvt=pvt, progs=PROGS)
    sched.config[const.CONF_BATTERY_CAPACITY_KWH] = cap
    res = await sched.suggest()
    return res

def soc_at(res, hour_abs_from_midnight_today):
    cur = res["curve"]; h0 = int(cur["start"][11:13]) if cur["start"][:10] == res["_day"] else int(cur["start"][11:13])
    i = hour_abs_from_midnight_today - h0
    return cur["soc"][i] if 0 <= i < len(cur["soc"]) else None

async def main():
    # --- dokładnie scenariusze, które planer dawniej pomijał mimo, że krzywa schodziła do progu
    for soc, load in ((45, 10), (60, 14), (50, 12)):
        res = await plan((2026, 11, 3, 21, 22), soc, load, 0.9)
        P = res["proposals"]["start_grid_charge"]
        check(f"SOC {soc}%, {load} kWh/d o 21:22: planer proponuje ładowanie (dawniej pomijał)", not P["skip"] and P["proposed"], P["reason"])
    # --- niezmiennik: o 6:00 (start szczytu) SOC > próg + 5 pp, dla wielu kombinacji i pór
    worst = 100.0; n = 0; bad = []
    for now in ((2026, 11, 3, 21, 22), (2026, 11, 3, 22, 30), (2026, 11, 3, 23, 40), (2026, 11, 4, 1, 30), (2026, 11, 4, 3, 10)):
        for soc in (28, 35, 45, 55, 65, 80):
            for load in (8, 12, 16):
                res = await plan(now, soc, load, 0.9)
                cur = res["curve"]; h0 = int(cur["start"][11:13]); day0 = int(cur["start"][8:10])
                six = (4 - day0) * 24 + 6 if day0 == 3 else 6      # 06:00 dnia 4.11 liczone od północy dnia startu krzywej
                i = (24 + 6 if day0 == 3 else 6) - h0
                if not (0 <= i < len(cur["soc"])): continue
                v = cur["soc"][i]; n += 1
                if v < 25 + 5 and soc >= 28: bad.append((now[3:], soc, load, round(v, 1)))
                worst = min(worst, v)
    check(f"niezmiennik: o 6:00 SOC > próg+5 pp we wszystkich {n} scenariuszach", not bad, bad[:6])
    print("   najniższy SOC o 6:00 w siatce scenariuszy:", round(worst, 1))
    # --- wysoki SOC i małe zużycie: ładowanie niepotrzebne, a powód mówi o stanie po nocy
    res = await plan((2026, 11, 3, 21, 22), 95, 6, 0.9)
    P = res["proposals"]["start_grid_charge"]
    check("SOC 95%, 6 kWh/d: pomija ładowanie", P["skip"], P["reason"])
    check("powód pominięcia podaje SOC po nocy bez ładowania", "bez ładowania" in P["reason"] and "o 06:00" in P["reason"], P["reason"])
    print(f"NIGHT PASS={common.PASS} FAIL={common.FAIL}")
asyncio.run(main())
