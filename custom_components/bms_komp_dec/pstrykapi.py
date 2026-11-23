"""Dokładne ceny godzinowe prosto z API Pstryka (klucz z aplikacji: Konto → Urządzenia i integracje → Klucz API).

Dlaczego: ceny wyliczane z PSE (RCE) są tylko przybliżeniem, a własne ceny Pstryka są dokładnie tym, co widać w aplikacji
i na rachunku. Gdy klucz jest ustawiony, EMS bierze z API pełną cenę brutto za kWh (`price_gross`) i nie zgaduje.

Czysty moduł (bez HA i sieci): adres zapytania, nagłówki, parsowanie odpowiedzi. Parser jest tolerancyjny na kształt odpowiedzi
(lista albo obiekt z listą `frames`), ale NIE zgaduje cen: brak pola `price_gross` w godzinie = godzina bez ceny, a doba
z mniej niż 20 godzinami cen jest odrzucana (np. jutro przed publikacją)."""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any
from urllib.parse import urlencode

BASE_URL = "https://api.pstryk.pl/integrations/pricing/"
MIN_HOURS_DAY = 20
PRICE_FIELD = "price_gross"


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def window(d: date, tz: tzinfo) -> tuple[str, str]:
    """Początek i koniec doby `d` w lokalnej strefie, zapisane w UTC (ISO, „Z”)."""
    a = datetime.combine(d, time(0, 0), tzinfo=tz)
    b = datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=tz)
    f = lambda x: x.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    return f(a), f(b)


def day_url(d: date, tz: tzinfo) -> str:
    a, b = window(d, tz)
    return f"{BASE_URL}?{urlencode({'resolution': 'hour', 'window_start': a, 'window_end': b})}"


def headers(token: str, bearer: bool = False) -> dict[str, str]:
    t = str(token or "").strip()
    return {"Authorization": f"Bearer {t}" if bearer else t, "Accept": "application/json"}


def _frames(payload: Any) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("frames", "results", "data", "prices", "values"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
    return []


def parse_day(payload: Any, d: date, tz: tzinfo) -> list[float | None] | None:
    """24 ceny brutto (zł/kWh) doby `d` w lokalnych godzinach albo None, gdy doba jest niepełna / odpowiedź jest zła."""
    out: list[float | None] = [None] * 24
    for fr in _frames(payload):
        if not isinstance(fr, dict):
            continue
        p = _num(fr.get(PRICE_FIELD))
        raw = fr.get("start")
        if p is None or not isinstance(raw, str):
            continue
        try:
            t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        loc = t.astimezone(tz)
        if loc.date() != d or not 0 <= loc.hour <= 23:
            continue
        out[loc.hour] = round(p, 4)
    return out if sum(1 for v in out if v is not None) >= MIN_HOURS_DAY else None
