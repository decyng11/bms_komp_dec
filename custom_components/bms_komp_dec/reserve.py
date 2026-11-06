"""Dynamiczna rezerwa SOC (funkcja 3) — czysta logika bez zależności od HA.

Rezerwa = energia potrzebna domowi od teraz do pierwszej godziny, w której PV samo
pokrywa zużycie (liczone po godzinach), plus stałe minimum, wyrażona w % pojemności.
"""
from __future__ import annotations

from typing import Any, Sequence

DEFAULT_LOAD_KWH_PER_H = 0.5
FALLBACK_PV_START_HOUR = 8     # gdy brak prognozy PV: PV pokrywa zużycie od 8:00
MAX_RESERVE_PCT = 95.0
SCAN_HOURS = 30


def compute_reserve(
    *,
    now_hour: int,
    capacity_kwh: float,
    floor_pct: float,
    load_hourly: Sequence[float | None] | None,
    pv_hourly: Sequence[float | None] | None,
    pv_scale_next_day: float = 1.0,
    load_fallback_kwh_h: float = DEFAULT_LOAD_KWH_PER_H,
) -> dict[str, Any]:
    """Zwraca {'pct','need_kwh','until_hour','hours'}.

    now_hour: bieżąca godzina; dla kolejnych godzin liczymy zużycie z load_hourly[h % 24]
    i produkcję z pv_hourly[h % 24] (dla dnia następnego skalowaną pv_scale_next_day).
    """
    capacity_kwh = max(float(capacity_kwh), 0.1)
    floor_pct = min(max(float(floor_pct), 0.0), MAX_RESERVE_PCT)

    def load_at(h: int) -> float:
        if load_hourly and len(load_hourly) == 24 and load_hourly[h % 24] is not None:
            return max(0.0, float(load_hourly[h % 24]))
        return load_fallback_kwh_h

    def pv_at(h_abs: int) -> float | None:
        if pv_hourly and len(pv_hourly) == 24:
            v = pv_hourly[h_abs % 24]
            if v is None:
                return 0.0
            scale = pv_scale_next_day if h_abs >= 24 else 1.0
            return max(0.0, float(v)) * scale
        return None  # brak prognozy

    need = 0.0
    until = None
    hours = 0
    for step in range(1, SCAN_HOURS + 1):
        h_abs = now_hour + step          # godzina po bieżącej
        hh = h_abs % 24
        pv = pv_at(h_abs)
        load = load_at(hh)
        if pv is None:
            covered = FALLBACK_PV_START_HOUR <= hh < 18 and h_abs > now_hour
            pv_used = load if covered else 0.0
        else:
            pv_used = pv
        # PV pokrywa zużycie -> koniec okresu, w którym bateria musi trzymać dom
        if pv_used >= load and pv_used > 0.05:
            until = hh
            break
        need += max(0.0, load - pv_used)
        hours += 1
    else:
        until = (now_hour + SCAN_HOURS) % 24

    pct = min(MAX_RESERVE_PCT, floor_pct + need / capacity_kwh * 100.0)
    return {
        "pct": round(pct, 1),
        "need_kwh": round(need, 2),
        "until_hour": until,
        "hours": hours,
    }
