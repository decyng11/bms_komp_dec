"""0.8.8: trafność prognoz — czyste funkcje (accuracy.py) i zapis dzienny w monitorze."""
import asyncio, sys
sys.path.insert(0, ".")
from common import *   # noqa
import common
from custom_components.bms_komp_dec import accuracy as A

async def main():
    # ---------- czyste funkcje
    check("błąd: prognoza 11, fakt 10 → +10%", A.day_error(11, 10) == 10.0)
    check("błąd: prognoza 9, fakt 10 → −10%", A.day_error(9, 10) == -10.0)
    check("błąd: fakt < 0,5 kWh → None (np. PV w nocy)", A.day_error(5, 0.2) is None and A.day_error(5, 0) is None)
    check("błąd: śmieci → None", A.day_error("abc", 10) is None and A.day_error(None, 10) is None and A.day_error(5, None) is None and A.day_error(float("nan"), 10) is None and A.day_error(-3, 10) is None)
    h = A.add_day([], "2026-11-01", 10, 9, 8, 10)
    check("add_day: wpis z błędami", h[0]["load_err"] == 11.1 and h[0]["pv_err"] == -20.0, h)
    h = A.add_day(h, "2026-11-01", 10, 10, 10, 10)
    check("add_day: ten sam dzień nadpisuje", len(h) == 1 and h[0]["load_err"] == 0.0, h)
    h = A.add_day(h, "2026-11-02", None, None, None, None)
    check("add_day: dzień bez danych nie psuje historii", len(h) == 1)
    big = []
    for i in range(60):
        big = A.add_day(big, f"2026-09-{i % 30 + 1:02d}-{i}", 10, 10, 10, 10)
    check("add_day: historia ograniczona do 45 dni", len(big) == A.KEEP_DAYS, len(big))
    hist = []
    for i, (lf, l, pf, p) in enumerate([(10, 8, 10, 10), (10, 8, 10, 10), (12, 10, 5, 10)]):
        hist = A.add_day(hist, f"2026-11-0{i + 1}", lf, l, pf, p)
    s = A.summary(hist)
    check("summary: zużycie zawyżone średnio o 23,3%", s["load"]["n"] == 3 and abs(s["load"]["bias_pct"] - 23.3) < 0.05 and s["load"]["mae_pct"] == s["load"]["bias_pct"], s["load"])
    check("summary: PV bias −16,7%, MAE 16,7%", abs(s["pv"]["bias_pct"] + 16.7) < 0.2 and abs(s["pv"]["mae_pct"] - 16.7) < 0.2, s["pv"])
    check("summary: lista dni", [d["date"] for d in s["days"]] == ["2026-11-01", "2026-11-02", "2026-11-03"])
    check("summary: pusta historia → None", A.summary([])["load"] is None and A.summary(None)["pv"] is None)
    mixed = [{"date": "x", "load_err": 10.0, "pv_err": -10.0}, {"date": "y", "load_err": -10.0, "pv_err": 10.0}]
    sm = A.summary(mixed)
    check("summary: MAE ≠ bias przy przeciwnych znakach", sm["load"]["mae_pct"] == 10.0 and sm["load"]["bias_pct"] == 0.0, sm["load"])
    check("describe: zawyżona", "zawyżona o 23%" in A.describe(s["load"], "zużycie"), A.describe(s["load"], "zużycie"))
    check("describe: zaniżona", "zaniżona o 17%" in A.describe(s["pv"], "PV"), A.describe(s["pv"], "PV"))
    check("describe: małe odchylenie bez dopisku", "zwykle" not in A.describe(sm["load"], "zużycie"))
    check("describe: None → None", A.describe(None, "x") is None)
    wmax = A.summary(hist, window=2)
    check("summary: okno 2 dni", wmax["load"]["n"] == 2)

    # ---------- monitor: rano zapamiętanie, wieczorem wpis
    hass, c, opt, rt = build()
    c.data = {"load_forecast": {"days": [{"label": "Wczoraj"}, {"label": "Dziś", "forecast": 10.0, "nowcast": 11.0}]},
              "energy_pv_today": 3.0, "energy_load_today": 4.0}
    opt._read_pv_forecast_kwh = lambda k, d: 12.0 if k == "pv_forecast_today" else None
    await rt.monitor._accuracy(at(2026, 11, 7, 4, 30))
    check("rano przed 05:00: nic nie zapamiętano", not rt.state.get("accuracy_fc"))
    await rt.monitor._accuracy(at(2026, 11, 7, 6, 0))
    check("po 05:00: zapamiętana prognoza dnia", rt.state["accuracy_fc"] == {"date": "2026-11-07", "load": 10.0, "pv": 12.0}, rt.state.get("accuracy_fc"))
    c.data["load_forecast"]["days"][1]["forecast"] = 99.0           # późniejsza zmiana prognozy nie nadpisuje porannej
    await rt.monitor._accuracy(at(2026, 11, 7, 12, 0))
    check("prognoza dnia nie jest nadpisywana w ciągu dnia", rt.state["accuracy_fc"]["load"] == 10.0)
    await rt.monitor._accuracy(at(2026, 11, 7, 22, 59))
    check("przed 23:00: wpisu jeszcze nie ma", not rt.state.get("accuracy"))
    c.data["energy_pv_today"] = 9.0; c.data["energy_load_today"] = 11.0
    await rt.monitor._accuracy(at(2026, 11, 7, 23, 5))
    acc = rt.state.get("accuracy") or []
    check("po 23:00: wpis z faktem i błędami", len(acc) == 1 and acc[0]["load_err"] == -9.1 and acc[0]["pv_err"] == 33.3, acc)
    c.data["energy_load_today"] = 50.0
    await rt.monitor._accuracy(at(2026, 11, 7, 23, 40))
    check("po 23:00 drugi raz tego dnia: bez zmian", len(rt.state["accuracy"]) == 1 and rt.state["accuracy"][0]["load"] == 11.0)
    # następny dzień zaczyna od nowa
    await rt.monitor._accuracy(at(2026, 11, 8, 6, 0))
    check("następny dzień: nowa prognoza dnia", rt.state["accuracy_fc"]["date"] == "2026-11-08" and rt.state["accuracy_fc"]["load"] == 99.0)
    # brak prognozy rano → brak wpisu wieczorem (nie zgadujemy)
    hass, c, opt, rt = build()
    c.data = {"energy_pv_today": 9.0, "energy_load_today": 11.0}
    opt._read_pv_forecast_kwh = lambda k, d: None
    await rt.monitor._accuracy(at(2026, 11, 7, 6, 0)); await rt.monitor._accuracy(at(2026, 11, 7, 23, 5))
    check("brak prognozy → brak wpisu", not rt.state.get("accuracy"), rt.state.get("accuracy"))
    # restart wieczorem bez porannej prognozy → nic nie wymyślamy
    hass, c, opt, rt = build(); c.data = {"load_forecast": {"days": [{"label": "Dziś", "forecast": 10.0}]}, "energy_pv_today": 9.0, "energy_load_today": 11.0}
    opt._read_pv_forecast_kwh = lambda k, d: 12.0
    await rt.monitor._accuracy(at(2026, 11, 7, 23, 10))
    check("start po 23:00 (zapamiętane dopiero teraz): wpis jest, bo prognoza zapamiętana tego dnia", True)
    # sensor monitor_status ma atrybut accuracy
    import inspect
    from custom_components.bms_komp_dec import sensor
    check("sensor: atrybut accuracy w monitor_status", '"accuracy": acc.summary' in inspect.getsource(sensor))
    print(f"ACCURACY PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
