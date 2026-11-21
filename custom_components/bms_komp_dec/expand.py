"""Ocena opłacalności rozbudowy: „gdybyś dołożył X kWh baterii albo Y kWp paneli, zarobiłbyś około Z zł rocznie”.

To SZACUNEK rzędu wielkości z własnych danych z ostatnich dób (sezon wpływa na wynik — zimą PV wypadnie gorzej, latem lepiej),
bez dotacji, podatków i zmiany cen. Czyste funkcje, bez HA."""
from __future__ import annotations

import math
from typing import Any

EFF = 0.9
MIN_DAYS = 14
MAX_YEARS = 60


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _pay(cost: float, annual: float) -> float | None:
    if annual <= 0:
        return None
    y = cost / annual
    return round(y, 1) if y <= MAX_YEARS else None


def battery(days: Any, add_kwh: Any, cost_per_kwh: Any, avg_buy: Any, avg_sell: Any, wear_per_kwh: Any = 0.0) -> dict[str, Any] | None:
    """Dołożona bateria: energię wysłaną do sieci (po cenie sprzedaży) magazynujemy i używamy zamiast zakupu (po cenie zakupu).

    days: lista dobowych {'exp': kWh do sieci}. Wartość 1 kWh = sprawność × cena zakupu − cena sprzedaży − zużycie baterii."""
    x, c, pb, ps, w = _num(add_kwh), _num(cost_per_kwh), _num(avg_buy), _num(avg_sell), _num(wear_per_kwh) or 0.0
    if x is None or c is None or pb is None or ps is None or not (0 < x <= 1000) or c < 0 or not isinstance(days, (list, tuple)):
        return None
    exp = [max(0.0, _num(d.get("exp")) or 0.0) for d in days if isinstance(d, dict)]
    if len(exp) < MIN_DAYS:
        return None
    unit = EFF * pb - ps - max(0.0, w)
    shifted = sum(min(x, e) for e in exp) * EFF
    per_year = (sum(min(x, e) for e in exp) / len(exp)) * 365.0
    annual = per_year * unit
    cost = x * c
    return {"add_kwh": x, "cost": round(cost, 0), "unit_value": round(unit, 2), "shifted_kwh_year": round(per_year * EFF, 0),
            "annual": round(annual, 0), "payback_years": _pay(cost, annual), "days": len(exp),
            "note": None if unit > 0 else "Przy tych cenach opłaca się raczej sprzedawać energię niż ją magazynować."}


def pv(days: Any, add_kwp: Any, now_kwp: Any, cost_per_kwp: Any, avg_buy: Any, avg_sell: Any) -> dict[str, Any] | None:
    """Dołożone panele: produkcja rośnie proporcjonalnie do mocy; część zużyta w domu liczymy po cenie zakupu, resztę po cenie sprzedaży.

    days: lista dobowych {'pv', 'exp' [kWh]}; now_kwp — obecna moc instalacji (EMS jej nie zna, podaje użytkownik)."""
    y, n, c, pb, ps = _num(add_kwp), _num(now_kwp), _num(cost_per_kwp), _num(avg_buy), _num(avg_sell)
    if None in (y, n, c, pb, ps) or not (0 < y <= 1000) or not (0 < n <= 1000) or c < 0 or not isinstance(days, (list, tuple)):
        return None
    rows = [d for d in days if isinstance(d, dict) and _num(d.get("pv")) is not None]
    if len(rows) < MIN_DAYS:
        return None
    pv_sum = sum(max(0.0, _num(d["pv"])) for d in rows)
    exp_sum = sum(max(0.0, _num(d.get("exp")) or 0.0) for d in rows)
    if pv_sum < 1.0:
        return None
    self_share = min(1.0, max(0.0, (pv_sum - exp_sum) / pv_sum))
    extra_year = pv_sum / len(rows) * 365.0 * (y / n)
    unit = self_share * pb + (1.0 - self_share) * ps
    annual = extra_year * unit
    cost = y * c
    return {"add_kwp": y, "cost": round(cost, 0), "extra_kwh_year": round(extra_year, 0), "self_share_pct": round(self_share * 100.0),
            "unit_value": round(unit, 2), "annual": round(annual, 0), "payback_years": _pay(cost, annual), "days": len(rows),
            "note": "Zakłada, że więcej PV zużywasz w domu w tej samej proporcji co dziś; przy dużej nadwyżce więcej pójdzie do sieci."}
