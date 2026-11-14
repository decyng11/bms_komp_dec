"""Ręczne nadpisania planu na wybrane godziny (14): „ładuj z sieci”, „nie sprzedawaj”, „nie ładuj z sieci”.

Wpisy trzymamy w runtime.state["overrides"]: {id, kind, start, end (znaczniki czasu), target (SOC, tylko „charge”)}.
Wygasają same; maksymalnie 48 h do przodu."""
from __future__ import annotations

from typing import Any

KINDS = {
    "charge": "ładuj z sieci",
    "no_sell": "nie sprzedawaj z baterii",
    "no_grid": "nie ładuj z sieci",
}
MAX_HOURS = 48.0
MAX_ITEMS = 6
# rodzaje, które się wykluczają (nowy zastępuje nakładający się stary)
CONFLICT = {"charge": {"no_grid", "charge"}, "no_grid": {"charge", "no_grid"}, "no_sell": {"no_sell"}}


class OverrideError(ValueError):
    pass


def prune(items: list[dict], now_ts: float) -> list[dict]:
    return [o for o in items if isinstance(o, dict) and float(o.get("end") or 0) > now_ts]


def active(items: list[dict], now_ts: float, kind: str | None = None) -> list[dict]:
    return [o for o in items if float(o.get("start") or 0) <= now_ts < float(o.get("end") or 0)
            and (kind is None or o.get("kind") == kind)]


def add(items: list[dict], kind: str, start_ts: float, end_ts: float, now_ts: float, target: float | None = None) -> list[dict]:
    """Zwraca nową listę z dodanym wpisem. Zgłasza OverrideError przy błędnych danych."""
    if kind not in KINDS:
        raise OverrideError(f"nieznany rodzaj nadpisania: {kind}")
    if end_ts <= start_ts:
        raise OverrideError("koniec musi być po początku")
    if end_ts <= now_ts:
        raise OverrideError("to okno już minęło")
    if start_ts > now_ts + MAX_HOURS * 3600:
        raise OverrideError(f"nadpisanie można ustawić najwyżej {MAX_HOURS:.0f} h do przodu")
    if end_ts - start_ts > MAX_HOURS * 3600:
        raise OverrideError(f"nadpisanie może trwać najwyżej {MAX_HOURS:.0f} h")
    if target is not None:
        if kind != "charge":
            target = None
        elif not 5 <= float(target) <= 100:
            raise OverrideError("docelowy SOC musi mieścić się w zakresie 5–100%")
    keep = []
    for o in prune(items, now_ts):
        overlap = float(o["start"]) < end_ts and start_ts < float(o["end"])
        if overlap and o.get("kind") in CONFLICT[kind]:
            continue                                  # nowy wpis zastępuje nakładający się, sprzeczny z nim
        keep.append(o)
    item = {"id": f"{int(now_ts)}-{kind}", "kind": kind, "start": float(start_ts), "end": float(end_ts)}
    if target is not None:
        item["target"] = float(target)
    keep.append(item)
    keep.sort(key=lambda o: o["start"])
    if len(keep) > MAX_ITEMS:
        raise OverrideError(f"najwyżej {MAX_ITEMS} nadpisań naraz — usuń któreś")
    return keep


def remove(items: list[dict], oid: str | None) -> list[dict]:
    """Usuwa wpis o danym id (None = wszystkie)."""
    return [] if oid is None else [o for o in items if o.get("id") != oid]
