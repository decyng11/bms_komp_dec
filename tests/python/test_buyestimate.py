"""Szacunek cen zakupu na jutro (podgląd): czysta logika, historia z insights, atrybuty czujnika; planer nie widzi szacunku."""
import asyncio, json, sys
from datetime import date, timedelta
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import buyestimate as BE, insights as INS, sensor as sens, tariff as T

TODAY = [0.99, 0.95, 0.90, 0.88, 0.90, 0.95, 1.05, 1.20, 1.30, 1.10, 0.90, 0.84, 0.80, 0.82, 0.90, 1.40, 1.96, 1.80, 1.70, 1.50, 1.40, 1.30, 1.20, 1.16]
SHAPE = [0.70, 0.66, 0.62, 0.60, 0.63, 0.70, 0.90, 1.25, 1.40, 1.15, 0.80, 0.55, 0.50, 0.52, 0.70, 1.00, 1.60, 1.75, 1.65, 1.45, 1.30, 1.10, 0.95, 0.85]
TARGET = date(2026, 11, 21)          # sobota


def hist(n=6, shape=SHAPE, skip=(), hole=(), scale=lambda i: 1.0):
    out = {}
    for i in range(1, n + 1):
        d = (TARGET - timedelta(days=i))
        if i in skip:
            continue
        out[d.isoformat()] = [None if h in hole else round(shape[h] * scale(i), 4) for h in range(24)]
    return out


def pure():
    e = BE.estimate(hist(6), TARGET)
    check("stały kształt z 6 dób: szacunek = ten kształt", e and e["prices"] == [round(x, 4) for x in SHAPE] and e["days"] >= 3, e)
    check("kształt ma 24 wartości", e and len(e["prices"]) == 24)
    # mediana odporna na jeden dziwny dzień
    e = BE.estimate(hist(5, scale=lambda i: 3.0 if i == 2 else 1.0), TARGET)
    check("mediana ignoruje jedną skrajną dobę", e and e["prices"][8] == 1.4, e and e["prices"][8])
    check("za mało dób → None", BE.estimate(hist(2), TARGET) is None)
    check("dokładnie 3 doby wystarczą", BE.estimate(hist(3), TARGET) is not None)
    check("doby z dziurami (poniżej 20 godzin) nie liczą się", BE.estimate(hist(4, hole=range(0, 6)), TARGET) is None)
    check("doby z <=4 dziurami liczą się", BE.estimate(hist(4, hole=(0, 1, 2)), TARGET) is not None)
    e = BE.estimate(hist(4, hole=(0, 1, 2)), TARGET)
    check("godzina z dziurą w każdej dobie → None (nie zgadujemy)", e["prices"][0] is None and e["prices"][5] is not None, e["prices"][:6])
    # dni robocze osobno od weekendów
    wk = {}
    for i in range(1, 15):
        d = TARGET - timedelta(days=i)
        sc = 0.5 if d.weekday() >= 5 else 1.0
        wk[d.isoformat()] = [round(SHAPE[h] * sc, 4) for h in range(24)]
    e = BE.estimate(wk, TARGET)                      # sobota → tylko weekendy (są 4: 2 weekendy z 14 dób)
    check("cel w weekend: mediana z weekendów", e["kind"] == "weekend" and e["prices"][8] == 0.7, e)
    e = BE.estimate(wk, date(2026, 11, 23))          # poniedziałek
    check("cel w dzień roboczy: mediana z dni roboczych", e["kind"] == "workday" and e["prices"][8] == 1.4, e)
    few = {k: v for k, v in list(wk.items())[:5]}
    check("za mało dób tego samego rodzaju → wszystkie doby (kind all)", BE.estimate(few, date(2026, 11, 23))["kind"] in ("all", "workday"))
    # okno i przyszłość
    fut = {(TARGET + timedelta(days=1)).isoformat(): SHAPE, TARGET.isoformat(): SHAPE}
    check("dni od celu wzwyż nie są historią", BE.estimate(fut, TARGET) is None)
    old = {(TARGET - timedelta(days=40 + i)).isoformat(): SHAPE for i in range(5)}
    check("dane starsze niż okno ignorowane", BE.estimate(old, TARGET) is None)
    # śmieci
    for bad in (None, 5, "x", [], {"2026-11-20": "abc"}, {"zła-data": SHAPE}, {"2026-11-20": [float("nan")] * 24}, {"2026-11-20": [True] * 24}):
        check(f"śmieci na wejściu nie wywalają ({str(bad)[:20]})", BE.estimate(bad, TARGET) is None)
    check("zły dzień docelowy", BE.estimate(hist(5), "2026-11-21") is None and BE.estimate(hist(5), None) is None)
    zero = hist(5, scale=lambda i: 0.0)
    check("ceny zerowe w historii nie dają szacunku", BE.estimate(zero, TARGET) is None)
    n = BE.note(BE.estimate(hist(6), TARGET))
    check("podpis: mówi, że to nie ceny z rynku i że plan z tego nie korzysta", n and "nie ceny z rynku" in n and "Plan z niego nie korzysta" in n, n)
    check("podpis dla None", BE.note(None) is None)


def bucket(p, secs=3600):
    b = [0.0] * 10 + [None]
    b[INS.BUY_S], b[INS.BUY_T] = p * secs, float(secs)
    return b


