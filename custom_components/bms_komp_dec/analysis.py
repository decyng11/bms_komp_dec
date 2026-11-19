"""Analizy dla zakładki „Zysk i log”: porównanie taryf na własnym poborze (11) i symulacja roczna / zwrot z inwestycji (12).

Wszystko to SZACUNKI z godzinowych koszyków i dziennych kosztów Insights (a nie z faktur): bez opłat stałych,
bez zmiany zachowania EMS przy innej taryfie."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .tariff import TariffProfile, parse_peaks

_LOAD, _PV, _IMP, _EXP, _BCH, _BDIS, _BUY_S, _BUY_T, _SELL_S, _SELL_T, _SOC = range(11)
MIN_DAYS_SIM = 3
FULL_YEAR_DAYS = 330


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


# górne granice ustawień analiz: cena zł/kWh, nakład zł
_CFG_MAX = {"g11": 20.0, "dyn_markup": 20.0, "invest_pv": 5_000_000.0, "invest_batt": 5_000_000.0}


def clean_cfg(raw: dict | None) -> dict[str, Any]:
    """Ustawienia użytkownika (ceny alternatyw, nakłady) — tylko poprawne liczby."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    for k in ("g11", "invest_pv", "invest_batt", "dyn_markup"):
        v = _f(raw.get(k))
        if v is not None and 0 <= v <= _CFG_MAX[k]:      # absurdalne wartości (1e308, inf) odrzucamy zamiast liczyć z nimi
            out[k] = round(v, 4)
    z = raw.get("zone")
    if isinstance(z, dict):
        peak, off = _f(z.get("peak")), _f(z.get("off"))
        if peak is not None and off is not None and 0 < peak <= _CFG_MAX["g11"] and 0 < off <= _CFG_MAX["g11"]:
            txt = str(z.get("windows") or "6-13,15-22")
            peaks, err = parse_peaks(txt)
            if err is None:
                out["zone"] = {"peak": round(peak, 4), "off": round(off, 4), "windows": txt,
                               "weekend_offpeak": bool(z.get("weekend_offpeak", True)),
                               "holiday_offpeak": bool(z.get("holiday_offpeak", True))}
    return out


def tariff_compare(buckets_by_day: dict[str, list], cfg: dict, today: date, days: int = 30) -> dict[str, Any]:
    """Ile zapłaciłbyś za TEN SAM pobór z sieci (godzina po godzinie) przy innej taryfie."""
    cfg = clean_cfg(cfg)
    keys = [(today - timedelta(days=i)).isoformat() for i in range(days, 0, -1)]
    keys = [k for k in keys if k in buckets_by_day and any(x is not None for x in buckets_by_day[k])]
    n_days = len(keys)
    imp_total = actual = 0.0
    alt = {"g11": 0.0, "zone": 0.0, "dyn": 0.0}
    zprof = None
    z = cfg.get("zone")
    if z:
        zprof = TariffProfile(parse_peaks(z["windows"])[0] or (), z["weekend_offpeak"], z["holiday_offpeak"])
    dyn_ok = dyn_n = 0
    for k in keys:
        d = date.fromisoformat(k)
        for h, b in enumerate(buckets_by_day[k]):
            if b is None or b[_IMP] <= 0:
                continue
            imp = b[_IMP]
            buy = _f(b[_BUY_S] / b[_BUY_T]) if b[_BUY_T] else None
            if buy is None:
                continue
            imp_total += imp
            actual += imp * buy
            if "g11" in cfg:
                alt["g11"] += imp * cfg["g11"]
            if zprof is not None:
                alt["zone"] += imp * (z["peak"] if zprof.is_peak(datetime(d.year, d.month, d.day, h)) else z["off"])
            if "dyn_markup" in cfg:
                rce = _f(b[_SELL_S] / b[_SELL_T]) if b[_SELL_T] else None
                dyn_n += 1
                if rce is not None:
                    dyn_ok += 1
                    alt["dyn"] += imp * (max(0.0, rce) + cfg["dyn_markup"])
                else:
                    alt["dyn"] += imp * buy
    scale = 30.0 / n_days if n_days else 0.0
    rows = [{"key": "actual", "name": "Twoja obecna taryfa (rzeczywiste ceny)", "cost": round(actual, 2), "diff": 0.0}]
    if "g11" in cfg:
        rows.append({"key": "g11", "name": f"Jedna stawka (G11) {cfg['g11']:.2f} zł/kWh", "cost": round(alt["g11"], 2),
                     "diff": round(alt["g11"] - actual, 2)})
    if zprof is not None:
        rows.append({"key": "zone", "name": f"Strefowa: szczyt {z['peak']:.2f} / poza {z['off']:.2f} zł/kWh ({z['windows']})",
                     "cost": round(alt["zone"], 2), "diff": round(alt["zone"] - actual, 2)})
    if "dyn_markup" in cfg and dyn_n and dyn_ok / dyn_n >= 0.8:
        rows.append({"key": "dyn", "name": f"Dynamiczna: giełda (RCE) + {cfg['dyn_markup']:.2f} zł/kWh", "cost": round(alt["dyn"], 2),
                     "diff": round(alt["dyn"] - actual, 2)})
    for r in rows:
        r["per_month"] = round(r["cost"] * scale, 2)
        r["diff_month"] = round(r["diff"] * scale, 2)
    best = min(rows, key=lambda r: r["cost"]) if len(rows) > 1 else None
    return {"days": n_days, "import_kwh": round(imp_total, 1), "rows": rows,
            "best": best["key"] if best and best["key"] != "actual" else None, "cfg": cfg,
            "note": "Szacunek: ten sam pobór z sieci co do godziny; bez opłat stałych i bez zmiany zachowania EMS przy innej taryfie."}


