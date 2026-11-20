"""Dowód zakazu arbitrażu: dla każdej doby trzy liczby — ile energii poszło z sieci do baterii, ile z baterii do sieci i ile z tego,
co bateria oddała do sieci, mogło pochodzić z sieci (zakaz „ładuj z sieci → sprzedaj” mówi, że ma być 0).

Czyste funkcje (bez Home Assistanta). Runtime dolicza energię w każdym kroku (co ok. 10 s) do wpisu doby w `state["arb_proof"]`.
„Z sieci sprzedane” to GÓRNA granica: zakładamy, że do sieci schodzi najpierw energia pobrana z sieci. Jeśli wychodzi 0, to na pewno
nic z sieci nie wróciło do sieci; jeśli kilka setnych kWh — to mieści się w dokładności pomiaru i tolerancji blokady."""
from __future__ import annotations

import math
from typing import Any

KEEP_DAYS = 30
LEAK_OK = 0.05           # poniżej tego „z sieci sprzedane” uznajemy za zero (szum pomiaru)
IDLE_KWH = 0.05          # poniżej tego w obie strony doba była „bez arbitrażu w ogóle”
KEYS = ("in", "out", "leak")
MAX_KWH = 5000.0


def _n(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def fmt(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def clean(store: Any) -> dict[str, dict[str, float]]:
    """Wczytany z pliku słownik doba → liczniki: zostają daty ISO i nieujemne, skończone liczby."""
    out: dict[str, dict[str, float]] = {}
    if not isinstance(store, dict):
        return out
    for k, rec in store.items():
        if not (isinstance(k, str) and len(k) == 10 and k[4] == "-" and k[7] == "-" and isinstance(rec, dict)):
            continue
        row = {}
        for f in KEYS:
            x = _n(rec.get(f))
            row[f] = round(min(MAX_KWH, max(0.0, x)), 4) if x is not None else 0.0
        out[k] = row
    return out


def add(store: dict[str, Any], day: str, grid_in: float = 0.0, out: float = 0.0, leak: float = 0.0) -> None:
    """Dolicza energię (kWh) do wpisu doby i przycina starsze niż KEEP_DAYS dób."""
    rec = store.get(day)
    if not isinstance(rec, dict):
        rec = store[day] = {"in": 0.0, "out": 0.0, "leak": 0.0}
    for f, v in (("in", grid_in), ("out", out), ("leak", leak)):
        x = _n(v)
        cur = _n(rec.get(f)) or 0.0
        if x is not None and x > 0:
            cur += x
        rec[f] = round(min(MAX_KWH, cur), 4)
    for k in sorted(store)[:-KEEP_DAYS]:
        store.pop(k, None)


def verdict(rec: dict[str, Any], tol: float) -> dict[str, str]:
    """{'level': ok|warn|bad|idle, 'text': po polsku} — czy zakaz arbitrażu został dotrzymany tej doby."""
    gin, out, leak = (_n(rec.get(k)) or 0.0 for k in KEYS)
    if gin < IDLE_KWH and out < IDLE_KWH:
        return {"level": "idle", "text": "brak ładowania z sieci i sprzedaży z baterii"}
    if leak <= LEAK_OK:
        return {"level": "ok", "text": "z sieci nic nie sprzedano — zakaz dotrzymany"}
    if tol > 0 and leak <= tol:
        return {"level": "ok", "text": f"w granicach tolerancji blokady ({fmt(tol)} kWh)"}
    if tol <= 0:
        return {"level": "warn", "text": "blokada arbitrażu jest wyłączona w ustawieniach — nic nie pilnuje tego zakazu"}
    return {"level": "bad", "text": f"możliwe sprzedanie energii z sieci (ponad tolerancję {fmt(tol)} kWh) — sprawdź dziennik decyzji"}


def row(day: str, rec: dict[str, Any], tol: float) -> dict[str, Any]:
    v = verdict(rec, tol)
    return {"date": day, "in": round(_n(rec.get("in")) or 0.0, 2), "out": round(_n(rec.get("out")) or 0.0, 2),
            "leak": round(_n(rec.get("leak")) or 0.0, 2), "level": v["level"], "text": v["text"]}


def rows(store: Any, n: int, tol: float) -> list[dict[str, Any]]:
    """Ostatnie `n` dób, najnowsze pierwsze."""
    st = clean(store)
    return [row(k, st[k], tol) for k in sorted(st, reverse=True)[:max(0, int(n))]]


def line(r: dict[str, Any]) -> str:
    """Jedno zdanie do podsumowania dnia."""
    d = str(r["date"])
    return (f"Arbitraż {d[8:10]}.{d[5:7]}: z sieci do baterii {fmt(r['in'])} kWh, z baterii do sieci {fmt(r['out'])} kWh, "
            f"z sieci sprzedane {fmt(r['leak'])} kWh — {r['text']}")


def week_line(store: Any, start: str, end: str, tol: float) -> str | None:
    """Suma za okres [start, end] (daty ISO) do raportu tygodniowego; None, gdy nic się nie działo."""
    st = clean(store)
    days = [k for k in st if start <= k <= end]
    if not days:
        return None
    tot = {f: sum(st[k][f] for k in days) for f in KEYS}
    if tot["in"] < IDLE_KWH and tot["out"] < IDLE_KWH:
        return None
    worst = max((verdict(st[k], tol)["level"] for k in days), key=lambda lv: {"idle": 0, "ok": 1, "warn": 2, "bad": 3}[lv])
    tail = {"bad": "UWAGA: w którejś dobie mogło dojść do arbitrażu", "warn": "blokada arbitrażu wyłączona"}.get(worst, "zakaz dotrzymany")
    return (f"Arbitraż ({len(days)} dób): z sieci do baterii {fmt(tot['in'])} kWh, z baterii do sieci {fmt(tot['out'])} kWh, "
            f"z sieci sprzedane {fmt(tot['leak'])} kWh — {tail}")
