"""Uszkodzone pliki zapisu (.storage): księga zysków, statystyki baterii, taryfa, historia zużycia, urządzenia, historia godzinowa,
dziennik — zły kształt albo „nan”/„inf” nie zatrzymuje startu, nie zatruwa sum; po starcie kopia oryginału + powiadomienie."""
import asyncio, math, sys
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import store_guard as SG, tariff as tar, notify_cfg
from custom_components.bms_komp_dec import battery_stats as bsm, devices as devm, insights as insm, decision_log as dlm, diag_store as dsm


def feed(obj, raw):
    """Podstawia zawartość pliku zapisu, którą obiekt zobaczy przy wczytywaniu."""
    async def _load():
        return raw
    obj._store.async_load = _load
    return obj


NAN, INF = float("nan"), float("inf")
_ = -INF


async def main():
    hass, c, opt, rt = build()
    at(2026, 11, 20, 12, 0)

    # ---- pomocnicze
    check("num: nan/inf/bool/tekst odrzucone", all(SG.num(v) is None for v in (NAN, INF, -INF, True, "abc", None, [], {})))
    check("num: liczba i liczba w tekście", SG.num(3) == 3.0 and SG.num("2.5") == 2.5)
    check("num: zakres", SG.num(5, 0, 4) is None and SG.num(-1, 0, 4) is None and SG.num(4, 0, 4) == 4.0)
    check("num: ogromna liczba całkowita nie rzuca", SG.num(10 ** 400) is None)
    check("is_day: tylko poprawne daty", SG.is_day("2026-11-20") and not SG.is_day("2026-13-40") and not SG.is_day("x") and not SG.is_day(5))
    check("scrub usuwa nan z słownika i zamienia w liście", SG.scrub({"a": 1.0, "b": NAN, "c": [1.0, INF]}) == {"a": 1.0, "c": [1.0, 0.0]})
    check("has_nonfinite", SG.has_nonfinite({"x": [1, {"y": NAN}]}) and not SG.has_nonfinite({"x": [1, {"y": 2.0}]}))

    # ---- księga zysków
    from custom_components.bms_komp_dec.ledger import Ledger
    lg = feed(Ledger(hass), {"days": {
        "2026-11-19": {"export_kwh": 5.0, "import_kwh": 2.0, "revenue": 3.0, "cost": 1.0},
        "2026-11-18": {"export_kwh": NAN, "import_kwh": "x", "revenue": INF, "cost": 2.0},
        "zly-klucz": {"export_kwh": 1.0},
        "2026-11-17": [1, 2],
    }})
    await lg.async_load()
    check("księga: poprawny dzień wczytany", lg.days["2026-11-19"]["export_kwh"] == 5.0 and lg.days["2026-11-19"]["neg_export_kwh"] == 0.0)
    d18 = lg.days.get("2026-11-18") or {}
    check("księga: nan/inf/tekst → 0, sumy skończone", d18.get("export_kwh") == 0.0 and d18.get("revenue") == 0.0 and d18.get("cost") == 2.0, d18)
    check("księga: zły klucz i zły wpis pominięte", "zly-klucz" not in lg.days and "2026-11-17" not in lg.days)
    check("księga: bilans nie jest nan", math.isfinite(lg.total_net()), lg.total_net())
    check("księga: zgłoszona naprawa z oryginałem", bool(lg.integrity) and lg.integrity.raw is not None and "księga" in lg.integrity.summary())
    for bad in ([], "tekst", 7, {"days": []}, {"days": "x"}, {"days": {"2026-11-19": None}}):
        l2 = feed(Ledger(hass), bad)
        try:
            await l2.async_load(); ok = True
        except Exception as e:
            ok = False; print("wyjątek:", repr(bad), e)
        check(f"księga: kształt {bad!r} nie wywala startu", ok and isinstance(l2.days, dict))
    l3 = feed(Ledger(hass), None); await l3.async_load()
    check("księga: brak pliku = brak naprawy", not l3.integrity and l3.days == {})
    l4 = feed(Ledger(hass), {"days": {"2026-11-19": {"export_kwh": 1.0, "import_kwh": 1.0, "revenue": 1.0, "cost": 1.0}}}); await l4.async_load()
    check("księga: poprawny plik (starszy układ bez pól) = bez naprawy", not l4.integrity)

    # ---- statystyki baterii
    bs = feed(bsm.BatteryStats(hass), {"days": [1, 2], "caps": "x"})
    try:
        await bs.async_load(); ok = True
    except Exception as e:
        ok = False; print("wyjątek:", e)
    check("statystyki: days jako lista nie wywala startu (wcześniej AttributeError)", ok and bs.days == {} and bs.caps == [])
    check("statystyki: zgłoszone", bool(bs.integrity))
    bs = feed(bsm.BatteryStats(hass), {"days": {"2026-11-19": {"pv": 10.0, "soc0": 150.0, "soc1": 20.0, "t1h": NAN, "chg": "a"}, "2026-11-20": {"pv": 1}},
                                       "caps": [{"t": 5, "cap": 12.0, "dsoc": 10.0, "e": 1.2}, {"cap": NAN}, "x", {"cap": -3}]})
    await bs.async_load()
    check("statystyki: SOC spoza 0–100, nan i tekst odrzucone", bs.days["2026-11-19"] == {"pv": 10.0, "soc1": 20.0}, bs.days["2026-11-19"])
    check("statystyki: pomiary pojemności filtrowane", [x["cap"] for x in bs.caps] == [12.0], bs.caps)
    bs = feed(bsm.BatteryStats(hass), {"days": {"2026-11-19": {"pv": 10.0, "soc0": 20.0, "soc1": 80.0, "t1h": 23.9, "chg": 3.0, "dis": 2.0}}, "caps": [{"t": 1, "cap": 10.0}]})
    await bs.async_load()
    check("statystyki: poprawny plik bez naprawy", not bs.integrity and bs.caps == [{"cap": 10.0, "t": 1}] and "soc0" in bs.days["2026-11-19"])

    # ---- taryfa
    t = tar.G12wTariff(hass, "sensor.x")
    feed(t, {"prices": {"peak": NAN, "off_peak": -2.0}})
    await t.async_load()
    check("taryfa: nan i ujemna cena odrzucone, zgłoszone", t.prices == {"peak": None, "off_peak": None} and len(t.integrity.notes) == 2, (t.prices, t.integrity.notes))
    t = tar.G12wTariff(hass, "sensor.x"); feed(t, {"prices": ["x"]})
    await t.async_load()
    check("taryfa: prices jako lista = zgłoszone, bez wyjątku", bool(t.integrity) and t.prices["peak"] is None)
    t = tar.G12wTariff(hass, "sensor.x"); feed(t, "śmieci")
    await t.async_load()
    check("taryfa: plik-napis = zgłoszone", bool(t.integrity))
    t = tar.G12wTariff(hass, "sensor.x"); feed(t, {"prices": {"peak": 1.1, "off_peak": 0.6}})
    await t.async_load()
    check("taryfa: poprawne ceny wczytane bez naprawy", t.prices == {"peak": 1.1, "off_peak": 0.6} and not t.integrity)

    # ---- historia zużycia
    lf = lfm.LoadForecaster(hass, lambda: None)
    feed(lf, {"days": {"2026-11-19": 12.0, "2026-11-18": NAN, "kiepski": 5.0, "2026-11-17": 99999.0},
              "profiles": {"2026-11-19": [0.04] * 24, "2026-11-18": [0.04] * 23, "2026-11-17": [NAN] * 24},
              "forecast_history": [1, 2], "temperatures": {"2026-11-19": 4.5, "2026-11-18": 900},
              "seasonal_factors": {"1": 1.1, "13": 1.0, "x": 1.0, "2": NAN},
              "hourly_accum": {"values": [NAN] * 24, "date": "2026-11-20"},
              "hdd_coef": "abc", "params": {"alpha": NAN}, "tune": {"x": NAN, "y": 1.0}})
    try:
        await lf.async_load(); ok = True
    except Exception as e:
        ok = False; print("wyjątek:", repr(e))
    check("prognoza zużycia: uszkodzony plik nie wywala wczytywania", ok)
    check("prognoza zużycia: tylko poprawne dni", lf.days == {"2026-11-19": 12.0}, lf.days)
    check("prognoza zużycia: tylko pełny, skończony profil", list(lf.profiles) == ["2026-11-19"], list(lf.profiles))
    check("prognoza zużycia: temperatury i współczynniki sezonowe filtrowane", lf.temperatures.get("2026-11-19") == 4.5 and "2026-11-18" not in lf.temperatures
          and lf.seasonal_factors == {1: 1.1}, (lf.temperatures, lf.seasonal_factors))
    check("prognoza zużycia: nan w sumach godzinowych → od zera", all(x == 0.0 for x in lf._hourly_accum))
    check("prognoza zużycia: nan w strojeniu zgłoszony i usunięty (po starcie strojenie liczy się od nowa)",
          any("dostrojeniu" in n for n in lf.integrity.notes) and not SG.has_nonfinite(lf.tune), (lf.integrity.notes, lf.tune))
    check("prognoza zużycia: parametr nan nie nadpisał domyślnego", math.isfinite(lf.params["alpha"]) and math.isfinite(lf.hdd_coef))
    check("prognoza zużycia: naprawa zgłoszona", len(lf.integrity.notes) >= 5, lf.integrity.notes)
    lf2 = lfm.LoadForecaster(hass, lambda: None); feed(lf2, ["x"])
    await lf2.async_load()
    check("prognoza zużycia: plik-lista zgłoszony", bool(lf2.integrity) and lf2._loaded)

    # ---- urządzenia
    dm = devm.DeviceManager(hass)
    feed(dm, {"devices": [{"id": "boj", "name": "Bojler", "power_eid": "sensor.boj_p", "category": "boiler"}, "x", {"power_eid": "zle"}],
              "data": {"boj": {"daily": {"2026-11-19": 3.0, "2026-11-18": NAN}, "hourly": {"2026-11-19": [1.0, "abc", None] + [0.0] * 21},
                               "cycles": [{"kwh": 1.0}, {"kwh": NAN}, "x"]}},
              "price_min": {"2026-11-19": 0.3, "2026-11-18": INF}})
    try:
        await dm.async_load(); ok = True
    except Exception as e:
        ok = False; print("wyjątek:", repr(e))
    check("urządzenia: tekst w godzinach nie rzuca (wcześniej ValueError gubił wszystkie dane)", ok)
    check("urządzenia: poprawne urządzenie zostaje, dwa uszkodzone pominięte", [d["id"] for d in dm.devices] == ["boj"])
    rec = dm.data.get("boj") or {}
    check("urządzenia: nan w danych dziennych odrzucony", rec.get("daily") == {"2026-11-19": 3.0}, rec.get("daily"))
    check("urządzenia: tekst w godzinach = 0.0", (rec.get("hourly") or {}).get("2026-11-19", [])[:3] == [1.0, 0.0, 0.0])
    check("urządzenia: cykle z nan pominięte", rec.get("cycles") == [{"kwh": 1.0}], rec.get("cycles"))
    check("urządzenia: nan w cenach minimalnych pominięty", dm.price_min == {"2026-11-19": 0.3})
    check("urządzenia: naprawa zgłoszona", bool(dm.integrity))
    dm = devm.DeviceManager(hass); feed(dm, {"devices": "x", "data": []})
    await dm.async_load()
    check("urządzenia: devices i data o złym kształcie zgłoszone", len(dm.integrity.notes) >= 2 and dm.devices == [], dm.integrity.notes)

    # ---- historia godzinowa
    ins = insm.Insights(hass)
    feed(ins, {"hours": [1, 2], "days": {"2026-11-19": {"pv": NAN, "load": 5.0}, "x": 7}, "fc": {"2026-11-19": {"pv_fc": INF, "n": 1}, "y": 3},
               "counters": {"2026-11-19": {"pv": 3.0, "load": NAN}, "z": 1}, "cur_day": 5})
    try:
        await ins.async_load(); ok = True
    except Exception as e:
        ok = False; print("wyjątek:", repr(e))
    check("historia godzinowa: hours jako lista nie wywala startu (wcześniej AttributeError)", ok)
    check("historia godzinowa: nan usunięte z dni i prognoz", ins.days == {"2026-11-19": {"load": 5.0}} and ins.fc == {"2026-11-19": {"n": 1}}, (ins.days, ins.fc))
    check("historia godzinowa: liczniki z nan filtrowane", ins.counters == {"2026-11-19": {"pv": 3.0}}, ins.counters)
    check("historia godzinowa: naprawa zgłoszona", bool(ins.integrity))

    # ---- dziennik i magazyn Diagnostyki
    lg2 = feed(dlm.DecisionLog(hass), {"entries": [{"ts": "2026-11-20T10:00:00+01:00", "msg": "ok"}, {"ts": 5, "msg": "x"}, {"ts": "a", "msg": None}, "x"]})
    await lg2.async_load()
    check("dziennik: tylko wpisy z napisowym ts i msg", [e["msg"] for e in lg2.entries] == ["ok"] and bool(lg2.integrity))
    ds = feed(dsm.DiagStore(hass), ["x"]); await ds.async_load()
    check("magazyn Diagnostyki: plik-lista zgłoszony, bez wyjątku", bool(ds.integrity) and ds.data == {})

    # ---- raport po starcie: kopia + dziennik + powiadomienie
    hass, c, opt, rt = build(); S = hass.states
    rt.ledger = feed(rt.ledger, {"days": {"2026-11-19": {"export_kwh": NAN, "cost": 1.0}, "kiepski": {}}})
    rt.stats = feed(rt.stats, {"days": [1]})
    rt.insights = feed(rt.insights, {"hours": [1]})
    rt._state_store.async_load = (lambda: asyncio.sleep(0, {"low_soc_active": "tak", "notified": []}))
    # prognoza i taryfa w tym środowisku: atrapy bez integralności — runtime ma je pominąć
    rt.log._store.async_load = (lambda: asyncio.sleep(0, None))
    rt.diag_store._store.async_load = (lambda: asyncio.sleep(0, None))
    rt.devices._store.async_load = (lambda: asyncio.sleep(0, None))
    await rt.async_load()
    items = rt.integrity_items()
    keys = sorted(i.key for i in items)
    check("runtime: zebrano naprawy z księgi, statystyk, historii i stanu", keys == sorted(["bms_komp_dec_ledger", "bms_komp_dec_battery_stats", "bms_komp_dec_insights", "bms_komp_dec_runtime"]), keys)
    check("runtime: stan naprawiony i zgłoszony", rt.state["low_soc_active"] is False and any("low_soc_active" in n for i in items for n in i.notes))
    saved = []
    from custom_components.bms_komp_dec import runtime as _rtm
    async def fake_backup(h, key, raw): saved.append((key, raw is not None)); return True
    _rtm.backup_raw = fake_backup
    sent = []
    async def fake_send(kind, title, message, **kw): sent.append((kind, title, message, kw.get("level"))); return True
    rt.monitor.notifier.send = fake_send
    await rt.store_repair_tick(at(2026, 11, 20, 12, 1))
    check("kopia zapisana dla każdego naprawionego pliku", sorted(k for k, _ in saved) == keys and all(ok for _, ok in saved), saved)
    check("jedno powiadomienie „data_repair” z listą plików", len(sent) == 1 and sent[0][0] == "data_repair" and "księga zysków" in sent[0][2] and "stan EMS" in sent[0][2], sent)
    check("dziennik zawiera wpis o naprawie każdego pliku", sum(1 for e in rt.log.entries if "Naprawiono uszkodzone dane" in e.get("msg", "")) == len(keys))
    await rt.store_repair_tick(at(2026, 11, 20, 12, 2))
    check("raport tylko raz na start", len(sent) == 1 and len(saved) == len(keys))
    check("rodzaj data_repair w katalogu powiadomień i w priorytetach", "data_repair" in notify_cfg.CATALOG and notify_cfg.PRIORITY.get("data_repair") == 2)

    # ---- zdrowy start: żadnego raportu
    hass, c, opt, rt = build()
    await rt.async_load()
    sent = []; rt.monitor.notifier.send = fake_send
    await rt.store_repair_tick(at(2026, 11, 20, 12, 3))
    check("zdrowy start: bez kopii i bez powiadomienia", sent == [] and rt.integrity_items() == [])

    print(f"STOREGUARD PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
