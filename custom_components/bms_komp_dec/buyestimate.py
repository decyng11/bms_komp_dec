"""Szacunek godzinowych cen zakupu na jutro — wyłącznie PODGLĄD na karcie, zanim operator cen opublikuje prawdziwe.

Przy taryfie dynamicznej (np. Pstryk) ceny na jutro pojawiają się około 12–14. Do tej pory tabela „Jutro” jest pusta.
Ten moduł pokazuje, jak zwykle wyglądał kształt cen w ostatnich dobach (mediana z tej samej godziny; dni robocze osobno od
weekendów, jeśli jest ich dość), żeby można było z grubsza ocenić, kiedy jutro będzie drogo. To NIE jest cena: planer jej nie
widzi (nie przechodzi przez `buy_hourly_for`), a po opublikowaniu prawdziwych cen szacunek znika. Czysty moduł, bez HA."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

MIN_DAYS = 3             # tyle dób z (prawie) pełnymi cenami trzeba, żeby w ogóle pokazać szacunek
MIN_HOURS_PER_DAY = 20   # doba jest „pełna”, gdy ma ceny z tylu godzin
MIN_SAMPLES = 2          # godzina dostaje wartość, gdy ma ją z tylu dób
MIN_HOURS_OUT = 20       # szacunek pokazujemy, gdy da się go policzyć dla tylu godzin
SAME_KIND_MIN = 3        # dni robocze/weekendy liczymy osobno, gdy takich dób jest co najmniej tyle
LOOKBACK = 14            # patrzymy najwyżej tyle dób wstecz


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


def _median(xs: list[float]) -> float:
    v = sorted(xs)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def _weekend(d: date) -> bool:
    return d.weekday() >= 5


def estimate(history: Any, target: date) -> dict[str, Any] | None:
    """Szacunek 24 cen na dzień `target` z historii {data ISO: [24 ceny lub None]} albo None, gdy za mało danych.

    Zwraca {"prices": [24 × cena|None], "days": ile dób użyto, "kind": "weekend"|"workday"|"all"}."""
    if not isinstance(history, dict) or not isinstance(target, date):
        return None
    days: list[tuple[date, list[float | None]]] = []
    for k, arr in history.items():
        d = _day(k)
        if d is None or d >= target or d < target - timedelta(days=LOOKBACK) or not isinstance(arr, (list, tuple)):
            continue
        vals = [_num(arr[h]) if h < len(arr) else None for h in range(24)]
        vals = [v if v is not None and v > 0 else None for v in vals]       # cena 0 lub ujemna w historii nie jest typowa — pomijamy
        if sum(v is not None for v in vals) >= MIN_HOURS_PER_DAY:
            days.append((d, vals))
    if len(days) < MIN_DAYS:
        return None
    same = [x for x in days if _weekend(x[0]) == _weekend(target)]
    kind = "all"
    if len(same) >= SAME_KIND_MIN:
        days, kind = same, ("weekend" if _weekend(target) else "workday")
    out: list[float | None] = []
    for h in range(24):
        col = [vals[h] for _, vals in days if vals[h] is not None]
        out.append(round(_median(col), 4) if len(col) >= MIN_SAMPLES else None)
    if sum(v is not None for v in out) < MIN_HOURS_OUT:
        return None
    return {"prices": out, "days": len(days), "kind": kind}


def note(info: dict[str, Any] | None) -> str | None:
    """Podpis pod tabelą po polsku — wprost mówi, że to nie są ceny z rynku."""
    if not info:
        return None
    kind = {"weekend": "weekendów", "workday": "dni roboczych"}.get(info.get("kind"), "ostatnich dób")
    return (f"Szacunek (nie ceny z rynku): mediana godzinowa z {info['days']} ostatnich dób ({kind}). "
            "Plan z niego nie korzysta — po publikacji prawdziwych cen tabela pokaże je zamiast szacunku.")
