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
    # --- rosnące zużycie (zimno) i weekendy 1,4× wyższe: baza weekendowa z dawnych weekendów się spóźnia, świeży poziom ją goni
    vals = []
    for i in range(60):
        d = today - timedelta(days=60 - i)
        vals.append((7.0 + 0.12 * i) * (1.4 if d.weekday() >= 5 else 1.0))
    lf = mk(vals, today); sun = date(2026, 11, 15)          # niedziela
    truth = (7.0 + 0.12 * (60 + (sun - today).days - 1)) * 1.4
    lf.params = dict(lfm.DEFAULT_PARAMS, lvl_w=0.0); p0 = lf._model_core(sun, today)
    lf.params = dict(lfm.DEFAULT_PARAMS, lvl_w=1.0); p1 = lf._model_core(sun, today)
    check("trend: model „świeży poziom” bliżej prawdy dla weekendu niż standardowy", abs(p1 - truth) < abs(p0 - truth), (round(p0, 2), round(p1, 2), round(truth, 2)))
    check("trend: standardowy zaniża weekend o ≥10%", p0 < 0.9 * truth, (p0, truth))
    lf = mk(vals, today); lf._autotune(today)
    check("trend: samostrojenie wybiera wariant ze świeżym poziomem", "świeży poziom" in str(lf.tune.get("variant")) and lf.params.get("lvl_w", 0) > 0, lf.tune)
    lf = mk([10.0 + 0.8 * math.sin(i * 1.7) for i in range(50)], today); lf._autotune(today)
    check("stabilne dane: lvl_w zostaje 0", lf.params.get("lvl_w", 0) == 0, lf.tune)
    # --- stałe zaniżanie dni wolnych: korekta może przekroczyć ±25% (do +50%)
    jump = []
    for i in range(60):
        d = today - timedelta(days=60 - i)
        k = max(0, (i - 40) // 7 + 1) if d.weekday() >= 5 else 0          # każdy kolejny weekend o 35% wyższy
        jump.append(10.0 * (1.35 ** k) * (1.03 if d.weekday() == 6 else 1.0))
    lf = mk(jump, today); lf.params = dict(lfm.DEFAULT_PARAMS)
    f_off = lf._bias_factor(today + timedelta(days=1), True)
    check("skok weekendów: korekta dla dni wolnych przekracza dawny sufit 1,25", 1.25 < f_off <= 1.5, f_off)
    check("skok weekendów: dni robocze bez zmiany (≈1)", abs(lf._bias_factor(today + timedelta(days=1), False) - 1.0) < 0.1, lf._bias_factor(today + timedelta(days=1), False))
    check("sufit korekty zaniżania to 1,5", lfm.BIAS_MAX_UNDER == 1.5)
    # --- wysokie weekendy nie są odrzucane jako „odstające” (skośność w prawo): prognoza niedzieli nie jest zaniżona
    hi = []
    for i in range(60):
        d = today - timedelta(days=60 - i)
        if d.weekday() < 5:
            hi.append(10.0 + 0.2 * math.sin(i * 2.3))
        else:
            hi.append((15.0 if i >= 46 else 12.0) + 0.5 * math.sin(i * 1.9))        # dwa ostatnie weekendy wyraźnie wyższe
    lf = mk(hi, today); lf.params = dict(lfm.DEFAULT_PARAMS, wd_w=0.0)
    p_sun = lf._model_core(date(2026, 11, 15), today)
    check("wysokie weekendy zostają w modelu: prognoza niedzieli ≥ 14", p_sun >= 14.0, p_sun)
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