MIN_HOURS_NEG = 20            # doba z co najmniej tyloma godzinami danych (jak „pełna doba” w Insights)


def neg_price_day(buckets: list) -> dict[str, float] | None:
    """Godziny z UJEMNĄ ceną sprzedaży / zakupu w jednej dobie (z godzinowych koszyków; tylko prawdziwe ceny godziny).

    sell_cost  — ile realnie dopłacono za eksport w tych godzinach (kWh × |cena|);
    buy_gain   — ile „zarobiono” na poborze z sieci przy ujemnej cenie zakupu;
    nobat_sell_cost / nopv_buy_gain — to samo w scenariuszach symulacji „Samo PV” i „Bez PV” (tłumaczą, czemu
    „Samo PV” może wyjść drożej niż „Bez PV”). None, gdy doba ma za mało danych."""
    out = {"hours": 0, "sell_h": 0, "sell_kwh": 0.0, "sell_cost": 0.0, "buy_h": 0, "buy_kwh": 0.0, "buy_gain": 0.0,
           "nobat_sell_cost": 0.0, "nopv_buy_gain": 0.0}
    for b in buckets:
        if b is None or len(b) < 10:
            continue
        out["hours"] += 1
        buy = b[_BUY_S] / b[_BUY_T] if b[_BUY_T] > 0 else None
        sell = b[_SELL_S] / b[_SELL_T] if b[_SELL_T] > 0 else None
        load, pv = max(0.0, b[_LOAD]), max(0.0, b[_PV])
        if sell is not None and sell < 0:
            out["sell_h"] += 1
            out["sell_kwh"] += max(0.0, b[_EXP])
            out["sell_cost"] += max(0.0, b[_EXP]) * -sell
            out["nobat_sell_cost"] += max(0.0, pv - load) * -sell
        if buy is not None and buy < 0:
            out["buy_h"] += 1
            out["buy_kwh"] += max(0.0, b[_IMP])
            out["buy_gain"] += max(0.0, b[_IMP]) * -buy
            out["nopv_buy_gain"] += load * -buy
    return out if out["hours"] >= MIN_HOURS_NEG else None


