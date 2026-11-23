"""Okna cenowe doby: najtańszy / najdroższy ciągły blok godzin i godziny z ujemną ceną. Czyste funkcje, bez Home Assistanta.

Używane w powiadomieniu „plan na jutro” (jedno zdanie o najtańszych i najdroższych godzinach) i w ostrzeżeniu o ujemnych cenach."""
from __future__ import annotations

import math
from typing import Any

MIN_KNOWN = 20           # doba bez co najmniej tylu cen nie ma sensownych „najtańszych godzin”


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def known(prices: Any) -> list[float | None]:
    arr = prices if isinstance(prices, (list, tuple)) else []
    return [_num(arr[h]) if h < len(arr) else None for h in range(24)]


def best_block(prices: Any, n: int, cheapest: bool = True) -> dict[str, Any] | None:
    """Ciągły blok `n` godzin o najniższej (albo najwyższej) średniej cenie: {start, end, avg}. Godzina `end` jest wyłączna
    (blok 12–14 to godziny 12:00 i 13:00). None, gdy cen jest za mało albo w bloku jest dziura."""
    p = known(prices)
    n = int(n)
    if n < 1 or n > 24 or sum(1 for v in p if v is not None) < MIN_KNOWN:
        return None
    best: tuple[float, int] | None = None
    for s in range(0, 24 - n + 1):
        w = p[s:s + n]
        if any(v is None for v in w):
            continue
        avg = sum(w) / n
        if best is None or (avg < best[0] if cheapest else avg > best[0]):
            best = (avg, s)
    if best is None:
        return None
    return {"start": best[1], "end": best[1] + n, "avg": round(best[0], 4)}


def negative_hours(prices: Any, threshold: float = 0.0) -> list[int]:
    """Godziny z ceną poniżej progu (domyślnie ujemną)."""
    return [h for h, v in enumerate(known(prices)) if v is not None and v < threshold]


def spans(hours: list[int]) -> str:
    """[11,12,13,16] → „11–14, 16–17” (koniec wyłączny)."""
    out, hs = [], sorted(set(hours))
    i = 0
    while i < len(hs):
        j = i
        while j + 1 < len(hs) and hs[j + 1] == hs[j] + 1:
            j += 1
        out.append(f"{hs[i]:02d}–{hs[j] + 1:02d}")
        i = j + 1
    return ", ".join(out)


def _f(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def windows_text(prices: Any, n: int = 2) -> str | None:
    """„Najtaniej 12–14 (śr. 0,41 zł/kWh), najdrożej 18–20 (śr. 1,60 zł/kWh).” albo None, gdy za mało cen."""
    lo, hi = best_block(prices, n, True), best_block(prices, n, False)
    if not lo or not hi:
        return None
    return (f"Najtaniej {lo['start']:02d}–{lo['end']:02d} (śr. {_f(lo['avg'])} zł/kWh), "
            f"najdrożej {hi['start']:02d}–{hi['end']:02d} (śr. {_f(hi['avg'])} zł/kWh).")
