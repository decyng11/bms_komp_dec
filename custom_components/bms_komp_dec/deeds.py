"""„Co EMS zrobił za Ciebie”: licznik miesięczny zdarzeń z dziennika decyzji, które pokazują wartość systemu.

Dziennik trzyma tylko ostatnie ~300 wpisów, więc zdarzenia liczymy na bieżąco (jeden wpis dziennika = jedno zliczenie) i zapisujemy
w stanie runtime po miesiącach. Czyste funkcje, bez HA."""
from __future__ import annotations

import math
from typing import Any

KEEP_MONTHS = 13
KINDS = ("blocked", "sale_stop", "guard", "auto", "commands")
LABELS = {
    "blocked": "zablokował ryzykowny zapis do falownika",
    "sale_stop": "zatrzymał sprzedaż z baterii",
    "guard": "uruchomił inne zabezpieczenia",
    "auto": "zastosował zmiany harmonogramu automatycznie",
    "commands": "wykonał komend sterujących",
}


def classify(entry: Any) -> str | None:
    """Do której kategorii należy wpis dziennika decyzji (None = nie liczymy)."""
    if not isinstance(entry, dict):
        return None
    kind, level, msg = entry.get("kind"), entry.get("level"), str(entry.get("msg") or "")
    if kind == "guard" and level == "warn":
        if "ZABLOKOWANA" in msg:
            return "blocked"
        if msg.startswith("Zatrzymuję sprzedaż"):
            return "sale_stop"
        return "guard"
    if kind == "auto" and level == "ok" and msg.startswith("Auto-zastosowano"):
        return "auto"
    if kind == "command" and level == "ok":
        return "commands"
    return None


def bump(store: Any, month: str, cat: str) -> dict[str, dict[str, int]]:
    """Dolicza 1 do kategorii w miesiącu; zwraca oczyszczony zapis (maks. KEEP_MONTHS miesięcy)."""
    st = clean(store)
    if cat in KINDS and isinstance(month, str) and len(month) == 7:
        m = st.setdefault(month, {})
        m[cat] = m.get(cat, 0) + 1
    for k in sorted(st)[:-KEEP_MONTHS]:
        st.pop(k, None)
    return st


def clean(store: Any) -> dict[str, dict[str, int]]:
    """Zapis po wczytaniu z pliku: tylko miesiące „RRRR-MM” i znane kategorie z nieujemnymi liczbami całkowitymi."""
    out: dict[str, dict[str, int]] = {}
    if not isinstance(store, dict):
        return out
    for k, v in store.items():
        if not (isinstance(k, str) and len(k) == 7 and k[4] == "-" and k[:4].isdigit() and k[5:].isdigit() and isinstance(v, dict)):
            continue
        row = {}
        for c in KINDS:
            n = v.get(c)
            if isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) and 0 <= n < 10_000_000:
                row[c] = int(n)
        out[k] = row
    return out


def summary(store: Any, month: str) -> dict[str, Any]:
    """{'month', 'counts': {kategoria: n}, 'total', 'text'} — text pusty, gdy w miesiącu nic się nie wydarzyło."""
    row = clean(store).get(month, {})
    counts = {c: row.get(c, 0) for c in KINDS}
    parts = [f"{counts[c]}× {LABELS[c]}" if c != "commands" else f"{counts[c]} {LABELS[c]}" for c in KINDS if counts[c]]
    return {"month": month, "counts": counts, "total": sum(counts.values()),
            "text": ("W tym miesiącu EMS: " + "; ".join(parts) + ".") if parts else ""}
