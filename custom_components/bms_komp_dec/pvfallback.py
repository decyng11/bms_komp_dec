"""Zapasowa prognoza PV: gdy nie ma Solcast ani Forecast.Solar, plan zamiast „słońca nie będzie” dostaje typowy dzień z ostatnich dni.

Czyste funkcje (bez Home Assistanta). Wejście: produkcja PV w kWh na godzinę z ostatnich dób (z koszyków godzinowych Insights).
Wynik to MEDIANA godzinowa z kilku ostatnich pełnych dób pomnożona przez współczynnik ostrożności — to nie jest prognoza pogody,
tylko „zakładamy, że jutro będzie jak ostatnio, trochę gorzej”. Karta zawsze pokazuje to jako szacunek, a nie prognozę."""
from __future__ import annotations

import math
from datetime import date
from typing import Any

N_DAYS = 5               # tyle ostatnich pełnych dób wchodzi do mediany
MIN_USED = 2             # poniżej tylu dób nie zgadujemy
MAX_AGE_DAYS = 10        # starsze doby nie opisują obecnej pogody ani pory roku
MIN_DAY_KWH = 1.0        # doba bez produkcji (awaria, zasłonięte panele) nie jest wzorcem
MIN_HOURS = 6            # tyle godzin z pomiarem musi mieć doba, by była „pełna”
CAUTION = 0.8            # ostrożność: planujemy z 80% typowej produkcji


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) and x >= 0 else None


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def profile(days: Any, today: date, n: int = N_DAYS, caution: float = CAUTION) -> dict[str, Any] | None:
    """{'hourly': [24 kWh], 'days': ile dób, 'dates': [...], 'kwh': suma dobowa po ostrożności, 'raw_kwh': przed, 'caution': k} albo None.

    `days`: {'YYYY-MM-DD': [24 wartości kWh albo None]}. Dobą „pełną” jest ta z pomiarem w ≥ MIN_HOURS godzinach i produkcją ≥ MIN_DAY_KWH;
    dzisiejsza doba nigdy nie wchodzi (jest niedokończona)."""
    if not isinstance(days, dict):
        return None
    good: list[tuple[str, list[float | None]]] = []
    for k in sorted((k for k in days if isinstance(k, str)), reverse=True):
        try:
            d = date.fromisoformat(k)
        except ValueError:
            continue
        if d >= today or (today - d).days > MAX_AGE_DAYS:
            continue
        arr = days[k]
        if not isinstance(arr, (list, tuple)) or len(arr) != 24:
            continue
        vals = [_num(v) for v in arr]
        if sum(1 for v in vals if v is not None) < MIN_HOURS or sum(v or 0.0 for v in vals) < MIN_DAY_KWH:
            continue
        good.append((k, vals))
        if len(good) >= max(1, int(n)):
            break
    if len(good) < MIN_USED:
        return None
    k_ = min(1.0, max(0.0, float(caution)))
    raw = []
    for h in range(24):
        col = [v[h] for _k, v in good if v[h] is not None]
        raw.append(_median(col) if col else 0.0)
    hourly = [round(v * k_, 3) for v in raw]
    return {"hourly": hourly, "days": len(good), "dates": [k for k, _v in good], "kwh": round(sum(hourly), 2),
            "raw_kwh": round(sum(raw), 2), "caution": k_}


def label(fb: dict[str, Any]) -> str:
    """Podpis źródła po polsku — wszędzie tam, gdzie karta pokazuje źródło prognozy."""
    return f"szacunek z ostatnich {fb['days']} dni × {str(round(fb['caution'], 2)).replace('.', ',')}"
