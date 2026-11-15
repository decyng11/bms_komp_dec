"""Dziennik zmian ustawień EMS: kto i kiedy zmienił encję integracji (number / switch / time / select) i z jakiej wartości.

Rejestruje zmiany zlecone przez użytkownika (panel, aplikacja HA, API) albo automatyzację/skrypt. Zmiany wewnętrzne
integracji (bez użytkownika i bez nadrzędnego kontekstu) pomijamy — one trafiają do dziennika decyzji. Zapis w rt.state."""
from __future__ import annotations

import time
from typing import Any

DOMAINS = ("number", "switch", "time", "select")
LOG_MAX = 150
SKIP_STATES = ("unknown", "unavailable", "none", "")


def record(state: dict[str, Any], eid: str, old: Any, new: Any, who: str, ts: float | None = None) -> dict[str, Any] | None:
    """Dopisuje zmianę; zwraca wpis albo None, gdy zmiana nic nie znaczy (brak poprzedniej wartości, ta sama wartość)."""
    o, n = str(old if old is not None else "").strip(), str(new if new is not None else "").strip()
    if o.lower() in SKIP_STATES or n.lower() in SKIP_STATES or o == n:
        return None
    items = state.get("settings_log")
    if not isinstance(items, list):
        items = state["settings_log"] = []
    seq = int(state.get("settings_log_seq") or 0) + 1
    state["settings_log_seq"] = seq
    entry = {"id": seq, "ts": round(float(ts if ts is not None else time.time())), "eid": eid, "from": o, "to": n, "who": who}
    items.append(entry)
    if len(items) > LOG_MAX:
        del items[: len(items) - LOG_MAX]
    return entry


def items(state: dict[str, Any], limit: int = 100) -> list[dict[str, Any]]:
    raw = state.get("settings_log")
    out = [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []
    return list(reversed(out))[: max(1, int(limit))]
