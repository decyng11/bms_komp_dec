"""Pierwszy słoneczny dzień po serii pochmurnych: powiadomienie wieczorem, gdy jutro ma być wyraźnie lepiej niż ostatnie dni.

Porównanie jest względne (do najlepszego dnia z ostatnich 30), więc działa tak samo zimą i latem, bez wiedzy o mocy instalacji.
Czyste funkcje, bez HA."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

WINDOW = 30
MIN_HISTORY = 7          # tyle dób z produkcją trzeba, żeby ocenić „pochmurno”
MIN_BEST_KWH = 3.0       # najlepszy dzień poniżej tego = brak sensownego wzorca (np. awaria licznika)
POOR_SHARE = 0.35        # doba „pochmurna”: poniżej tylu najlepszego dnia
SUNNY_SHARE = 0.65       # jutro „słoneczne”: prognoza co najmniej tyle najlepszego dnia
POOR_DAYS = 2            # tyle ostatnich dób z rzędu musiało być pochmurnych


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) and 0 <= x < 1000 else None


def evaluate(daily_pv: Any, tomorrow_kwh: Any, today: date) -> dict[str, Any] | None:
    """Dane: {data ISO: produkcja PV doby [kWh]} (dziś ma być już niemal kompletne — sprawdzamy wieczorem). None = nie powiadamiać."""
    if not isinstance(daily_pv, dict) or not isinstance(today, date):
        return None
    fc = _num(tomorrow_kwh)
    if fc is None:
        return None
    hist: dict[date, float] = {}
    for k, v in daily_pv.items():
        try:
            d = date.fromisoformat(str(k)[:10])
        except ValueError:
            continue
        x = _num(v)
        if x is not None and today - timedelta(days=WINDOW) <= d <= today:
            hist[d] = x
    if len(hist) < MIN_HISTORY:
        return None
    best = max(hist.values())
    if best < MIN_BEST_KWH:
        return None
    last = [hist.get(today - timedelta(days=i)) for i in range(POOR_DAYS)]
    if any(x is None or x >= POOR_SHARE * best for x in last):
        return None
    if fc < SUNNY_SHARE * best:
        return None
    return {"tomorrow": round(fc, 1), "best": round(best, 1), "last": [round(x, 1) for x in last],
            "text": (f"Po {POOR_DAYS} pochmurnych dniach (dziś {last[0]:.1f} kWh, wczoraj {last[1]:.1f} kWh) jutro ma być słonecznie: "
                     f"prognoza PV {fc:.1f} kWh. Bateria powinna się naładować, więc plan może mniej dokupować z sieci.").replace(".", ",")}
