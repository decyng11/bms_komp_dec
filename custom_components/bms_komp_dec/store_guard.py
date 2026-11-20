"""Kontrola plików zapisu (.storage) przy wczytywaniu: księga zysków, statystyki baterii, nauczone ceny, historia zużycia, urządzenia.

Plik mógł zostać zmieniony ręcznie, uciąć się przy awarii zasilania albo pochodzić ze starszej wersji. Zły kształt albo
wartość „nan”/„inf” w jednym wpisie nie może zatrzymać startu integracji ani po cichu zatruć sum (jedno „nan” w księdze
zysków psuło wszystkie późniejsze bilanse). Niepoprawny wpis jest pomijany, a to, co pominięto, trafia do `Integrity` —
runtime po starcie zapisuje kopię oryginału, dopisuje wpis do dziennika i wysyła powiadomienie „Naprawiono uszkodzone dane”."""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

MAX_NOTES = 10
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Integrity:
    """Co zostało naprawione w jednym pliku zapisu przy wczytywaniu."""

    def __init__(self, key: str, label: str) -> None:
        self.key = key                      # klucz pliku w .storage (kopia: „<klucz>_backup”)
        self.label = label                  # nazwa po polsku do powiadomienia
        self.notes: list[str] = []
        self.raw: Any = None                # oryginał sprzed naprawy (trafia do kopii)

    def note(self, text: str, raw: Any = None) -> None:
        if self.raw is None and raw is not None:
            self.raw = raw
        if text not in self.notes and len(self.notes) < MAX_NOTES:
            self.notes.append(text)

    def __bool__(self) -> bool:
        return bool(self.notes)

    def summary(self) -> str:
        return f"{self.label}: " + "; ".join(self.notes)


def num(v: Any, lo: float | None = None, hi: float | None = None) -> float | None:
    """Skończona liczba (bez bool, „nan”, „inf”) z zakresu [lo, hi] albo None."""
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(x):
        return None
    if lo is not None and x < lo:
        return None
    if hi is not None and x > hi:
        return None
    return x


def is_day(k: Any) -> bool:
    if not isinstance(k, str) or not _DAY.match(k):
        return False
    try:
        date.fromisoformat(k)
    except ValueError:
        return False
    return True


def as_dict(v: Any, integ: Integrity, what: str, raw: Any = None) -> dict:
    """Słownik albo {} (z notatką, gdy w pliku jest co innego niż None/słownik)."""
    if isinstance(v, dict):
        return v
    if v is not None:
        integ.note(f"{what}: oczekiwano słownika, jest {type(v).__name__} — pominięto", raw)
    return {}


def clean_day_map(src: Any, fields: dict[str, tuple[float | None, float | None]], integ: Integrity, what: str,
                  raw: Any = None) -> dict[str, dict[str, float]]:
    """{data: {pole: liczba}} — zły klucz, zły wpis albo wartość spoza zakresu są pomijane i zliczane."""
    out: dict[str, dict[str, float]] = {}
    src = as_dict(src, integ, what, raw)
    bad_rows = bad_vals = 0
    for k, v in src.items():
        if not is_day(k) or not isinstance(v, dict):
            bad_rows += 1
            continue
        row: dict[str, float] = {}
        for f, (lo, hi) in fields.items():
            if f not in v or v[f] is None:
                continue
            x = num(v[f], lo, hi)
            if x is None:
                bad_vals += 1
                continue
            row[f] = x
        out[k] = row
    if bad_rows:
        integ.note(f"{what}: pominięto {bad_rows} uszkodzonych wpisów", raw)
    if bad_vals:
        integ.note(f"{what}: odrzucono {bad_vals} niepoprawnych liczb (nan/inf/poza zakresem)", raw)
    return out


def scrub(v: Any) -> Any:
    """Kopia struktury bez „nan”/„inf”: w słowniku klucz znika, w liście wartość wraca jako 0.0."""
    if isinstance(v, float):
        return v if math.isfinite(v) else 0.0
    if isinstance(v, dict):
        return {k: scrub(x) for k, x in v.items() if not (isinstance(x, float) and not math.isfinite(x))}
    if isinstance(v, list):
        return [scrub(x) for x in v]
    return v


def has_nonfinite(v: Any) -> bool:
    if isinstance(v, float):
        return not math.isfinite(v)
    if isinstance(v, dict):
        return any(has_nonfinite(x) for x in v.values())
    if isinstance(v, list):
        return any(has_nonfinite(x) for x in v)
    return False


# ------------------------------------------------------------------ zakresy pól (szerokie — chodzi o ślad uszkodzenia, nie o walidację fizyki)
LEDGER_FIELDS: dict[str, tuple[float | None, float | None]] = {
    "export_kwh": (0.0, 5000.0), "import_kwh": (0.0, 5000.0), "neg_export_kwh": (0.0, 5000.0), "peak_import_kwh": (0.0, 5000.0),
    "revenue": (-1e6, 1e6), "cost": (-1e6, 1e6),
}
STATS_FIELDS: dict[str, tuple[float | None, float | None]] = {
    "pv": (0.0, 5000.0), "load": (0.0, 5000.0), "imp": (0.0, 5000.0), "exp": (0.0, 5000.0), "chg": (0.0, 5000.0),
    "dis": (0.0, 5000.0), "soc0": (0.0, 100.0), "soc1": (0.0, 100.0), "t1h": (0.0, 24.0),
}


def clean_caps(src: Any, integ: Integrity, raw: Any = None) -> list[dict[str, Any]]:
    """Pomiary pojemności baterii: wpis musi być słownikiem z poprawną liczbą „cap”; pozostałe pola liczbowe — skończone."""
    if src is None:
        return []
    if not isinstance(src, list):
        integ.note(f"pomiary pojemności: oczekiwano listy, jest {type(src).__name__} — pominięto", raw)
        return []
    out: list[dict[str, Any]] = []
    bad = 0
    for c in src:
        if not isinstance(c, dict) or num(c.get("cap"), 0.1, 5000.0) is None:
            bad += 1
            continue
        row = {"cap": float(c["cap"])}
        for f in ("t", "dsoc", "e"):
            x = num(c.get(f))
            if x is not None:
                row[f] = int(x) if f == "t" else x
        out.append(row)
    if bad:
        integ.note(f"pomiary pojemności: pominięto {bad} uszkodzonych wpisów", raw)
    return out
