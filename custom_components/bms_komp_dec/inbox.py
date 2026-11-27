"""Skrzynka powiadomień panelu (dzwonek) i pamięć odrzuconych propozycji harmonogramu.

Wszystko w rt.state (zapisywane przez runtime) — działa bez otwartej karty. Propozycje planu nie trafiają do skrzynki:
karta pokazuje je na żywo z sensora planu, a „Odrzuć” zapamiętuje tu proponowaną wartość, dopóki plan nie zaproponuje innej."""
from __future__ import annotations

import re
import time
from typing import Any

from .notify_cfg import CATALOG

INBOX_MAX = 60
INBOX_DAYS = 14
SKIP_KINDS = ("proposal",)
AUTO_READ_INFO_H = 6          # informacje (info/ok) przestają być „nieprzeczytane” same po tylu godzinach
QUIET_LEVELS = ("info", "ok")  # te wpisy czytają się same szybko i po zamknięciu okna
SEEN_LEVELS = ("info", "ok", "warn")   # po obejrzeniu (zamknięciu okna) ostrzeżenie też staje się przeczytane; błędy czekają
AUTO_READ_H = {"info": AUTO_READ_INFO_H, "ok": AUTO_READ_INFO_H, "warn": 24.0, "error": 72.0}   # siatka bezpieczeństwa: nic nie wisi bez końca
MERGE_H = 12.0                 # powtórka tego samego komunikatu w tym czasie zlewa się w jeden wpis (licznik ×N), zamiast zapychać skrzynkę
REARM_H = 6.0                  # przeczytany wpis wraca jako nieprzeczytany, tylko gdy powtórka przyszła po tylu godzinach ciszy
ACTIONS = ("read", "read_all", "read_info", "read_seen", "delete", "clear", "reject", "unreject")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _items(state: dict[str, Any]) -> list[dict[str, Any]]:
    inbox = state.get("inbox")
    if not isinstance(inbox, list):
        inbox = state["inbox"] = []
    return inbox


def _same_message(a: str, b: str) -> bool:
    """Ten sam komunikat z innymi liczbami („Bateria 12%” / „Bateria 9%”) — to powtórka, a nie nowe zdarzenie."""
    return _NUM.sub("#", str(a)) == _NUM.sub("#", str(b))


def _mark(e: dict[str, Any], why: str) -> None:
    e["read"] = True
    e["auto"] = why


def add(state: dict[str, Any], kind: str, title: str, message: str, level: str = "info",
        ts: float | None = None, supersede: bool = False) -> dict[str, Any] | None:
    """Dopisuje wpis do skrzynki; zwraca go (albo None dla rodzajów pomijanych).

    supersede=True (autoodczyt): starsze NIEPRZECZYTANE wpisy z tym samym rodzajem, tytułem i treścią (z dokładnością do liczb)
    i poziomem info/ok/warn dostają „przeczytane” — zostaje jeden, najnowszy, nieprzeczytany. Błędów nie ruszamy."""
    if kind in SKIP_KINDS:
        return None
    now = float(ts if ts is not None else time.time())
    items = _items(state)
    lvl = level if level in ("info", "warn", "error", "ok") else "info"
    for e in reversed(items):                      # powtórka tego samego komunikatu: jeden wpis z licznikiem, nie kolejny
        if (isinstance(e, dict) and e.get("kind") == kind and e.get("title") == str(title)[:160] and e.get("level") == lvl
                and now - float(e.get("ts") or now) <= MERGE_H * 3600.0 and _same_message(e.get("message", ""), str(message)[:1500])):
            quiet_for = now - float(e.get("ts") or now)
            e["n"] = int(e.get("n") or 1) + 1
            e["ts"] = round(now)
            e["message"] = str(message)[:1500]
            if e.get("read") and quiet_for >= REARM_H * 3600.0:
                e["read"] = False
                e.pop("auto", None)
            return e
    if supersede:
        for e in items:
            if (isinstance(e, dict) and not e.get("read") and e.get("kind") == kind and e.get("title") == str(title)[:160]
                    and e.get("level") in ("info", "ok", "warn") and _same_message(e.get("message", ""), str(message)[:1500])):
                _mark(e, "zastąpione nowszym")
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
    elif action == "read_info":
        for e in items:
            if not e.get("read") and e.get("level") in QUIET_LEVELS:
                _mark(e, "obejrzane")
                n += 1
    elif action == "read_seen":
        for e in items:
            if not e.get("read") and e.get("level") in SEEN_LEVELS:
                _mark(e, "obejrzane")
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


def prune_rejected(state: dict[str, Any], proposals: dict[str, Any]) -> int:
    """Zapomina odrzucenia, których plan już nie proponuje (inna godzina, brak propozycji albo „pomiń”).

    Dzięki temu ta sama godzina zaproponowana ponownie za kilka dni znów trafi do decyzji, zamiast zostać ukryta na zawsze."""
    rej = rejected(state)
    drop = [k for k, v in rej.items()
            if not isinstance(proposals.get(k), dict) or proposals[k].get("skip") or proposals[k].get("proposed") != v]
    for k in drop:
        rej.pop(k, None)
    return len(drop)


def prune_auto_skip(state: dict[str, Any], proposals: dict[str, Any]) -> int:
    """Zapomina powody niezastosowania propozycji, której plan już nie proponuje (inna godzina, „pomiń”, brak) albo która
    jest już ustawiona. Powód dotyczy konkretnej propozycji (`prop`), więc nowa godzina zaczyna bez cudzego komunikatu."""
    store = state.get("auto_skip")
    if not isinstance(store, dict) or not store:
        return 0
    drop = []
    for k, rec in store.items():
        p = proposals.get(k)
        if (not isinstance(rec, dict) or not isinstance(p, dict) or p.get("skip") or not p.get("proposed")
                or str(p.get("proposed")) != str(rec.get("prop")) or p.get("proposed") == p.get("current")):
            drop.append(k)
    for k in drop:
        store.pop(k, None)
    return len(drop)


def auto_read(state: dict[str, Any], now: float | None = None, hours: float = AUTO_READ_INFO_H) -> list[str]:
    """Wpisy starsze niż próg poziomu (info/ok: `hours`, ostrzeżenia 24 h, błędy 72 h) → „przeczytane”. Zwraca rodzaje, które nie mają
    już nieprzeczytanych wpisów (ich powiadomienia w HA można zdjąć)."""
    t = float(now if now is not None else time.time())
    touched = set()
    for e in _items(state):
        h = hours if e.get("level") in QUIET_LEVELS else AUTO_READ_H.get(e.get("level"), hours)
        if isinstance(e, dict) and not e.get("read") and t - float(e.get("ts") or t) >= h * 3600.0:
            _mark(e, f"po {h:g} h")
            touched.add(e.get("kind"))
    left = {e.get("kind") for e in _items(state) if isinstance(e, dict) and not e.get("read")}
    return sorted(k for k in touched if k and k not in left)


def resolve(state: dict[str, Any], kind: str) -> int:
    """Sytuacja minęła (np. SOC wrócił, brak danych ustąpił): nieprzeczytane wpisy tego rodzaju poziomu info/ok/warn → „przeczytane”.
    Błędy zostają nieprzeczytane — to ślad, że coś się wydarzyło, nawet jeśli już przeszło."""
    n = 0
    for e in _items(state):
        if isinstance(e, dict) and not e.get("read") and e.get("kind") == kind and e.get("level") in ("info", "ok", "warn"):
            _mark(e, "sytuacja minęła")
            n += 1
    return n


def unread(state: dict[str, Any]) -> int:
    return sum(1 for e in _items(state) if not e.get("read"))
