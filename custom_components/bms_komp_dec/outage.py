"""Test zaniku sieci: ile bateria utrzyma dom w kilku wariantach, bez odcinania prądu. Czyste funkcje, bez HA."""
from __future__ import annotations

import math
from typing import Any

from . import autonomy as au

ESSENTIAL_W = 150.0          # „podstawa domu”: lodówka, router, oświetlenie — przybliżenie, nie pomiar


def _n(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def scenarios(soc: Any, floor: Any, cap_kwh: Any, load_w: Any, top: Any = None) -> list[dict[str, Any]]:
    """Warianty: teraz, bez największego odbiornika, tylko podstawa domu, pełna bateria. Pusta lista, gdy brak danych."""
    base = au.estimate(soc, floor, cap_kwh, load_w)
    if base is None:
        return []
    out = [{"id": "now", "label": "Teraz (obecny pobór)", "load_w": base["load_w"], "hours": base["hours"], "text": au.fmt_hours(base["hours"], base["capped"])}]
    loads: list[tuple[str, float]] = []
    for item in top if isinstance(top, (list, tuple)) else []:
        if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], str) and _n(item[1]) is not None and _n(item[1]) > 0:
            loads.append((item[0][:40], float(_n(item[1]))))
    if loads:
        nm, p = max(loads, key=lambda x: x[1])
        w = max(base["load_w"] - p, au.MIN_LOAD_W)
        if w < base["load_w"]:
            e = au.estimate(soc, floor, cap_kwh, w)
            out.append({"id": "no_top", "label": f"Bez „{nm}” ({p / 1000.0:.1f} kW)".replace(".", ","), "load_w": e["load_w"], "hours": e["hours"], "text": au.fmt_hours(e["hours"], e["capped"])})
    e = au.estimate(soc, floor, cap_kwh, ESSENTIAL_W)
    if e["load_w"] < base["load_w"]:
        out.append({"id": "essential", "label": f"Tylko podstawa domu (~{ESSENTIAL_W:.0f} W)", "load_w": e["load_w"], "hours": e["hours"], "text": au.fmt_hours(e["hours"], e["capped"])})
    s = _n(soc)
    if s is not None and s < 99:
        e = au.estimate(100, floor, cap_kwh, load_w)
        out.append({"id": "full", "label": "Gdyby bateria była pełna (obecny pobór)", "load_w": e["load_w"], "hours": e["hours"], "text": au.fmt_hours(e["hours"], e["capped"])})
    return out
