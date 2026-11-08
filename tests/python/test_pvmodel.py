"""0.9.1: korekta prognozy PV — współczynnik osobno dla każdego dnia do przodu, kształt godzinowy, korekta „na żywo”,
pomijanie dni z ucięciem PV, zakres niepewności."""
import asyncio, sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import insights as I, scheduler as SCH, runtime as rtm

TODAY = date(2026, 11, 20)


def mk_ins():
    hass = stubs.FakeHass()
    return I.Insights(hass)


def seed_days(ins, n, by_h_ratio, base=10.0):
    """n dni wstecz: prognoza wydana h dni wcześniej = base, wykonanie = base × ratio(h) (h=0 także jako pv_fc)."""
    for i in range(1, n + 1):
        d = (TODAY - timedelta(days=i)).isoformat()
        rec = ins.fc.setdefault(d, {})
        h0 = by_h_ratio.get(0, 1.0)
        rec["pv_fc"] = base
        rec["pv_act"] = round(base * h0, 3)
        rec["pv_fc_by_h"] = {str(h): base for h in by_h_ratio}
        rec["pv_adj_by_h"] = {str(h): round(base * r, 3) for h, r in by_h_ratio.items()}   # „idealna” korekta


async def main():
    # ---------- 1. współczynnik osobno dla każdego horyzontu
    ins = mk_ins()
    # wykonanie liczone względem prognozy h=0; dla innych h wykonanie jest to samo — różnią się wydane prognozy
    for i in range(1, 13):
        d = (TODAY - timedelta(days=i)).isoformat()
        ins.fc[d] = {"pv_fc": 10.0, "pv_act": 8.0, "pv_fc_by_h": {"0": 10.0, "1": 9.0, "3": 16.0}}
    f0 = ins.pv_horizon_factor(0, TODAY)
    f1 = ins.pv_horizon_factor(1, TODAY)
    f3 = ins.pv_horizon_factor(3, TODAY)
    check("h=0: wykonanie/prognoza 0,8", f0[0] == 0.8 and f0[1] == 12, f0)
    check("h=1: prognoza wydana wcześniej 9 → 0,889", abs(f1[0] - 0.889) < 0.002, f1)
    check("h=3: prognoza 16 → 0,5 (dolna granica)", f3[0] == 0.5, f3)
    f2 = ins.pv_horizon_factor(2, TODAY)
    check("h=2 bez własnych danych → współczynnik najbliższego niższego (h=1)", f2[0] == f1[0] and f2[1] == f1[1], f2)
    f6 = ins.pv_horizon_factor(6, TODAY)
    check("h=6 bez danych → z h=3", f6[0] == f3[0], f6)
    check("brak jakichkolwiek danych → 1,0", mk_ins().pv_horizon_factor(4, TODAY)[0] == 1.0)
    check("za mało dni (4) → 1,0", (lambda i: (seed_days(i, 4, {0: 0.5}), i.pv_horizon_factor(0, TODAY)[0])[1])(mk_ins()) == 1.0)

    # ---------- 2. mediana odporna na pojedynczy zepsuty dzień
    ins = mk_ins()
    seed_days(ins, 12, {0: 0.9})
    d = (TODAY - timedelta(days=3)).isoformat()
    ins.fc[d]["pv_act"] = 1.0                 # pojedynczy dzień z awarią pomiaru (0,1)
    fac, n, med = ins.pv_horizon_factor(0, TODAY)
    check("mediana: jeden zepsuty dzień nie ciągnie korekty", abs(med - 0.9) < 0.001 and abs(fac - 0.9) < 0.001, (fac, n, med))

    # ---------- 3. dni z ucięciem PV nie uczą modelu
    ins = mk_ins()
    seed_days(ins, 12, {0: 0.9})
    for i in range(1, 8):                     # 7 z 12 dni ucięte (bateria pełna, brak eksportu)
        ins.fc[(TODAY - timedelta(days=i)).isoformat()].update(pv_act=3.0, pv_lim=0.6)
    fac, n, med = ins.pv_horizon_factor(0, TODAY)
    check("dni z ucięciem pomijane (zostaje 5 dni, ratio 0,9)", n == 5 and abs(med - 0.9) < 0.001, (fac, n, med))

    # ---------- 4. kształt godzinowy: rano za dużo, po południu za mało; suma dnia = współczynnik × surowa
    ins = mk_ins()
    raw = [0.0] * 24
    for h in range(8, 16):
        raw[h] = 1.0
    for i in range(1, 13):
        d = (TODAY - timedelta(days=i)).isoformat()
        ins.fc[d] = {"pv_fc": 8.0, "pv_act": 8.0, "pv_fc_h": list(raw)}
        for h in range(24):
            b = I._blank_bucket()
            b[I.PV] = raw[h] * (0.6 if h < 12 else 1.4) if raw[h] else 0.0
            b[I.SOC] = 50.0
            ins.hours[f"{d}T{h:02d}"] = b
    shape, sd = ins.pv_shape(TODAY)
    check("kształt: rano < 1, po południu > 1", shape[9] < 0.8 and shape[14] > 1.2, (shape[9], shape[14]))
    check("kształt: godziny bez produkcji = 1,0", shape[2] == 1.0 and shape[22] == 1.0)
    check("kształt: liczba dni", sd == 12, sd)
    # mnożniki: suma dnia po korekcie = współczynnik × suma surowa (współczynnik dnia 1,0 → suma bez zmian)
    stubs.CLOCK["now"] = datetime(2026, 11, 20, 5, 0, tzinfo=TZ)
    info = ins.pv_multipliers(1, raw, stubs.CLOCK["now"])
    tot_adj = sum(raw[h] * info["mult"][h] for h in range(24))
    check("mnożniki: suma dnia zachowana (× współczynnik)", abs(tot_adj - sum(raw) * info["factor"]) < 1e-6, (tot_adj, info["factor"]))
    check("mnożniki: kształt przeniesiony (rano mniej, po południu więcej)", info["mult"][9] < info["mult"][14], info["mult"][8:16])

    # ---------- 5. godziny z ucięciem nie uczą kształtu
    ins2 = mk_ins()
    for i in range(1, 13):
        d = (TODAY - timedelta(days=i)).isoformat()
        ins2.fc[d] = {"pv_fc": 8.0, "pv_act": 8.0, "pv_fc_h": list(raw)}
        for h in range(24):
            b = I._blank_bucket()
            b[I.PV] = raw[h] * 0.5 if raw[h] else 0.0
            b[I.SOC] = 100.0 if 11 <= h < 15 else 50.0     # w środku dnia bateria pełna i brak eksportu → ucięte
            ins2.hours[f"{d}T{h:02d}"] = b
    check("ucięte godziny rozpoznane", ins2._limited_hours((TODAY - timedelta(days=1)).isoformat()) == {11, 12, 13, 14})
    sh2, _ = ins2.pv_shape(TODAY)
    check("kształt: ucięte godziny (11–14) zostają neutralne", all(sh2[h] == 1.0 for h in range(11, 15)), sh2[8:16])
    # eksport > 0 = nie ucięte
    b = I._blank_bucket(); b[I.PV] = 1.0; b[I.SOC] = 100.0; b[I.EXP] = 0.8
    ins2.hours["2026-11-10T12"] = b
    check("bateria pełna, ale jest eksport → PV nie było ucięte", 12 not in ins2._limited_hours("2026-11-10"))

    # ---------- 6. korekta „na żywo” (dziś): ostatnie godziny 50% prognozy
    ins3 = mk_ins()
    now = datetime(2026, 11, 20, 13, 5, tzinfo=TZ)
    stubs.CLOCK["now"] = now
    day = TODAY.isoformat()
    for h in (10, 11, 12):
        b = I._blank_bucket(); b[I.PV] = 0.5; b[I.SOC] = 60.0
        ins3.hours[f"{day}T{h:02d}"] = b
    info = ins3.pv_multipliers(0, raw, now)
    check("na żywo: współczynnik ≈ 0,65 (połowa prognozy, waga 0,7)", abs(info["live"] - 0.65) < 0.01, info["live"])
    check("na żywo: godziny, które minęły, bez zmian", info["mult"][10] == 1.0, info["mult"][8:14])
    check("na żywo: bieżąca godzina skorygowana", abs(info["mult"][13] - 0.65) < 0.01, info["mult"][13])
    check("na żywo: wpływ słabnie z odległością", info["mult"][15] > info["mult"][13], (info["mult"][13], info["mult"][15]))
    check("na żywo: jutro bez korekty na żywo", ins3.pv_multipliers(1, raw, now)["live"] == 1.0)
    # za mało godzin → brak korekty
    ins4 = mk_ins()
    b = I._blank_bucket(); b[I.PV] = 0.1; b[I.SOC] = 60.0
    ins4.hours[f"{day}T12"] = b
    check("na żywo: jedna godzina to za mało", ins4.pv_multipliers(0, raw, now)["live"] == 1.0)
    # godziny z ucięciem nie liczą się do korekty na żywo
    ins5 = mk_ins()
    for h in (10, 11, 12):
        b = I._blank_bucket(); b[I.PV] = 0.2; b[I.SOC] = 100.0
        ins5.hours[f"{day}T{h:02d}"] = b
    check("na żywo: ucięte godziny pomijane", ins5.pv_multipliers(0, raw, now)["live"] == 1.0)

    # ---------- 7. zapis prognoz na 7 dni
    ins6 = mk_ins()
    raws = [10, 11, 12, 13, 14, 15, 16]
    adjs = [9, 10, 11, 12, 13, 14, 15]
    check("przed 6:00 bez zapisu", not ins6.snapshot_horizons(datetime(2026, 11, 20, 5, 59, tzinfo=TZ), raws, adjs))
    check("po 6:00 zapis", ins6.snapshot_horizons(datetime(2026, 11, 20, 6, 1, tzinfo=TZ), raws, adjs))
    check("dzień +3 dostał prognozę wydaną 3 dni wcześniej", ins6.fc["2026-11-23"]["pv_fc_by_h"] == {"3": 13.0} and ins6.fc["2026-11-23"]["pv_adj_by_h"] == {"3": 12.0}, ins6.fc["2026-11-23"])
    check("drugi raz tego samego dnia — bez zmian", not ins6.snapshot_horizons(datetime(2026, 11, 20, 12, 0, tzinfo=TZ), [99] * 7, [99] * 7))
    check("następnego dnia dopisuje kolejny horyzont (dzień +3 ma h=2)", ins6.snapshot_horizons(datetime(2026, 11, 21, 7, 0, tzinfo=TZ), raws, adjs)
          and ins6.fc["2026-11-23"]["pv_fc_by_h"]["2"] == 12.0 and ins6.fc["2026-11-23"]["pv_fc_by_h"]["3"] == 13.0)
    check("rekord przyszłego dnia nie psni trafności (brak pv_act)", I.pv_correction(ins6.fc, TODAY)["days"] == 0)

    # ---------- 8. zakres niepewności i trafność po korekcie
    ins7 = mk_ins()
    check("zakres bez historii: wartości domyślne rosną z horyzontem", ins7.pv_spread(0, TODAY) == 0.12 and ins7.pv_spread(6, TODAY) == 0.45)
    seed_days(ins7, 12, {0: 1.0})
    for i in range(1, 13):                    # po korekcie błąd 20% (wykonanie 10, wydane po korekcie 8)
        ins7.fc[(TODAY - timedelta(days=i)).isoformat()].update(pv_act=10.0, pv_adj_by_h={"0": 8.0})
    check("zakres z historii: mediana błędu po korekcie (0,2)", abs(ins7.pv_spread(0, TODAY) - 0.2) < 0.001, ins7.pv_spread(0, TODAY))
    st = ins7.pv_horizon_stats(TODAY)
    check("statystyki: 7 horyzontów", len(st) == 7 and st[0]["h"] == 0 and st[0]["n_adj"] == 12, st[0])
    check("statystyki: błąd po korekcie 20%", st[0]["mape_adj"] == 20.0, st[0])

    # ---------- 9. planer i karta (prawdziwy ScheduleOptimizer)
    PROGS = [("00:00", 25, "Allow Grid"), ("06:00", 25, "Disabled"), ("12:00", 25, "Disabled"), ("18:00", 25, "Disabled"), ("21:00", 25, "Disabled"), ("23:00", 25, "Disabled")]
    pvt = lambda h: 1.0 if 9 <= h < 15 else 0.0
    hass, c, sched = await mk((2026, 11, 20, 21, 22), 45, shutdown=25, load=12, pvt=pvt, progs=PROGS)
    rt = rtm.BmsRuntime(hass, c, sched); c.runtime = rt
    for i in range(1, 13):
        rt.insights.fc[(TODAY - timedelta(days=i)).isoformat()] = {"pv_fc": 10.0, "pv_act": 9.0, "pv_fc_by_h": {"0": 10.0, "1": 10.0}}
    f, n, _m = rt.insights.pv_horizon_factor(1, TODAY)
    check("planer: współczynnik jutra 0,9", f == 0.9, (f, n))
    pv, sun = sched._pv_day(1)
    check("planer: godzinowa prognoza jutra × 0,9", abs(pv[10] - 0.9) < 0.001, pv[8:16])
    S = hass.states
    S.set("number.bms_pv_plan_pessimism_pct", 100)
    pv_p, _ = sched._pv_day(1)
    check("ostrożność 100%: bez p10 Solcast używa typowego błędu horyzontu (h=1: 0,18)", abs(pv_p[10] - 0.9 * (1 - 0.18)) < 0.002, pv_p[10])
    S.set("number.bms_pv_plan_pessimism_pct", 50)
    pv_h, _ = sched._pv_day(1)
    check("ostrożność 50%: pół drogi", abs(pv_h[10] - 0.9 * (1 - 0.09)) < 0.002, pv_h[10])
    S.set("number.bms_pv_plan_pessimism_pct", 0)
    S.set("switch.bms_pv_forecast_correction", "off")
    pv_off, _ = sched._pv_day(1)
    check("przełącznik korekty wyłączony → surowa prognoza", abs(pv_off[10] - 1.0) < 1e-9, pv_off[10])
    S.set("switch.bms_pv_forecast_correction", "on")

    # karta: sumy 7 dni po korekcie, surowa wartość, zakres
    out = {"pv_hourly_today": [None] * 24, "pv_hourly_tomorrow": [1.0 if 9 <= h < 15 else 0.0 for h in range(24)],
           "pv_daily": [{"date": (TODAY + timedelta(days=i)).isoformat(), "kwh": 10.0} for i in range(7)]}
    out["pv_daily"][3].update(lo=6.0, hi=13.0)
    out["pv_daily"][5]["kwh"] = None
    sched._pv_adjust_payload(out)
    d1 = out["pv_daily"][1]
    check("karta: jutro = surowa × 0,9", d1["raw"] == 10.0 and d1["kwh"] == 9.0 and d1["factor"] == 0.9, d1)
    check("karta: zakres z historii (±18% dla h=1)", d1["lo"] == round(9.0 * 0.82, 2) and d1["hi"] == round(9.0 * 1.18, 2) and d1["range"] == "szac.", d1)
    d3 = out["pv_daily"][3]
    check("karta: zakres ze Solcast przeskalowany współczynnikiem (h=3 → h=1 fallback 0,9)", d3["lo"] == 5.4 and d3["hi"] == 11.7 and d3["range"] == "solcast", d3)
    check("karta: brak prognozy zostaje brakiem", out["pv_daily"][5]["kwh"] is None and out["pv_daily"][5]["raw"] is None)
    check("karta: godzinowa prognoza jutra po korekcie", abs(out["pv_hourly_tomorrow_adj"][10] - 0.9) < 0.001, out["pv_hourly_tomorrow_adj"][9:12])
    S.set("switch.bms_pv_forecast_correction", "off")
    out2 = {"pv_hourly_today": None, "pv_hourly_tomorrow": None, "pv_daily": [{"date": "2026-11-20", "kwh": 10.0}]}
    sched._pv_adjust_payload(out2)
    check("karta: korekta wyłączona → bez zmian, raw = kwh", out2["pv_daily"][0]["kwh"] == 10.0 and out2["pv_daily"][0]["raw"] == 10.0, out2["pv_daily"][0])
    S.set("switch.bms_pv_forecast_correction", "on")

    # sensor rezerwy niesie sumy po korekcie, a snapshot zapisuje surowe i skorygowane
    from custom_components.bms_komp_dec import sensor as SN
    check("runtime: snapshot 7 dni używa pv_card_payload_raw", hasattr(sched, "pv_card_payload_raw") and hasattr(rt, "_pv_horizon_snapshot"))
    stubs.CLOCK["now"] = datetime(2026, 11, 20, 7, 0, tzinfo=TZ)
    rt._pv_horizon_snapshot(stubs.CLOCK["now"])
    rec = rt.insights.fc.get("2026-11-20") or {}
    check("runtime: snapshot dnia 0 zapisany po 6:00", "0" in (rec.get("pv_fc_by_h") or {}), rec)

    print(f"PVMODEL PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
