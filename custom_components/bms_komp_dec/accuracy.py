"""Trafność prognoz: porównanie prognozy dnia (zużycie, PV) z faktem. Czyste funkcje — bez zależności od HA."""
from __future__ import annotations

from typing import Any

KEEP_DAYS = 45          # tyle dni trzymamy w pamięci integracji
MIN_ACTUAL_KWH = 0.5    # poniżej tego błąd procentowy nie ma sensu (np. PV w nocy / przy awarii pomiaru)
WINDOW_DAYS = 7


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def day_error(fc: Any, actual: Any) -> float | None:
    """Błąd prognozy w % faktu: dodatni = prognoza zawyżona, ujemny = zaniżona. None, gdy brak sensownych danych."""
    f, a = _num(fc), _num(actual)
    if f is None or a is None or a < MIN_ACTUAL_KWH or f < 0:
        return None
    return round((f - a) / a * 100.0, 1)


def add_day(history: list, date: str, load_fc: Any, load: Any, pv_fc: Any, pv: Any) -> list:
    """Dopisuje (albo nadpisuje) wpis dnia; zwraca listę przyciętą do KEEP_DAYS, posortowaną po dacie."""
    rows = [r for r in (history or []) if isinstance(r, dict) and r.get("date") != date]
    row = {"date": date,
           "load_fc": _num(load_fc), "load": _num(load), "pv_fc": _num(pv_fc), "pv": _num(pv)}
    row["load_err"] = day_error(row["load_fc"], row["load"])
    row["pv_err"] = day_error(row["pv_fc"], row["pv"])
    if row["load_err"] is None and row["pv_err"] is None:
        return sorted(rows, key=lambda r: str(r.get("date")))[-KEEP_DAYS:]
    rows.append(row)
    return sorted(rows, key=lambda r: str(r.get("date")))[-KEEP_DAYS:]


def _stats(errs: list[float]) -> dict[str, Any] | None:
    if not errs:
        return None
    return {"n": len(errs), "mae_pct": round(sum(abs(e) for e in errs) / len(errs), 1),
            "bias_pct": round(sum(errs) / len(errs), 1)}


def summary(history: list, window: int = WINDOW_DAYS) -> dict[str, Any]:
    """Średni błąd bezwzględny i stałe odchylenie z ostatnich `window` dni z danymi, osobno dla zużycia i PV."""
    rows = [r for r in (history or []) if isinstance(r, dict)][-window:]
    return {
        "load": _stats([r["load_err"] for r in rows if _num(r.get("load_err")) is not None]),
        "pv": _stats([r["pv_err"] for r in rows if _num(r.get("pv_err")) is not None]),
        "days": [{"date": r.get("date"), "load_err": r.get("load_err"), "pv_err": r.get("pv_err")} for r in rows],
    }


def describe(stats: dict | None, what: str) -> str | None:
    """Jedno zdanie po polsku, np. „zużycie: średnio ±8% (prognoza zwykle zawyżona o 5%)”."""
    if not stats:
        return None
    b = stats["bias_pct"]
    tail = "" if abs(b) < 3 else f" (prognoza zwykle {'zawyżona' if b > 0 else 'zaniżona'} o {abs(b):.0f}%)"
    return f"{what}: średnio ±{stats['mae_pct']:.0f}%{tail}"
