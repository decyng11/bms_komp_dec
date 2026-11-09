"""Wyliczenia pomocnicze do karty i podsumowań: koszt „bez PV i baterii”, skąd energia dla domu, pobór w drogich godzinach.

Wszystko to SZACUNKI z dziennych liczników (BatteryStats.days: pv, load, imp, exp, chg, dis) i księgi rozliczeń (Ledger.days)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

SCOPES = ("day", "week", "month", "prev_month", "year", "total")


def prev_month_prefix(d: date) -> str:
    last = d.replace(day=1) - timedelta(days=1)
    return f"{last.year:04d}-{last.month:02d}-"


def _keys(days: dict, d: date, scope: str, start: date | None = None) -> list[str]:
    if scope == "week":
        start = start or (d - timedelta(days=d.weekday()))        # tydzień: od poniedziałku do dziś
        return [k for k in days if start.isoformat() <= k <= d.isoformat()]
    if scope == "prev_month":
        pre = prev_month_prefix(d)
        return [k for k in days if k.startswith(pre)]
    if scope == "year":
        return [k for k in days if k.startswith(f"{d.year:04d}-")]
    if scope == "day":
        return [d.isoformat()] if d.isoformat() in days else []
    if scope == "month":
        pre = f"{d.year:04d}-{d.month:02d}-"
        return [k for k in days if k.startswith(pre)]
    return list(days)


def _sum(days: dict, keys: list[str], f: str) -> tuple[float, int]:
    vals = [days[k][f] for k in keys if isinstance(days[k].get(f), (int, float))]
    return sum(vals), len(vals)


def savings(ledger, stats, d: date, scope: str, start: date | None = None) -> dict[str, Any]:
    """Ile kosztowałby prąd zużyty w domu bez PV i baterii (zużycie × średnia cena zakupu) i ile z tego zaoszczędzono.

    Średnia cena zakupu: z wybranego okresu, a gdy w nim nie było importu (np. dziś do tej pory) — z miesiąca, potem z całości.
    Opłat stałych nie uwzględniamy."""
    lk = _keys(ledger.days, d, scope, start)
    sk = _keys(stats.days, d, scope, start)
    load, n_load = _sum(stats.days, sk, "load")
    rev, _ = _sum(ledger.days, lk, "revenue")
    cost, _ = _sum(ledger.days, lk, "cost")
    avg = None
    for sc in (scope, "month", "total"):
        if sc == "week" and start is None:
            continue
        k2 = _keys(ledger.days, d, sc, start)
        imp, _ = _sum(ledger.days, k2, "import_kwh")
        cst, _ = _sum(ledger.days, k2, "cost")
        if imp > 0.5 and cst > 0:
            avg = cst / imp
            break
    if avg is None or n_load == 0 or load <= 0.05:
        return {"without_cost": None, "actual_cost": round(cost - rev, 2), "saving": None, "load_kwh": round(load, 2) if n_load else None,
                "avg_buy": round(avg, 3) if avg else None}
    without = load * avg
    actual = cost - rev
    return {"without_cost": round(without, 2), "actual_cost": round(actual, 2), "saving": round(without - actual, 2),
            "load_kwh": round(load, 2), "avg_buy": round(avg, 3)}


def split(stats, d: date, scope: str, start: date | None = None) -> dict[str, Any] | None:
    """Skąd energia dla domu: z sieci, z baterii, bezpośrednio z PV (kWh i %). Szacunek: import mógł też ładować baterię,
    więc udział sieci bywa zawyżony, a PV — zaniżony."""
    sk = _keys(stats.days, d, scope, start)
    load, n = _sum(stats.days, sk, "load")
    if not n or load <= 0.05:
        return None
    imp, _ = _sum(stats.days, sk, "imp")
    dis, _ = _sum(stats.days, sk, "dis")
    grid = min(max(imp, 0.0), load)
    batt = min(max(dis, 0.0), load - grid)
    pv = max(0.0, load - grid - batt)
    return {"load_kwh": round(load, 2), "grid_kwh": round(grid, 2), "battery_kwh": round(batt, 2), "pv_kwh": round(pv, 2),
            "grid_pct": round(grid / load * 100.0), "battery_pct": round(batt / load * 100.0),
            "pv_pct": max(0, 100 - round(grid / load * 100.0) - round(batt / load * 100.0))}


def tariff_split(ledger, d: date, scope: str, start: date | None = None) -> dict[str, Any] | None:
    """Pobór z sieci w drogich (szczyt wg taryfy) i tanich godzinach (kWh i %)."""
    lk = _keys(ledger.days, d, scope, start)
    imp, _ = _sum(ledger.days, lk, "import_kwh")
    if imp <= 0.05:
        return None
    pk = min(imp, _sum(ledger.days, lk, "peak_import_kwh")[0])
    return {"import_kwh": round(imp, 2), "peak_kwh": round(pk, 2), "offpeak_kwh": round(imp - pk, 2),
            "peak_pct": round(pk / imp * 100.0), "offpeak_pct": 100 - round(pk / imp * 100.0)}


def bundle(ledger, stats, d: date) -> dict[str, Any]:
    """Wszystkie trzy wyliczenia dla dnia / miesiąca / całości — atrybut `extras` sensora bilansu."""
    return {sc: {"savings": savings(ledger, stats, d, sc), "split": split(stats, d, sc), "tariff": tariff_split(ledger, d, sc)}
            for sc in SCOPES}


def lines(ledger, stats, d: date, scope: str, start: date | None = None) -> list[str]:
    """Linie tekstowe do powiadomień (podsumowanie dnia / tygodnia)."""
    out: list[str] = []
    sv = savings(ledger, stats, d, scope, start)
    if sv["saving"] is not None:
        out.append(f"Bez PV i baterii zapłaciłbyś około {sv['without_cost']:.2f} zł, a koszt netto to {sv['actual_cost']:.2f} zł — "
                   f"oszczędność około {sv['saving']:.2f} zł (szacunek)".replace(".", ","))
    sp = split(stats, d, scope, start)
    if sp:
        out.append(f"Skąd energia dla domu: PV {sp['pv_pct']}%, bateria {sp['battery_pct']}%, sieć {sp['grid_pct']}% ({sp['load_kwh']:.1f} kWh)".replace(".", ","))
    tf = tariff_split(ledger, d, scope, start)
    if tf:
        out.append(f"Pobór z sieci: drogie godziny {tf['peak_kwh']:.1f} kWh ({tf['peak_pct']}%), tanie {tf['offpeak_kwh']:.1f} kWh".replace(".", ","))
    return out
