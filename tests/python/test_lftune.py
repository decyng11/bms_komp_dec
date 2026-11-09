"""0.9.3: prognoza zużycia — codzienne uczenie (współczynniki) i samostrojenie wariantu testem wstecz."""
import asyncio, sys, math
from common import *   # noqa
import common
from datetime import date, datetime, timedelta
from custom_components.bms_komp_dec import load_forecast as lfm

def mk(values, today):
    hass, c, opt, rt = build()
    lf = lfm.LoadForecaster(hass, lambda: "sensor.x"); lf._loaded = True
    n = len(values)
    for i, v in enumerate(values):
        d = today - timedelta(days=n - i)
        lf.days[d.isoformat()] = v
    return lf

def main():
    today = date(2026, 11, 9); at(2026, 11, 9, 8, 0)
    # --- stabilne dane z lekkim szumem: zostaje wariant standardowy
    vals = [10.0 + 0.8 * math.sin(i * 1.7) for i in range(50)]
    lf = mk(vals, today); lf._autotune(today)
    check("stabilne dane: sprawdzono wiele wariantów", lf.tune.get("tried", 0) >= 30 and lf.tune.get("n", 0) >= 10, lf.tune)
    check("stabilne dane: błąd wariantu ≤ błędu standardowego", lf.tune["mae"] <= lf.tune["mae_default"] + 1e-9, lf.tune)
    # --- skokowa zmiana poziomu (nagłe zimno): szybszy wariant wygrywa
    vals = [8.0 + 0.3 * math.sin(i) for i in range(30)] + [16.0 + 0.3 * math.sin(i) for i in range(20)]
    lf = mk(vals, today); lf._autotune(today)
    t = lf.tune
    check("skok poziomu: wybrany inny wariant niż standardowy", t.get("variant") not in (None, "standardowy"), t)
    check("skok poziomu: błąd wyraźnie mniejszy (≥3%)", t["mae"] <= 0.97 * t["mae_default"], t)
    check("parametry zapisane w modelu", lf.params != lfm.DEFAULT_PARAMS, lf.params)
    p_new = lf.predict(today + timedelta(days=1), today)
    lfd = mk(vals, today); p_def = lfd.predict(today + timedelta(days=1), today)
    check("prognoza po strojeniu bliższa nowego poziomu (16) niż standardowa", abs(p_new - 16) <= abs(p_def - 16) + 1e-9 and p_new != p_def, (p_new, p_def))
    # --- za mało historii
    lf = mk([10.0] * 12, today); lf._autotune(today)
    check("za mało dni: bez zmiany parametrów", lf.params == lfm.DEFAULT_PARAMS and lf.tune.get("n") == 0, lf.tune)
    # --- konserwacja: raz na dobę, po 6:00
    lf = mk(vals, today); calls = []
    lf._autotune = lambda d: calls.append(d)
    lf._maintenance(datetime(2026, 11, 9, 3, 0, tzinfo=stubs.TZ)); check("przed 6:00 nie uczy", calls == [])
    lf._maintenance(datetime(2026, 11, 9, 7, 0, tzinfo=stubs.TZ)); lf._maintenance(datetime(2026, 11, 9, 9, 0, tzinfo=stubs.TZ))
    check("po 6:00 raz na dobę", len(calls) == 1, calls)
    lf._maintenance(datetime(2026, 11, 10, 7, 0, tzinfo=stubs.TZ)); check("następna doba: znów", len(calls) == 2)
    # --- współczynniki temperatury przeliczane codziennie
    lf = mk([10.0] * 40, today); lf._autotune = lambda d: None
    for i in range(1, 41):
        lf.temperatures[(today - timedelta(days=i)).isoformat()] = 0.0 if i <= 10 else 20.0
    for i in range(1, 11):
        lf.days[(today - timedelta(days=i)).isoformat()] = 14.0
    before = lf.hdd_coef; lf._maintenance(datetime(2026, 11, 9, 7, 0, tzinfo=stubs.TZ))
    check("współczynnik zimna przeliczony przy konserwacji", lf.hdd_coef != before and lf.hdd_coef > 0.0, (before, lf.hdd_coef))
    # --- czyszczenie historii resetuje parametry
    lf.params = dict(lfm.DEFAULT_PARAMS, alpha=0.5); lf.tune = {"x": 1}; lf.clear_history()
    check("czyszczenie historii: parametry domyślne", lf.params == lfm.DEFAULT_PARAMS and lf.tune == {})
    print(f"LFTUNE PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)
main()
