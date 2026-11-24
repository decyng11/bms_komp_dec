"""Porównanie rok do roku: ostatnie 30 dni z tymi samymi 30 dniami sprzed roku (księga rozliczeń, ledger.py)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

WINDOW = 30
MIN_DAYS = 15          # tyle dni z danymi w okresie sprzed roku, żeby porównanie miało sens
FIELDS = ("revenue", "cost", "net", "import_kwh", "export_kwh")


def _sum(days: dict[str, dict[str, float]], start: date, n: int) -> tuple[dict[str, float], int]:
    out = {f: 0.0 for f in FIELDS}
    have = 0
    for i in range(n):
        row = days.get((start + timedelta(days=i)).isoformat())
        if not row:
            continue
        have += 1
        for f in ("revenue", "cost", "import_kwh", "export_kwh"):
            out[f] += float(row.get(f, 0.0) or 0.0)
    out["net"] = out["revenue"] - out["cost"]
    return {k: round(v, 2) for k, v in out.items()}, have


def compare(days: dict[str, dict[str, float]], today: date) -> dict[str, Any]:
    """Zawsze zwraca słownik: available=False z opisem, kiedy dane sprzed roku się pojawią, albo dwa okresy i różnice."""
    keys = sorted(k for k, v in (days or {}).items() if v)
    cur_start = today - timedelta(days=WINDOW - 1)
    prev_start = cur_start - timedelta(days=365)
    cur, cur_n = _sum(days or {}, cur_start, WINDOW)
    prev, prev_n = _sum(days or {}, prev_start, WINDOW)
    base = {"window": WINDOW, "cur_from": cur_start.isoformat(), "prev_from": prev_start.isoformat(), "cur_days": cur_n, "prev_days": prev_n}
    if prev_n < MIN_DAYS:
        try:
            first = date.fromisoformat(keys[0]) if keys else today
        except ValueError:
            first = today
        ready = first + timedelta(days=365 + WINDOW // 2)
        return {**base, "available": False, "ready_from": max(ready, today).isoformat() if ready > today else None,
                "note": "Za mało danych sprzed roku. Porównanie pojawi się, gdy księga rozliczeń obejmie ten sam okres rok temu"
                        + (f" (około {ready.isoformat()})." if ready > today else ".")}
    diff = {f: round(cur[f] - prev[f], 2) for f in FIELDS}
    pct = {f: (round((cur[f] - prev[f]) / abs(prev[f]) * 100.0, 1) if abs(prev[f]) >= 0.5 else None) for f in FIELDS}
    return {**base, "available": True, "cur": cur, "prev": prev, "diff": diff, "pct": pct,
            "note": "Okres porównywany: ostatnie 30 dni wobec tych samych 30 dni rok wcześniej. Ceny i taryfy mogły się zmienić, więc różnica nie jest tylko zasługą EMS."
                    + (f" Dane z {cur_n}/{WINDOW} dni teraz i {prev_n}/{WINDOW} dni rok temu." if cur_n < WINDOW or prev_n < WINDOW else "")}
