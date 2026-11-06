"""Test losowy planera: dziwne dane wejściowe nie mogą powodować wyjątków ani wyników, których przeglądarka nie przeczyta (NaN/inf)."""
import asyncio, sys, json, math, random, traceback
sys.path.insert(0, ".")
from common import *   # noqa
import common

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 1
N = int(sys.argv[2]) if len(sys.argv) > 2 else 300
R = random.Random(SEED)
NAN, INF = float("nan"), float("inf")

def pick(*xs): return R.choice(xs)
def rnd_series(kind):
    if kind == "zero": return lambda h: 0.0
    if kind == "day": return lambda h: 0.6 if 9 <= h < 15 else 0.0
    if kind == "big": return lambda h: 50.0 if 8 <= h < 16 else 0.0
    if kind == "neg": return lambda h: -0.5 if 9 <= h < 15 else 0.0
    if kind == "none": return lambda h: None
    if kind == "nan": return lambda h: NAN if h % 3 == 0 else 0.4
    if kind == "str": return lambda h: "x" if h % 5 == 0 else 0.4
    if kind == "inf": return lambda h: INF if h == 12 else 0.2
    return lambda h: round(R.random() * 1.5, 2)

def bad_json(x, path="res"):
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)): return path
    if isinstance(x, dict):
        for k, v in x.items():
            r = bad_json(v, f"{path}.{k}")
            if r: return r
    if isinstance(x, (list, tuple)):
        for i, v in enumerate(x):
            r = bad_json(v, f"{path}[{i}]")
            if r: return r
    return None

async def one(i):
    now = pick((2026, 11, 3, R.randrange(24), R.randrange(60)), (2026, 10, 25, R.randrange(24), R.randrange(60)),
               (2027, 3, 28, R.randrange(24), R.randrange(60)), (2026, 12, 31, 23, 59), (2027, 1, 1, 0, 0), (2026, 6, 21, 12, 0))
    soc = pick(0, 1, 5, 24.9, 25, 50, 99.9, 100, "unavailable", "unknown", "abc", -5, 150, R.random() * 100)
    shutdown = pick(None, 0, 10, 25, 50, 100, "unavailable", "abc")
    load = pick(0, 0.01, 3, 8, 20, 100, -4, None, "abc", R.random() * 15)
    pvk = pick("zero", "day", "big", "neg", "none", "nan", "str", "inf", "rand")
    prices = pick((1.29, 0.92), (0.0, 0.0), (-1, 2), (0.5, 0.5), (5.0, 0.1))
    progs = None
    if R.random() < 0.7:
        progs = [(pick("00:00", "05:00", "06:00", "13:00", "22:00", "25:99", "abc", "", None, "23:59"), pick(0, 25, 50, 100, -1, 200, "x"),
                  pick("Disabled", "Allow Grid", "Allow Gen", "weird", None)) for _ in range(6)]
    cap = pick(None, 0, -3, 5.0, 15.0, 300.0, "abc")
    try:
        hass, c, sched = await mk(now, soc if soc is not None else 50, shutdown=shutdown, progs=progs, pvt=rnd_series(pvk),
                                  load=load, prices=prices, tou=pick("Week", "Disabled", "Mon", "x"))
        if cap is not None: sched.config[const.CONF_BATTERY_CAPACITY_KWH] = cap
        # losowe uszkodzenie cen RCE
        if R.random() < 0.6:
            d0 = date(*now[:3]); d1 = d0 + timedelta(days=1)
            def price(h):
                return pick(250, 700, 450, None, NAN, -300, "x", 1e9, 0)
            hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": [dict(x, rce_pln=price(h)) for h, x in enumerate(arr(d0, lambda h: 1) + arr(d1, lambda h: 1))][: R.randrange(0, 49)]})
        res = await sched.suggest()
    except Exception as e:  # noqa: BLE001
        tb = traceback.format_exc().strip().splitlines()[-3:]
        return f"WYJĄTEK {type(e).__name__}: {e} | now={now} soc={soc!r} sd={shutdown!r} load={load!r} pv={pvk} cap={cap!r} progs={'tak' if progs else 'nie'} :: {' / '.join(tb)}"
    if not isinstance(res, dict): return f"wynik nie jest dict: {type(res)} now={now}"
    bj = bad_json(res)
    if bj: return f"NaN/inf w wyniku: {bj} | now={now} soc={soc!r} load={load!r} pv={pvk} cap={cap!r}"
    try: json.dumps(res, allow_nan=False)
    except Exception as e: return f"wynik nie serializuje się do JSON: {e} | now={now} soc={soc!r} pv={pvk}"
    cur = res.get("curve")
    if cur:
        ln = {k: len(v) for k, v in cur.items() if isinstance(v, list)}
        if len(set(ln.values())) > 1: return f"krzywa: różne długości {ln} | now={now}"
        for v in cur.get("soc", []):
            if isinstance(v, (int, float)) and not (-0.01 <= v <= 100.01): return f"krzywa: SOC poza 0–100: {v} | now={now} soc={soc!r} cap={cap!r} load={load!r}"
    return None

async def main():
    bad = []
    for i in range(N):
        r = await one(i)
        if r: bad.append(r)
    kinds = {}
    for b in bad: kinds.setdefault(b.split(" |")[0].split(":")[0][:40], []).append(b)
    for k, v in kinds.items():
        print(f"[{len(v)}x] {k}\n    np. {v[0][:420]}")
    print(f"FUZZ seed={SEED} n={N} problemy={len(bad)}")
asyncio.run(main())
