"""Czytnik cen RCE: różne formaty encji (u znajomych będą inne) + diagnostyka „co widzę”."""
import asyncio, sys
sys.path.insert(0, ".")
from common import *   # noqa
import common

def hourly(d, f, step=60, key="start", fmt="iso", valkey="rce_pln", extra=None):
    out = []
    for m in range(0, 24 * 60, step):
        h, mi = divmod(m, 60)
        ts = f"{d.isoformat()}T{h:02d}:{mi:02d}:00+01:00" if fmt == "iso" else f"{d.isoformat()} {h:02d}:{mi:02d}:00"
        it = {key: ts, valkey: f(h)}
        if extra: it.update(extra)
        out.append(it)
    return out

async def main():
    def fresh(now=(2026, 11, 3, 20, 12), cfg=None):
        hass, c, opt0, rt = build()
        hass.states._s.pop("sensor.rce_pse_cena", None)
        conf = dict(const.SCHEDULER_DEFAULTS); conf.update(cfg or {})
        sched = scheduler.ScheduleOptimizer(hass, c, conf)
        at(*now)
        return hass, sched, date(*now[:3]), date(*now[:3]) + timedelta(days=1)
    price = lambda h: 250 + h * 10          # różne w każdej godzinie, więc „kopia dnia” się nie zdarzy
    price2 = lambda h: 700 - h * 7
    def n(sched, d): return sum(1 for v in (sched._read_rce_arrays().get(d.isoformat()) or []) if isinstance(v, (int, float)))

    # A. integracja „RCE PSE” (HACS): jedna lista `prices` z 15-min wpisami na dziś i jutro (dtime bez strefy)
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": hourly(d0, price, 15, "dtime", "naive", extra={"period": "x"}) + hourly(d1, price2, 15, "dtime", "naive")})
    check("A: 15-min, dtime, dziś i jutro w jednej liście", n(s, d0) == 24 and n(s, d1) == 24, (n(s, d0), n(s, d1)))

    # B. styl Nord Pool: raw_today / raw_tomorrow ze znacznikami start + value
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"raw_today": hourly(d0, price, 60, "start", valkey="value"), "raw_tomorrow": hourly(d1, price2, 60, "start", valkey="value")})
    check("B: raw_today + raw_tomorrow (value)", n(s, d0) == 24 and n(s, d1) == 24, (n(s, d0), n(s, d1)))

    # C. same listy liczb: today / tomorrow
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"today": [price(h) for h in range(24)], "tomorrow": [price2(h) for h in range(24)]})
    check("C: today/tomorrow jako 24 liczby", n(s, d0) == 24 and n(s, d1) == 24, (n(s, d0), n(s, d1)))
    r = s._read_rce_arrays()
    check("C: dziś i jutro to różne listy (nie kopia)", r.get(d0.isoformat()) != r.get(d1.isoformat()) and abs((r.get(d1.isoformat()) or [9]*24)[3] - normalize(price2(3))) < 1e-9, r.get(d1.isoformat()))

    # D. osobna encja „jutro” z samą listą liczb
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": hourly(d0, price)})
    hass.states.set("sensor.rce_pse_cena_jutro", 0.5, {"prices": [price2(h) for h in range(24)]})
    check("D: osobna encja jutro (lista liczb)", n(s, d0) == 24 and n(s, d1) == 24, (n(s, d0), n(s, d1)))

    # E. nieznane nazwy atrybutów, ale znaczniki czasu są
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"dane_cenowe": hourly(d0, price, 30, "period_start", valkey="price"), "ceny_nastepny_dzien": hourly(d1, price2, 30, "period_start", valkey="price")})
    check("E: dowolne nazwy list ze znacznikami czasu", n(s, d0) == 24 and n(s, d1) == 24, (n(s, d0), n(s, d1)))

    # F. skonfigurowana encja sprzedaży o dowolnej nazwie
    hass, s, d0, d1 = fresh(cfg={"price_sell_entity": "sensor.moje_ceny_sprzedazy"})
    hass.states.set("sensor.moje_ceny_sprzedazy", 0.6, {"raw_today": hourly(d0, price, valkey="value"), "raw_tomorrow": hourly(d1, price2, valkey="value")})
    check("F: własna encja z konfiguracji", n(s, d0) == 24 and n(s, d1) == 24, (n(s, d0), n(s, d1)))

    # G. inna encja z „rce” w nazwie, o nieznanej nazwie
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"nic": 1})
    hass.states.set("sensor.rce_ceny_pln", 0.6, {"tomorrow_prices": hourly(d1, price2), "today_prices": hourly(d0, price)})
    check("G: odkrycie encji z „rce” w nazwie", n(s, d0) == 24 and n(s, d1) == 24, (n(s, d0), n(s, d1)))

    # H. kopia dnia nie jest planem na jutro
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"today": [price(h) for h in range(24)], "tomorrow": [price(h) for h in range(24)]})
    check("H: identyczne dziś i jutro → jutro odrzucone", n(s, d0) == 24 and n(s, d1) == 0)

    # I. lista bez znaczników pod nazwą „today” nie może stać się cenami na jutro
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"today": [price(h) for h in range(24)]})
    check("I: tylko „today” bez znaczników → jutro puste", n(s, d0) == 24 and n(s, d1) == 0)

    # J. częściowe jutro (np. 10 godzin) liczy się jako niepełne
    hass, s, d0, d1 = fresh()
    part = hourly(d1, price2)[:10]
    hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": hourly(d0, price) + part})
    check("J: częściowe jutro = 10/24", n(s, d0) == 24 and n(s, d1) == 10, (n(s, d0), n(s, d1)))

    # K. wybiera źródło z lepszym pokryciem, nie pierwsze lepsze
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": hourly(d0, price) + hourly(d1, price2)[:6]})
    hass.states.set("sensor.rce_pse_cena_jutro", 0.5, {"prices": hourly(d1, price2)})
    check("K: lepsze pokrycie wygrywa (24 zamiast 6)", n(s, d1) == 24, n(s, d1))

    # L. diagnostyka: co widzę, gdy nie ma list / gdy nie ma encji
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"friendly_name": "RCE"})
    s._read_rce_arrays(); rep = s.rce_report()
    txt = " ".join(rep["seen"])
    check("L: raport wskazuje encję i brak list", "sensor.rce_pse_cena" in txt and rep["tomorrow"]["hours"] == 0 and rep["today"]["hours"] == 0, rep)
    hass, s, d0, d1 = fresh()
    s._read_rce_arrays(); rep = s.rce_report()
    check("L: bez żadnej encji raport mówi, czego szukano", rep["seen"] == [] and "sensor.rce_pse_cena" in rep["checked"], rep)
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"raw_today": hourly(d0, price), "raw_tomorrow": hourly(d1, price2)})
    s._read_rce_arrays(); rep = s.rce_report()
    check("L: raport podaje źródło i liczbę godzin", rep["tomorrow"]["hours"] == 24 and rep["tomorrow"]["source"] == "sensor.rce_pse_cena.raw_tomorrow" and rep["today"]["source"] == "sensor.rce_pse_cena.raw_today", rep)

    # M. śmieci w atrybutach nie wywalają czytnika
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": [None, 5, "x", {"start": "nie-data", "rce_pln": "abc"}, {"start": None}, {"rce_pln": 3}, [1, 2], {"start": f"{d1.isoformat()}T05:00:00+01:00", "rce_pln": None}],
                                              "raw_tomorrow": "tekst", "today": {"a": 1}, "tomorrow": None})
    try:
        r = s._read_rce_arrays(); ok_ = True
    except Exception as err:
        ok_ = False; r = err
    check("M: śmieci w atrybutach → bez wyjątku", ok_ and n(s, d1) == 0, r)

    # O. osobne encje „jutro” o nazwach znanych karcie (dawniej backend znał tylko dwie)
    for nm in ("sensor.cena_pradu_jutro", "sensor.rce_prices_tomorrow", "sensor.energy_price_tomorrow"):
        hass, s, d0, d1 = fresh()
        hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": hourly(d0, price)})
        hass.states.set(nm, 0.5, {"prices": [price2(h) for h in range(24)]})
        check(f"O: {nm}", n(s, d0) == 24 and n(s, d1) == 24, (n(s, d0), n(s, d1)))
    # P. encja „jutro” wykryta wzorcem nazwy
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": hourly(d0, price)})
    hass.states.set("sensor.moje_rce_cena_jutro_pln", 0.5, {"raw_today": [price2(h) for h in range(24)]})
    check("P: wzorzec nazwy rce…cena…jutro", n(s, d1) == 24, n(s, d1))
    # Q. lista bez znaczników z encji „jutro” NIE może zostać cenami „dziś”, gdy dziś jest niepełne
    hass, s, d0, d1 = fresh()
    hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": hourly(d0, price)[:9]})
    hass.states.set("sensor.cena_pradu_jutro", 0.5, {"prices": [price2(h) for h in range(24)]})
    check("Q: lista z encji „jutro” nie trafia do „dziś”", n(s, d0) == 9 and n(s, d1) == 24, (n(s, d0), n(s, d1)))

    # N. monitor: pełne ceny → brak alarmu; brak → alarm z opisem źródeł; po ich pojawieniu się alarm jest zdejmowany
    from custom_components.bms_komp_dec import monitor as mon
    import types
    hass, c, opt0, rt = build()
    hass.states._s.pop("sensor.rce_pse_cena", None)
    sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS))
    rt = rtm.BmsRuntime(hass, c, sched); c.runtime = rt
    now = at(2026, 11, 3, 20, 12); d0 = now.date(); d1 = d0 + timedelta(days=1)
    hass.states.set("sensor.rce_pse_cena", 0.6, {"raw_today": hourly(d0, price, valkey="value"), "raw_tomorrow": hourly(d1, price2, valkey="value")})
    m = mon.Monitor(rt)
    await m._rce(now)
    nn = [x for x in hass.services.calls if x[0] == "persistent_notification" and x[1] == "create"]
    check("N: pełne ceny na jutro → brak powiadomienia", not nn, nn)
    hass.states.set("sensor.rce_pse_cena", 0.6, {"raw_today": hourly(d0, price, valkey="value")})
    await m._rce(now)
    nn = [x for x in hass.services.calls if x[0] == "persistent_notification" and x[1] == "create"]
    check("N: brak cen na jutro → jedno powiadomienie z nazwą encji", len(nn) == 1 and "sensor.rce_pse_cena" in nn[0][2]["message"] and "0/24" in nn[0][2]["message"], nn)
    hass.states.set("sensor.rce_pse_cena", 0.6, {"raw_today": hourly(d0, price, valkey="value"), "raw_tomorrow": hourly(d1, price2, valkey="value")})
    await m._rce(now)
    dd = [x for x in hass.services.calls if x[0] == "persistent_notification" and x[1] == "dismiss"]
    check("N: gdy ceny się pojawią, powiadomienie jest zdejmowane", len(dd) == 1, dd)
    await m._rce(now)
    dd = [x for x in hass.services.calls if x[0] == "persistent_notification" and x[1] == "dismiss"]
    check("N: zdjęcie powiadomienia tylko raz", len(dd) == 1, dd)

    print(f"RCE PASS={common.PASS} FAIL={common.FAIL}")

def normalize(v):
    return helpers.normalize_price(float(v))

asyncio.run(main())
