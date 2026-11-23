"""Prognoza kosztu prądu na dziś i na jutro: dotychczasowy bilans + reszta dnia z planu, a jutro wprost z planu (znamy ceny).
Prognoza do końca miesiąca jest osobno w „Rachunek i cel” (billing.py). Czyste funkcje, bez Home Assistanta.

Znak: KOSZT dodatni = wydajesz (zakup − sprzedaż), ujemny = zarabiasz. To SZACUNEK z planu, który nie zna strat ani opłat stałych."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

MIN_PLAN_HOURS = 20      # plan na całą jutrzejszą dobę liczy się, gdy ma tyle godzin


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _plan_cost(rows: Any, day: date) -> tuple[float | None, int]:
    """(suma kosztu godzin planu z danej doby, liczba godzin)."""
    tot, n = 0.0, 0
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and r.get("day") == day.isoformat():
            c = _num(r.get("cost"))
            if c is not None:
                tot += c
                n += 1
    return (round(tot, 2), n) if n else (None, 0)


def forecast(ledger_days: dict[str, Any], plan_rows: Any, today: date) -> dict[str, Any]:
    """`ledger_days`: {data: {revenue, cost, ...}} z księgi; `plan_rows`: wiersze tabeli planu (pola day i cost)."""
    v = ledger_days.get(today.isoformat()) if isinstance(ledger_days, dict) else None
    rev, cst = (_num(v.get("revenue")), _num(v.get("cost"))) if isinstance(v, dict) else (None, None)
    so_far = 0.0 if rev is None or cst is None else cst - rev
    rest, rest_n = _plan_cost(plan_rows, today)
    tom, tom_n = _plan_cost(plan_rows, today + timedelta(days=1))
    return {"today": {"so_far": round(so_far, 2), "rest_plan": rest, "total": None if rest is None else round(so_far + rest, 2), "plan_hours": rest_n},
            "tomorrow": {"plan": tom if tom_n >= MIN_PLAN_HOURS else None, "plan_hours": tom_n},
            "note": "Szacunek z planu: koszt dodatni = wydajesz, ujemny = zarabiasz; bez strat i opłat stałych."}
