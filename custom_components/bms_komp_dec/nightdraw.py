"""Nocny pobór domu wyższy niż zwykle: zostawione włączone grzejniki, bojler, pompa, zepsuty odbiornik.

Czyste funkcje (bez Home Assistanta). Porównujemy średnią moc domu w godzinach 1:00–5:00 z medianą z ostatnich nocy (mediana jest
odporna na pojedynczą nietypową noc). Powiadomienie ma sens dopiero po kilku nocach historii i tylko wtedy, gdy różnica jest
wyraźna zarówno procentowo, jak i w watach — dom z poborem 80 W zamiast 50 W nie jest problemem."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

NIGHT_HOURS = (1, 2, 3, 4)       # 1:00–5:00 — pora, gdy w domu zwykle nikt nic nie robi
MIN_HOURS = 3                    # tyle godzin z pomiarem musi mieć noc, żeby się liczyła
MIN_NIGHTS = 4                   # tyle wcześniejszych nocy potrzeba do „zwykle”
MAX_NIGHTS = 14
MIN_ABS_W = 250.0                # poniżej tej średniej mocy nic nie zgłaszamy
MIN_EXTRA_W = 150.0              # i tylko, gdy to co najmniej tyle więcej niż zwykle
DEFAULT_RATIO = 1.6              # i co najmniej tyle razy więcej niż zwykle


def _kwh(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) and 0 <= x < 100 else None


def night_avg_w(loads: Any) -> tuple[float | None, int]:
    """(średnia moc w W w godzinach nocnych, ile godzin miało pomiar); None, gdy za mało godzin."""
    if not isinstance(loads, (list, tuple)) or len(loads) != 24:
        return None, 0
    vals = [x for x in (_kwh(loads[h]) for h in NIGHT_HOURS) if x is not None]
    if len(vals) < MIN_HOURS:
        return None, len(vals)
    return sum(vals) / len(vals) * 1000.0, len(vals)       # kWh w ciągu godziny = średnia moc w kW


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def baseline(history: Any, today: date, max_nights: int = MAX_NIGHTS) -> dict[str, Any] | None:
    """{'w': mediana nocnej średniej mocy, 'nights': ile nocy} z nocy sprzed `today`; None, gdy za mało nocy."""
    if not isinstance(history, dict):
        return None
    avgs: list[float] = []
    for k in sorted((k for k in history if isinstance(k, str)), reverse=True):
        try:
            d = date.fromisoformat(k)
        except ValueError:
            continue
        if d >= today or (today - d).days > max_nights + 3:
            continue
        w, _n = night_avg_w(history[k])
        if w is not None:
            avgs.append(w)
        if len(avgs) >= max_nights:
            break
    if len(avgs) < MIN_NIGHTS:
        return None
    return {"w": _median(avgs), "nights": len(avgs)}


def evaluate(today_loads: Any, history: Any, today: date, ratio: float = DEFAULT_RATIO) -> dict[str, Any] | None:
    """Wynik porównania dzisiejszej nocy z typową albo None, gdy nic wartego zgłoszenia (albo brak danych).

    {'avg_w', 'base_w', 'nights', 'ratio', 'extra_w'}"""
    avg, _n = night_avg_w(today_loads)
    base = baseline(history, today)
    if avg is None or base is None:
        return None
    r = max(1.2, float(ratio) if math.isfinite(float(ratio)) else DEFAULT_RATIO)
    b = max(base["w"], 1.0)
    extra = avg - b
    if avg < MIN_ABS_W or extra < MIN_EXTRA_W or avg < b * r:
        return None
    return {"avg_w": round(avg, 1), "base_w": round(b, 1), "nights": base["nights"], "ratio": round(avg / b, 2), "extra_w": round(extra, 1)}


def message(res: dict[str, Any], top: list[tuple[str, float]] | None = None) -> str:
    f = lambda v: f"{v:.0f}"  # noqa: E731
    txt = (f"W nocy (1:00–5:00) dom pobierał średnio {f(res['avg_w'])} W, a zwykle ok. {f(res['base_w'])} W "
           f"(mediana z {res['nights']} nocy) — {str(round(res['ratio'], 1)).replace('.', ',')}× więcej.")
    if top:
        txt += " Teraz najwięcej biorą: " + ", ".join(f"{nm} {p / 1000.0:.1f} kW".replace(".", ",") for nm, p in top[:3]) + "."
    else:
        txt += " Sprawdź, co zostało włączone na noc (grzejnik, bojler, pompa ciepła, ładowanie auta, zepsuty odbiornik)."
    return txt
