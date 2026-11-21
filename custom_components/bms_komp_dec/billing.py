"""Rachunek: prognoza bilansu z siecią do końca miesiąca, cel miesięczny, rozbicie miesiąca i „skarbonka” (zwrot z instalacji).

Czyste funkcje (bez Home Assistanta). Wszystko to SZACUNKI z księgi zysków (bilans z siecią), bez opłat stałych i dystrybucyjnych,
których EMS nie zna — przy celu miesięcznym warto o tym pamiętać."""
from __future__ import annotations

import math
from calendar import monthrange
from datetime import date, timedelta
from typing import Any

MIN_DAYS = 3             # tyle pełnych dób potrzeba do prognozy
AVG_WINDOW = 14          # średnia z tylu ostatnich pełnych dób
WARN_SHARE = 0.9         # prognozowany wydatek ≥ 90% celu = ostrzeżenie
MAX_YEARS = 50           # dalszych dat zwrotu nie podajemy
GOAL_MAX = 1_000_000.0


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _day(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _q(sorted_vals: list[float], p: float) -> float:
    """Kwantyl (interpolacja liniowa) z posortowanej listy."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = p * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(len(sorted_vals) - 1, lo + 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def zl(v: float | None, sign: bool = False) -> str:
    if v is None:
        return "—"
    return (f"{v:+.2f}" if sign else f"{v:.2f}").replace(".", ",") + " zł"


def forecast(days: Any, today: date, day_fraction: float = 0.0) -> dict[str, Any] | None:
    """Prognoza bilansu z siecią (przychód − koszt) za bieżący miesiąc.

    days: {data ISO: bilans doby [zł]} z księgi. Dziś jest liczone do „na razie”, ale NIE do średniej (doba niepełna).
    Przedział to kwartyle dobowego bilansu z ostatnich dób, pomnożone przez pozostałe doby."""
    if not isinstance(days, dict) or not isinstance(today, date):
        return None
    mtd = 0.0
    hist: list[float] = []
    for k, v in days.items():
        d, n = _day(k), _num(v)
        if d is None or n is None:
            continue
        if d.year == today.year and d.month == today.month and d <= today:
            mtd += n
        if today - timedelta(days=AVG_WINDOW) <= d < today:
            hist.append(n)
    if len(hist) < MIN_DAYS:
        return None
    hist.sort()
    avg = sum(hist) / len(hist)
    dim = monthrange(today.year, today.month)[1]
    frac = min(1.0, max(0.0, _num(day_fraction) or 0.0))
    remaining = (dim - today.day) + (1.0 - frac)
    return {"mtd": round(mtd, 2), "avg_day": round(avg, 2), "remaining_days": round(remaining, 2), "days_used": len(hist),
            "projected": round(mtd + avg * remaining, 2),
            "low": round(mtd + _q(hist, 0.25) * remaining, 2), "high": round(mtd + _q(hist, 0.75) * remaining, 2)}


def goal_status(fc: dict[str, Any] | None, goal: Any) -> dict[str, Any] | None:
    """Cel miesięczny: „wydam na prąd (koszt netto) najwyżej X zł”. None = cel wyłączony (0/brak) albo brak prognozy.

    Bilans dodatni (więcej sprzedaży niż zakupu) to wydatek 0 zł."""
    g = _num(goal)
    if g is None or g <= 0 or g > GOAL_MAX or not isinstance(fc, dict) or fc.get("projected") is None:
        return None
    spent = max(0.0, -float(fc["mtd"]))
    proj = max(0.0, -float(fc["projected"]))
    worst = max(0.0, -float(fc["low"])) if fc.get("low") is not None else proj
    if spent > g:
        status = "over_now"
    elif proj > g:
        status = "over"
    elif proj >= WARN_SHARE * g:
        status = "warn"
    else:
        status = "ok"
    text = {
        "over_now": f"Cel {g:.0f} zł już przekroczony: wydano {spent:.0f} zł.",
        "over": f"Przy obecnym tempie wydasz ok. {proj:.0f} zł — powyżej celu {g:.0f} zł (na razie {spent:.0f} zł).",
        "warn": f"Prognoza {proj:.0f} zł jest blisko celu {g:.0f} zł (na razie {spent:.0f} zł).",
        "ok": f"Prognoza {proj:.0f} zł mieści się w celu {g:.0f} zł (na razie {spent:.0f} zł).",
    }[status]
    return {"goal": round(g, 2), "spent": round(spent, 2), "projected_spent": round(proj, 2), "worst_spent": round(worst, 2),
            "status": status, "pct": round(proj / g * 100.0), "text": text}


def _c(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def breakdown(rep: Any) -> list[dict[str, str]]:
    """Rozbicie miesiąca (wynik report.monthly_report) na pozycje do wyświetlenia: [{k, v}]."""
    if not isinstance(rep, dict) or not rep.get("days_with_data"):
        return []
    out: list[dict[str, str]] = []
    imp, exp_ = _num(rep.get("import_kwh")), _num(rep.get("export_kwh"))
    cost, rev, net = _num(rep.get("cost")), _num(rep.get("revenue")), _num(rep.get("net"))
    buy_pr, sell_pr = _num(rep.get("avg_buy_price")), _num(rep.get("avg_sell_price"))
    if imp is not None and cost is not None:
        out.append({"k": "Kupiłeś z sieci", "v": f"{_c(imp)} kWh za {zl(cost)}" + (f" (śr. {_c(buy_pr, 2)} zł/kWh)" if buy_pr is not None else "")})
    if exp_ is not None and rev is not None:
        out.append({"k": "Sprzedałeś do sieci", "v": f"{_c(exp_)} kWh za {zl(rev)}" + (f" (śr. {_c(sell_pr, 2)} zł/kWh)" if sell_pr is not None else "")})
    if net is not None:
        out.append({"k": "Bilans z siecią", "v": zl(net, True)})
    load = _num(rep.get("load_kwh"))
    if load is not None and buy_pr is not None:
        out.append({"k": "Bez PV i baterii", "v": f"dom {_c(load, 0)} kWh × {_c(buy_pr, 2)} zł = {zl(load * buy_pr)}"})
    sv = _num(rep.get("saving_estimate"))
    if sv is not None:
        out.append({"k": "Oszczędność (szacunek)", "v": zl(sv)})
    return out


def piggy(saved: Any, invest: Any, days_counted: Any, today: date) -> dict[str, Any] | None:
    """„Skarbonka”: ile już zaoszczędzono względem domu bez instalacji, jaki to procent nakładu i kiedy się zwróci.

    saved — suma „vs_nobat” z oszczędności (zł), invest — nakład na PV + baterię (zł; brak = tylko suma), days_counted — dób z danymi."""
    s, n = _num(saved), _num(days_counted)
    if s is None or n is None or n < 1 or not isinstance(today, date):
        return None
    inv = _num(invest)
    out: dict[str, Any] = {"saved": round(s, 2), "days": int(n), "per_day": round(s / n, 2), "invest": None, "pct": None,
                           "payback_date": None, "years_left": None}
    if inv is None or inv <= 0:
        return out
    out["invest"] = round(inv, 2)
    out["pct"] = round(max(0.0, s) / inv * 100.0, 1)
    if s >= inv:
        out["payback_date"], out["years_left"] = "zwrócone", 0.0
        return out
    if s / n > 0 and n >= 14:
        left_days = (inv - s) / (s / n)
        if left_days <= MAX_YEARS * 365.0:
            out["years_left"] = round(left_days / 365.0, 1)
            out["payback_date"] = (today + timedelta(days=int(left_days))).isoformat()
    return out
