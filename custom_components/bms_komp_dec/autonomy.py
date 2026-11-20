"""„Na ile godzin starczy baterii”: energia nad progiem odcięcia falownika podzielona przez bieżący (wygładzony) pobór domu.

Czyste funkcje (bez Home Assistanta). To szacunek na najgorszy przypadek — liczony bez produkcji PV i przy stałym poborze, bo przy
zaniku sieci chcemy wiedzieć, ile bateria wytrzyma, gdyby słońca nie było."""
from __future__ import annotations

import math
from typing import Any

EFF = 0.92               # sprawność rozładowania baterii i falownika
MIN_LOAD_W = 50.0        # poniżej tego dom i tak ma pobór własny — nie dzielimy przez zero
MAX_HOURS = 72.0         # dłużej niż 3 doby nie podajemy konkretnej liczby
EMA_TAU_S = 300.0        # stała wygładzania poboru (5 minut) — pojedynczy czajnik nie zmienia wyniku
BIG_LOAD_W = 300.0       # tylko odbiorniki od tej mocy warto proponować do wyłączenia


def _n(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def ema(prev: Any, value: Any, dt_s: float, tau_s: float = EMA_TAU_S) -> float | None:
    """Średnia wykładnicza: nowa wartość = stara + (pomiar − stara) × dt/(dt+tau). Brak poprzedniej → sam pomiar."""
    v = _n(value)
    if v is None or v < 0:
        return _n(prev)
    p = _n(prev)
    if p is None or dt_s <= 0 or dt_s > 3600:
        return v
    return p + (v - p) * (dt_s / (dt_s + tau_s))


def estimate(soc: Any, floor_pct: Any, cap_kwh: Any, load_w: Any, eff: float = EFF) -> dict[str, Any] | None:
    """{'hours', 'capped', 'usable_kwh', 'load_w'} albo None, gdy brakuje któregokolwiek wejścia."""
    s, f, c, w = _n(soc), _n(floor_pct), _n(cap_kwh), _n(load_w)
    if s is None or f is None or c is None or w is None or c <= 0 or w < 0:
        return None
    usable = max(0.0, (min(100.0, s) - max(0.0, f)) / 100.0 * c) * eff
    hours = usable / (max(w, MIN_LOAD_W) / 1000.0)
    capped = hours > MAX_HOURS
    return {"hours": round(min(hours, MAX_HOURS), 1), "capped": capped, "usable_kwh": round(usable, 2), "load_w": round(w)}


def fmt_hours(h: float, capped: bool = False) -> str:
    """„ponad 3 doby”, „14 h”, „1 h 20 min”, „40 min”, „mniej niż 10 min” (minuty zaokrąglone do 5, od 10 h do pełnych godzin)."""
    if capped or h >= MAX_HOURS:
        return "ponad 3 doby"
    if h < 1 / 6:
        return "mniej niż 10 min"
    if h >= 10:
        return f"{int(round(h))} h"
    total_min = int(round(h * 60 / 5.0)) * 5
    hh, mm = divmod(total_min, 60)
    if hh == 0:
        return f"{mm} min"
    return f"{hh} h" if mm == 0 else f"{hh} h {mm} min"


def extend_hint(est: dict[str, Any], top: list[tuple[str, float]] | None) -> str:
    """Zdanie z propozycją: ile czasu zyskamy po wyłączeniu największego odbiornika (≥ BIG_LOAD_W); pusty napis, gdy nie ma czego proponować."""
    if not est or not top:
        return ""
    name, p = top[0]
    pw = _n(p)
    if pw is None or pw < BIG_LOAD_W or est.get("load_w") is None:
        return ""
    new_load = max(float(est["load_w"]) - pw, MIN_LOAD_W)
    new_h = est["usable_kwh"] / (new_load / 1000.0)
    if new_h <= est["hours"] * 1.15:
        return ""
    return f" Wyłączenie „{name}” ({pw / 1000.0:.1f} kW) wydłuży to do ok. {fmt_hours(min(new_h, MAX_HOURS), new_h > MAX_HOURS)}.".replace(".", ",", 1)
