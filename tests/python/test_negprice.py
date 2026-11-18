"""Ujemne ceny: liczniki godzin z ujemną ceną sprzedaży / zakupu i ich koszt (Zysk → symulacja), spójność z day_costs, payload analizy."""
import asyncio, sys
from datetime import timedelta
import common
sys.path.insert(0, ".")
from common import *   # noqa
from custom_components.bms_komp_dec import analysis, insights as I
from homeassistant.util import dt as dt_util

LOAD, PV, IMP, EXP, BCH, BDIS, BUY_S, BUY_T, SELL_S, SELL_T, SOC = range(11)


def bk(load=0.5, pv=0.0, imp=None, exp=None, buy=0.8, sell=0.3):
    """Koszyk godzinowy: ceny jako średnia ważona czasem (suma = cena × 3600 s)."""
    net = load - pv
    imp = max(0.0, net) if imp is None else imp
    exp = max(0.0, -net) if exp is None else exp
    b = [load, pv, imp, exp, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 50.0]
    if buy is not None:
        b[BUY_S], b[BUY_T] = buy * 3600.0, 3600.0
    if sell is not None:
        b[SELL_S], b[SELL_T] = sell * 3600.0, 3600.0
    return b


def day(neg_sell=(), neg_buy=(), hours=24, sell_price=-0.2, buy_price=-0.1):
    out = []
    for h in range(24):
        if h >= hours:
            out.append(None)
        elif h in neg_sell:
            out.append(bk(load=0.5, pv=4.0, sell=sell_price))          # eksport 3,5 kWh po ujemnej cenie
        elif h in neg_buy:
            out.append(bk(load=1.5, pv=0.0, buy=buy_price))            # pobór 1,5 kWh po ujemnej cenie zakupu
        else:
            out.append(bk())
    return out


