"""Skrzynka powiadomień panelu (dzwonek) i pamięć odrzuconych propozycji harmonogramu.

Wszystko w rt.state (zapisywane przez runtime) — działa bez otwartej karty. Propozycje planu nie trafiają do skrzynki:
karta pokazuje je na żywo z sensora planu, a „Odrzuć” zapamiętuje tu proponowaną wartość, dopóki plan nie zaproponuje innej."""
from __future__ import annotations

import time
from typing import Any

from .notify_cfg import CATALOG

INBOX_MAX = 60
INBOX_DAYS = 14
SKIP_KINDS = ("proposal",)
ACTIONS = ("read", "read_all", "delete", "clear", "reject", "unreject")


def _items(state: dict[str, Any]) -> list[dict[str, Any]]:
    inbox = state.get("inbox")
    if not isinstance(inbox, list):
        inbox = state["inbox"] = []
    return inbox


def add(state: dict[str, Any], kind: str, title: str, message: str, level: str = "info",
        ts: float | None = None) -> dict[str, Any] | None:
    """Dopisuje wpis do skrzynki; zwraca go (albo None dla rodzajów pomijanych)."""
    if kind in SKIP_KINDS:
        return None
    now = float(ts if ts is not None else time.time())
    items = _items(state)
    nid = int(state.get("inbox_seq") or 0) + 1
    state["inbox_seq"] = nid
    grp = CATALOG.get(kind, ("Inne",))[0]
    entry = {"id": nid, "ts": round(now), "kind": kind, "group": grp, "title": str(title)[:160],
             "message": str(message)[:1500], "level": level if level in ("info", "warn", "error", "ok") else "info",
             "read": False}
    items.append(entry)
    cut = now - INBOX_DAYS * 86400
    items[:] = [e for e in items if isinstance(e, dict) and e.get("ts", now) >= cut]
    if len(items) > INBOX_MAX:
        del items[: len(items) - INBOX_MAX]
    return entry


def rejected(state: dict[str, Any]) -> dict[str, str]:
    r = state.get("rejected_props")
    if not isinstance(r, dict):
        r = state["rejected_props"] = {}
    return r


def is_rejected(state: dict[str, Any], key: str, proposed: Any) -> bool:
    return rejected(state).get(key) == proposed and proposed is not None


def act(state: dict[str, Any], action: str, *, ident: Any = None, key: str | None = None,
        proposed: str | None = None) -> dict[str, Any]:
    """Operacja z karty. Zwraca {"changed": n}; nieznana akcja → ValueError."""
    if action not in ACTIONS:
        raise ValueError(f"nieznana akcja: {action}")
    items = _items(state)
    n = 0
    if action == "read":
        for e in items:
            if e.get("id") == ident and not e.get("read"):
                e["read"] = True
                n += 1
    elif action == "read_all":
        for e in items:
            if not e.get("read"):
                e["read"] = True
                n += 1
    elif action == "delete":
        before = len(items)
        items[:] = [e for e in items if e.get("id") != ident]
        n = before - len(items)
    elif action == "clear":
        n = len(items)
        items.clear()
    elif action == "reject":
        if not key or not proposed:
            raise ValueError("reject wymaga key i proposed")
        rejected(state)[str(key)] = str(proposed)
        n = 1
    elif action == "unreject":
        n = 1 if rejected(state).pop(str(key), None) is not None else 0
    return {"changed": n}


def unread(state: dict[str, Any]) -> int:
    return sum(1 for e in _items(state) if not e.get("read"))
