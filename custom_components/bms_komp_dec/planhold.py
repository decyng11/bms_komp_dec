"""Stabilizacja planu: nowe godziny okien zastępują stare dopiero wtedy, gdy to ma sens.

Zasady (para start/stop liczy się jako jedno okno):
- okno, które trwa albo zaczyna się w ciągu FREEZE_MIN minut, nie zmienia godzin (zamrożenie);
- inne zmiany godzin wchodzą po CONFIRM_N kolejnych przeliczeniach z tym samym wynikiem (potwierdzenie);
- wyraźnie lepszy wynik (zysk wyższy o BIG_GAIN_PLN) wchodzi od razu (histereza);
- pojawienie się / zniknięcie okna (skip) i zmiany bez poprzedniego okna przechodzą bez zwłoki.
"""
from __future__ import annotations

from typing import Any

PAIRS = (
    ("bateria_sprzedaz_start", "bateria_sprzedaz_stop"),
    ("bateria_sprzedaz_start_2", "bateria_sprzedaz_stop_2"),
    ("start_grid_charge", "stop_grid_charge"),
    ("start_grid_charge_2", "stop_grid_charge_2"),
)
FREEZE_MIN = 120
CONFIRM_N = 2
BIG_GAIN_PLN = 1.0


def _min(v: Any) -> int | None:
    try:
        h, m = str(v).split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return None


def _active(p: Any) -> bool:
    return isinstance(p, dict) and bool(p.get("proposed")) and not p.get("skip")


def _frozen(start: Any, stop: Any, cur_min: int) -> bool:
    s, e = _min(start), _min(stop)
    if s is None or e is None or s == e:
        return False
    inside = (cur_min - s) % 1440 < (e - s) % 1440
    until = (s - cur_min) % 1440
    return inside or 0 < until <= FREEZE_MIN


def stabilize(prev: dict | None, new: dict, hold: dict, cur_min: int, force: bool = False) -> list[str]:
    """Modyfikuje new["proposals"] w miejscu; zwraca opisy zmian i wstrzymań do dziennika. hold = pamięć kandydatów."""
    notes: list[str] = []
    pp = (prev or {}).get("proposals") or {}
    np_ = new.get("proposals") or {}
    if force or not pp:
        hold.clear()
        return notes
    for k1, k2 in PAIRS:
        o1, o2, n1, n2 = pp.get(k1), pp.get(k2), np_.get(k1), np_.get(k2)
        if not (_active(o1) and _active(o2) and _active(n1) and _active(n2)):
            hold.pop(k1, None)
            continue
        old = (str(o1["proposed"]), str(o2["proposed"]))
        cand = (str(n1["proposed"]), str(n2["proposed"]))
        if cand == old:
            hold.pop(k1, None)
            continue
        label = str(n1.get("label") or k1)
        why = None
        if _frozen(old[0], old[1], cur_min):
            why = f"okno {old[0]}–{old[1]} trwa albo zaczyna się za mniej niż {FREEZE_MIN // 60} h — nie zmieniam go"
            h = hold.get(k1)
            if not (h and h.get("cand") == list(cand)):
                hold[k1] = {"cand": list(cand), "n": 0, "logged": False}
        else:
            h = hold.get(k1)
            cnt = h["n"] + 1 if h and h.get("cand") == list(cand) else 1
            og, ng = o1.get("gain_pln"), n1.get("gain_pln")
            big = isinstance(og, (int, float)) and isinstance(ng, (int, float)) and ng - og >= BIG_GAIN_PLN
            if cnt >= CONFIRM_N or big:
                hold.pop(k1, None)
                notes.append(f"Plan: {label} zmienione {old[0]}–{old[1]} → {cand[0]}–{cand[1]}"
                             + (f" (zysk {og:.2f} → {ng:.2f} zł)" if isinstance(og, (int, float)) and isinstance(ng, (int, float)) else
                                f" (potwierdzone {cnt}× z rzędu)"))
                continue
            hold[k1] = {"cand": list(cand), "n": cnt}
            why = f"zmiana na {cand[0]}–{cand[1]} czeka na potwierdzenie ({cnt}/{CONFIRM_N})"
        for kk, o in ((k1, o1), (k2, o2)):
            np_[kk] = dict(o)
        h = hold.get(k1)
        if h is not None and not h.get("logged"):
            h["logged"] = True
            notes.append(f"Plan: {label} zostaje {old[0]}–{old[1]} — {why}")
    return notes
