"""Własne ceny godzinowe: RCE z PSE → cena zakupu dopasowana do prawdziwej taryfy dynamicznej (pricefeed.py)."""
import math, sys
from common import *   # noqa
import common
from datetime import date, timedelta
from custom_components.bms_komp_dec import pricefeed as pf


def rows(day, f, quarter=True):
    out = []
    for h in range(24):
        for q in ((0, 15, 30, 45) if quarter else (0,)):
            end_m = h * 60 + q + (15 if quarter else 60)
            end = f"{day.isoformat()} {(end_m // 60) % 24:02d}:{end_m % 60:02d}:00"
            per = f"{h:02d}:{q:02d} - {(h * 60 + q + 15) // 60 % 24:02d}:{(h * 60 + q + 15) % 60:02d}"
            out.append({"rce_pln": f(h) * 1000.0, "dtime": end, "period": per, "business_date": day.isoformat()})
    return {"value": out}


def main():
    d = date(2026, 11, 23)
    p = pf.parse_rce(rows(d, lambda h: 0.4 + 0.01 * h), d)
    check("PSE: 24 godziny, PLN/MWh → zł/kWh", p and len(p) == 24 and abs(p[0] - 0.4) < 1e-6 and abs(p[23] - 0.63) < 1e-6, p)
    p2 = pf.parse_rce(rows(d, lambda h: 0.5, quarter=False), d)
    check("PSE: wpisy godzinowe też", p2 and all(abs(x - 0.5) < 1e-6 for x in p2), p2)
    # bez „period”: godzina z końca okresu − 15 min (00:15 to początek 00:00)
    pay = rows(d, lambda h: 0.1 * (h + 1))
    for r in pay["value"]:
        r.pop("period")
    p3 = pf.parse_rce(pay, d)
    check("PSE: bez „period” godzina liczona z dtime (koniec okresu)", p3 and abs(p3[0] - 0.1) < 1e-6 and abs(p3[23] - 2.4) < 1e-6, p3)
    check("PSE: za mało godzin (doba nieopublikowana) → None", pf.parse_rce({"value": rows(d, lambda h: 1)["value"][:20]}, d) is None)
    check("PSE: zła odpowiedź → None, bez błędu", pf.parse_rce(None, d) is None and pf.parse_rce({"value": "x"}, d) is None and pf.parse_rce([1, 2], d) is None)
    check("PSE: wiersze innej doby ignorowane", pf.parse_rce(rows(d + timedelta(days=1), lambda h: 1), d) is None)
    check("adres: filtr po business_date", "business_date" in pf.day_url(d) and "2026-11-23" in pf.day_url(d) and " " not in pf.day_url(d), pf.day_url(d))

    # --- dopasowanie: cena = 1,23 × RCE + opłata (strefowa: 0,40 w szczycie, 0,15 poza)
    rce, buy = {}, {}
    for i in range(1, 11):
        day = d - timedelta(days=i)
        rce[day.isoformat()] = [round(0.3 + 0.2 * math.sin(i + h / 3.0), 4) for h in range(24)]
        buy[day.isoformat()] = [round(1.23 * rce[day.isoformat()][h] + (0.40 if 6 <= h < 22 else 0.15), 4) for h in range(24)]
    m = pf.fit(rce, buy)
    check("dopasowanie: mnożnik ≈ 1,23", m and abs(m["a"] - 1.23) < 0.01, m)
    check("dopasowanie: opłata godzinowa wychwycona (szczyt 0,40 / noc 0,15)", m and abs(m["b"][12] - 0.40) < 0.01 and abs(m["b"][3] - 0.15) < 0.01, m and m["b"])
    check("dopasowanie: błąd ≈ 0, jakość „idealne”, 100% godzin co do grosza", m and m["rmse"] < 0.01 and m["quality"] == "idealne" and m["exact"] == 1.0, m)
    tom = [0.5] * 24
    pr = pf.predict(tom, m)
    check("predykcja: 0,5 → 1,23×0,5 + 0,40 = 1,015 w szczycie, 0,765 w nocy", pr and abs(pr[12] - 1.015) < 0.01 and abs(pr[3] - 0.765) < 0.01, pr)
    # nieprzystające ceny (operator liczy z innej giełdy) → jakość „słaba”, nie udajemy dokładności
    import random
    rnd = random.Random(3)
    bad = {k: [round(0.9 + rnd.random() * 0.8, 3) for _ in range(24)] for k in buy}
    mb = pf.fit(rce, bad)
    check("dopasowanie: ceny bez związku z RCE → jakość „słaba”", mb and mb["quality"] == "słabe", mb)
    check("dopasowanie: za mało dób → None", pf.fit({k: rce[k] for k in list(rce)[:2]}, buy) is None)
    check("dopasowanie: ujemny/zerowy zakup pomijany, brak danych → None", pf.fit({}, {}) is None and pf.fit(rce, {k: [0] * 24 for k in rce}) is None)
    check("predykcja: bez modelu albo bez RCE → None", pf.predict(tom, None) is None and pf.predict(None, m) is None and pf.predict(tom, {"a": 1, "b": [1]}) is None)
    check("predykcja: dziura w RCE → dziura w cenie", pf.predict([None] + [0.5] * 23, m)[0] is None)
    pr2 = pf.prune({(d - timedelta(days=40)).isoformat(): [1.0] * 24, d.isoformat(): [1.0] * 24, "zly": [1], (d + timedelta(days=1)).isoformat(): [1.0] * 5}, d)
    check("prune: stare, złe i niepełne dobry wyrzucone", list(pr2) == [d.isoformat()], pr2)
    ser = pf.series(d, [0.5, None, 0.7], "+01:00")
    check("seria: format {start, price}, bez dziur", ser == [{"start": "2026-11-23T00:00:00+01:00", "price": 0.5}, {"start": "2026-11-23T02:00:00+01:00", "price": 0.7}], ser)

    # weekendy mają inne opłaty (np. strefa całą dobę tania): model uczy je osobno i trafia co do grosza
    import random
    random.seed(3)
    rce_w, buy_w = {}, {}
    for i in range(1, 22):
        dd = date(2026, 11, 23) - timedelta(days=i)
        r = [round(0.3 + 0.2 * math.sin(i + h / 3.0), 4) for h in range(24)]
        wk = dd.weekday() >= 5
        rce_w[dd.isoformat()] = r
        buy_w[dd.isoformat()] = [round(1.23 * r[h] + (0.15 if (wk or not 6 <= h < 22) else 0.40), 4) for h in range(24)]
    mw = pf.fit(rce_w, buy_w)
    check("weekend: osobne opłaty, 100% godzin co do grosza", mw and mw["bw"] and mw["exact"] == 1.0 and mw["quality"] == "idealne", mw and {k: mw[k] for k in ("exact", "rmse", "quality")})
    sat, mon = date(2026, 11, 28), date(2026, 11, 23)
    rr = [0.5] * 24
    ps, pm = pf.predict(rr, mw, sat), pf.predict(rr, mw, mon)
    check("predykcja: sobota 10:00 = tania strefa, poniedziałek 10:00 = szczyt", abs(ps[10] - (1.23 * 0.5 + 0.15)) < 0.01 and abs(pm[10] - (1.23 * 0.5 + 0.40)) < 0.01, (ps[10], pm[10]))
    noisy = {k: [round(v + random.uniform(-0.04, 0.04), 4) for v in row] for k, row in buy_w.items()}
    mn = pf.fit(rce_w, noisy)
    check("szum cen: odsetek trafień co do grosza spada, jakość nie jest „idealne”", mn and mn["exact"] < 0.6 and mn["quality"] != "idealne" and mn["max_err"] > 0.01, mn and {k: mn[k] for k in ("exact", "max_err", "quality")})
    print(f"PRICEFEED PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)


main()