async def main():
    # ---------------------------------------------------------------- jedna doba
    r = analysis.neg_price_day(day(neg_sell=(11, 12, 13)))
    check("doba: 3 godziny z ujemną ceną sprzedaży", r and r["sell_h"] == 3 and r["buy_h"] == 0, r)
    check("doba: eksport w tych godzinach = 3 × 3,5 kWh", abs(r["sell_kwh"] - 10.5) < 1e-6, r)
    check("doba: dopłata do eksportu = 10,5 kWh × 0,2 zł", abs(r["sell_cost"] - 2.1) < 1e-6, r)
    check("doba: w scenariuszu „Samo PV” koszt taki sam (bez baterii eksport ten sam)", abs(r["nobat_sell_cost"] - 2.1) < 1e-6, r)

    r = analysis.neg_price_day(day(neg_buy=(2, 3)))
    check("doba: 2 godziny z ujemną ceną zakupu", r and r["buy_h"] == 2 and r["sell_h"] == 0, r)
    check("doba: przychód z poboru = 2 × 1,5 kWh × 0,1 zł", abs(r["buy_gain"] - 0.3) < 1e-6 and abs(r["buy_kwh"] - 3.0) < 1e-6, r)
    check("doba: w scenariuszu „Bez PV” przychód z całego zużycia", abs(r["nopv_buy_gain"] - 0.3) < 1e-6, r)

    r = analysis.neg_price_day(day())
    check("doba bez ujemnych cen: same zera, ale doba policzona", r and r["sell_h"] == 0 and r["buy_h"] == 0 and r["hours"] == 24, r)
    check("doba z < 20 godzin danych: nie liczymy (None)", analysis.neg_price_day(day(neg_sell=(1,), hours=15)) is None)
    check("same puste koszyki: None", analysis.neg_price_day([None] * 24) is None)

    # godzina bez ceny nie jest ujemną ceną (brak danych ≠ ujemna cena)
    nb = day(neg_sell=(11,)); nb[11][SELL_T] = 0.0; nb[11][SELL_S] = 0.0
    r = analysis.neg_price_day(nb)
    check("godzina bez ceny sprzedaży nie jest liczona jako ujemna", r and r["sell_h"] == 0, r)
    zero = day(); zero[10] = bk(sell=0.0, buy=0.0)
    r = analysis.neg_price_day(zero)
    check("cena równa 0 to nie ujemna cena", r and r["sell_h"] == 0 and r["buy_h"] == 0, r)
    bad = day(); bad[5] = [0.0] * 3
    check("uszkodzony koszyk (za krótki) jest pomijany bez błędu", analysis.neg_price_day(bad) is not None)

    # ---------------------------------------------------------------- suma i przeliczenie na rok
    t = dt_util.now().date()
    dd = {(t - timedelta(days=i + 1)).isoformat(): day(neg_sell=(11, 12)) if i < 2 else day() for i in range(4)}
    s = analysis.neg_summary(dd)
    check("suma: 4 doby, 2 z ujemną sprzedażą", s and s["days"] == 4 and s["sell_days"] == 2 and s["buy_days"] == 0, s)
    check("suma: 4 godziny i dopłata 2 × 2 × 3,5 × 0,2 = 2,8 zł", s["sell_h"] == 4 and abs(s["sell_cost"] - 2.8) < 0.01, s)
    check("suma: rocznie = okres × 365/4, ekstrapolacja", abs(s["sell_cost_year"] - 2.8 * 365 / 4) < 0.1 and s["extrapolated"] is True, s)
    check("suma: brak dób → None", analysis.neg_summary({}) is None)
    check("suma: same niepełne doby → None", analysis.neg_summary({"2026-11-01": day(hours=10), "2026-11-02": [None] * 24}) is None)

    # ---------------------------------------------------------------- spójność z day_costs: dlaczego „Samo PV” > „Bez PV”
    bks = day(neg_sell=(10, 11, 12, 13, 14, 15))
    for h in (10, 11, 12, 13, 14, 15):                        # wysokie PV, mało zużycia, ujemna sprzedaż, tania sieć
        bks[h] = bk(load=0.2, pv=5.0, buy=0.05, sell=-0.6)
    dc = I.day_costs(bks, cap_kwh=10.0, eff=0.9, floor_pct=10.0, max_chg_kw=5.0, max_dis_kw=5.0, soc0=50.0)
    ng = analysis.neg_price_day(bks)
    check("paradoks: przy ujemnej cenie sprzedaży „Samo PV” wychodzi drożej niż „Bez PV”", dc["nobat"] > dc["nopv"], (dc["nobat"], dc["nopv"]))
    check("paradoks: liczniki to wykrywają (są godziny z ujemną ceną)", ng["sell_h"] == 6 and ng["nobat_sell_cost"] > dc["nobat"] - dc["nopv"] > 0, (ng, dc))
    ok_day = I.day_costs(day(), cap_kwh=10.0, eff=0.9, floor_pct=10.0, max_chg_kw=5.0, max_dis_kw=5.0, soc0=50.0)
    check("bez ujemnych cen paradoksu nie ma", ok_day["nobat"] <= ok_day["nopv"] + 1e-9, ok_day)

    # ---------------------------------------------------------------- payload analizy z runtime
    hass, c, opt, rt = build(); S = hass.states
    pl = rt.analysis_payload()
    check("payload bez danych: neg=None, reakcja wyłączona, próg 0", pl["neg"] is None and pl["neg_reaction"] is False and pl["neg_threshold"] == 0.0, {k: pl[k] for k in ("neg", "neg_reaction", "neg_threshold")})
    today = dt_util.now().date()
    for i in range(1, 4):
        d = (today - timedelta(days=i)).isoformat()
        for h, b in enumerate(day(neg_sell=(12,))):
            if b is not None:
                rt.insights.hours[f"{d}T{h:02d}"] = b
    S.set("switch.bms_negative_price_reaction", "on"); S.set("number.bms_low_price_threshold", "0.05")
    pl = rt.analysis_payload()
    check("payload: liczniki z godzinowych koszyków (3 doby × 1 h)", pl["neg"] and pl["neg"]["days"] == 3 and pl["neg"]["sell_h"] == 3, pl["neg"])
    check("payload: stan reakcji na ujemne ceny i próg", pl["neg_reaction"] is True and abs(pl["neg_threshold"] - 0.05) < 1e-9, (pl["neg_reaction"], pl["neg_threshold"]))
    print(f"NEGPRICE PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