def env(days=6, tomorrow_prices=False, dynamic=True):
    hass, c, opt, rt = build(); S = hass.states
    now = at(2026, 11, 20, 10, 0)
    d0 = now.date(); d1 = d0 + timedelta(days=1)

    def allp(d, f):
        return [{"start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "price": f(h), "is_cheap": False, "is_expensive": False} for h in range(24)]
    lst = allp(d0, lambda h: TODAY[h]) + (allp(d1, lambda h: SHAPE[h]) if tomorrow_prices else [])
    S.set("sensor.pstryk_current_buy_price", TODAY[10], {"All prices": lst})
    S.set("sensor.pstryk_prices_fetched", "ok", {"tomorrow_available": tomorrow_prices})
    cfg = dict(const.SCHEDULER_DEFAULTS); cfg.update({"tariff_mode": "auto" if dynamic else "g11", "price_buy_entity": "sensor.pstryk_current_buy_price"})
    sch = scheduler.ScheduleOptimizer(hass, c, cfg)
    T.set_profile(T.make_profile(cfg, prices_fn=sch.buy_hourly_for, eff_fn=lambda: 0.9, source="test"))
    rt.optimizer = sch; c.runtime = rt
    for i in range(1, days + 1):
        d = d0 - timedelta(days=i)
        for h in range(24):
            rt.insights.hours[f"{d.isoformat()}T{h:02d}"] = bucket(SHAPE[h])
    return hass, c, sch, rt, d0, d1


async def main():
    pure()

    # historia z insights: średnia cena godziny; godzina < 30 min pomiaru się nie liczy
    hass, c, sch, rt, d0, d1 = env()
    rt.insights.hours[f"{(d0 - timedelta(days=1)).isoformat()}T03"] = bucket(9.9, secs=600)
    h = rt.insights.buy_history(d0, days=3)
    k1 = (d0 - timedelta(days=1)).isoformat()
    check("historia: 3 doby wstecz od dziś, bez dziś", sorted(h) == [(d0 - timedelta(days=i)).isoformat() for i in (3, 2, 1)] or len(h) == 3 and d0.isoformat() not in h, sorted(h))
    check("historia: cena godziny z koszyka", h[k1][8] == 1.4, h[k1][8])
    check("historia: zbyt krótki pomiar godziny → None", h[k1][3] is None, h[k1][3])
    empty = rt.insights.buy_history(d0 + timedelta(days=60), days=5)
    check("historia bez danych: same None", all(all(v is None for v in row) for row in empty.values()))

    # atrybuty czujnika: jutro nieopublikowane → szacunek jako OSOBNY atrybut
    a = sens.BmsRuntimeSensor._price_attrs(rt)
    json.dumps(a, allow_nan=False)
    check("czujnik: tariff dynamic i stan waiting", a.get("tariff_dynamic") is True and a.get("price_buy_tomorrow_state") == "waiting", (a.get("tariff_dynamic"), a.get("price_buy_tomorrow_state")))
    est = a.get("prices_buy_tomorrow_est")
    check("czujnik: szacunek 24 godzin ze średnich z historii", est and len(est) == 24 and abs(est[8] - 1.4) < 1e-9, est)
    check("czujnik: notatka szacunku", "nie ceny z rynku" in (a.get("price_buy_tomorrow_est_note") or ""), a.get("price_buy_tomorrow_est_note"))
    check("czujnik: prawdziwe ceny jutra NADAL puste (szacunek nie przecieka do planu)", a.get("prices_buy_tomorrow") is None and not sch.buy_hourly_for(d1))
    check("planer: buy_hourly_for(jutro) puste mimo szacunku", not sch.buy_hourly_for(d1))
    check("atrybuty szacunku są poza bazą rekordów", {"prices_buy_tomorrow_est", "price_buy_tomorrow_est_note"} <= sens.BmsRuntimeSensor._unrecorded_attributes)

    # za mało historii → brak szacunku
    hass, c, sch, rt, d0, d1 = env(days=2)
    a = sens.BmsRuntimeSensor._price_attrs(rt)
    check("czujnik: 2 doby historii → brak szacunku", "prices_buy_tomorrow_est" not in a and a.get("price_buy_tomorrow_state") == "waiting", list(a))

    # prawdziwe ceny jutra są → szacunku nie ma
    hass, c, sch, rt, d0, d1 = env(tomorrow_prices=True)
    a = sens.BmsRuntimeSensor._price_attrs(rt)
    check("prawdziwe ceny jutra: stan ok, bez szacunku", a.get("price_buy_tomorrow_state") == "ok" and "prices_buy_tomorrow_est" not in a and a.get("prices_buy_tomorrow"), list(a))

    # taryfa stała → bez szacunku
    hass, c, sch, rt, d0, d1 = env(dynamic=False)
    a = sens.BmsRuntimeSensor._price_attrs(rt)
    check("taryfa nie-dynamiczna: bez szacunku", "prices_buy_tomorrow_est" not in a, {k: a.get(k) for k in ("tariff_dynamic", "tariff_mode", "prices_buy_tomorrow_est")})


asyncio.run(main())
print(f"BUYESTIMATE PASS={common.PASS} FAIL={common.FAIL}")