def neg_summary(days_buckets: dict[str, list]) -> dict[str, Any] | None:
    """Suma ujemnych cen z wielu dób (klucz = data) + przeliczenie na rok. None, gdy brak pełnych dób."""
    rows = [r for r in (neg_price_day(b) for _k, b in sorted(days_buckets.items())) if r is not None]
    if not rows:
        return None
    m = len(rows)
    tot = {k: sum(r[k] for r in rows) for k in rows[0]}
    k = 365.0 / m
    return {
        "days": m, "sell_days": sum(1 for r in rows if r["sell_h"] > 0), "buy_days": sum(1 for r in rows if r["buy_h"] > 0),
        "sell_h": int(tot["sell_h"]), "sell_kwh": round(tot["sell_kwh"], 2), "sell_cost": round(tot["sell_cost"], 2),
        "buy_h": int(tot["buy_h"]), "buy_kwh": round(tot["buy_kwh"], 2), "buy_gain": round(tot["buy_gain"], 2),
        "nobat_sell_cost": round(tot["nobat_sell_cost"], 2), "nopv_buy_gain": round(tot["nopv_buy_gain"], 2),
        "sell_cost_year": round(tot["sell_cost"] * k, 2), "extrapolated": m < FULL_YEAR_DAYS,
    }


def year_sim(insight_days: dict[str, dict], cfg: dict, avg_buy: float | None) -> dict[str, Any] | None:
    """Cztery scenariusze kosztu energii na pełnych dobach: bez PV i baterii / samo PV / PV + bateria bez planera / z EMS.

    Wynik skalowany do roku; gdy danych jest mało, zaznaczamy, że to ekstrapolacja (sezonowość!)."""
    cfg = clean_cfg(cfg)
    rows = [r for k, r in sorted(insight_days.items()) if isinstance(r, dict) and r.get("complete")]
    n = len(rows)
    if n < MIN_DAYS_SIM:
        return None
    nopv = 0.0
    for r in rows:
        v = _f(r.get("nopv"))
        if v is None:
            load = _f(r.get("load_kwh")) or 0.0
            v = load * avg_buy if avg_buy else None
        if v is None:
            return None
        nopv += v
    nobat = sum(_f(r.get("nobat")) or 0.0 for r in rows)
    simple = sum(_f(r.get("simple")) or 0.0 for r in rows)
    actual = sum(_f(r.get("actual")) or 0.0 for r in rows)
    k = 365.0 / n
    sc = [
        {"key": "nopv", "name": "Bez PV i bez baterii", "period": nopv},
        {"key": "nobat", "name": "Samo PV (bez baterii)", "period": nobat},
        {"key": "simple", "name": "PV + bateria, prosta strategia (bez planera)", "period": simple},
        {"key": "ems", "name": "PV + bateria + EMS (rzeczywiście)", "period": actual},
    ]
    for s in sc:
        s["period"] = round(s["period"], 2)
        s["year"] = round(s["period"] * k, 2)
    pv_year = (nopv - nobat) * k
    batt_year = (nobat - simple) * k
    ems_year = (simple - actual) * k
    out: dict[str, Any] = {
        "days": n, "scenarios": sc, "extrapolated": n < FULL_YEAR_DAYS,
        "savings_year": {"pv": round(pv_year, 2), "battery": round(batt_year, 2), "ems": round(ems_year, 2),
                         "total": round((nopv - actual) * k, 2)},
        "cfg": cfg,
        "note": ("Szacunek z danych godzinowych: " + (f"{n} dób, wynik przeliczony na rok — sezonowość (zima/lato) może mocno zmienić wartość."
                                                          if n < FULL_YEAR_DAYS else f"{n} dób.")),
    }
    pay: dict[str, Any] = {}
    ip, ib = cfg.get("invest_pv"), cfg.get("invest_batt")
    if ip and pv_year > 0:
        pay["pv_years"] = round(ip / pv_year, 1)
    if ib and (batt_year + ems_year) > 0:
        pay["battery_years"] = round(ib / (batt_year + ems_year), 1)
    if ip and ib and (nopv - actual) * k > 0:
        pay["total_years"] = round((ip + ib) / ((nopv - actual) * k), 1)
    if pay:
        out["payback"] = pay
    return out
