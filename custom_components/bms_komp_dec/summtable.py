"""Podsumowania w formie zwartej tabeli (dzień, tydzień, miesiąc) — zamiast kilku długich zdań.

Czyste funkcje (bez Home Assistanta). Tabela jest tekstem wyrównanym spacjami, a kolumny rozdziela „│”, dzięki czemu czyta się ją
także wtedy, gdy telefon pokazuje czcionkę o zmiennej szerokości (wtedy kolumny mogą się lekko rozjechać, ale nadal są rozdzielone).
Brak danych to „—”. Dodatkowe zdania (oszczędność, plan, zabezpieczenia) dokłada runtime pod tabelą."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

DAYS_SHORT = ("Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd")
DASH = "—"
SEP = " │ "


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def fmt(v: Any, nd: int = 1, sign: bool = False, unit: str = "") -> str:
    """Liczba po polsku (przecinek), z opcjonalnym znakiem i jednostką; brak danych → „—”."""
    x = _num(v)
    if x is None:
        return DASH
    x = round(x, nd)
    if x == 0:
        x = 0.0                                          # „-0,0” nie ma sensu
    s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
    return s.replace(".", ",") + unit


def render(header: list[str], rows: list[list[str]]) -> list[str]:
    """Tabela jako lista wierszy: pierwsza kolumna do lewej, reszta do prawej, kolumny rozdzielone „│”."""
    table = [header] + rows
    ncol = max(len(r) for r in table)
    table = [r + [""] * (ncol - len(r)) for r in table]
    widths = [max(len(r[i]) for r in table) for i in range(ncol)]
    out = []
    for r in table:
        cells = [r[0].ljust(widths[0])] + [r[i].rjust(widths[i]) for i in range(1, ncol)]
        out.append(SEP.join(cells).rstrip())
    return out


def _bat(t: dict[str, Any]) -> str:
    c, d = _num(t.get("chg_kwh")), _num(t.get("dis_kwh"))
    if c is None and d is None:
        return DASH
    return f"↑{fmt(c)} ↓{fmt(d)}"


def day_lines(cur: dict[str, Any], prev: dict[str, Any] | None) -> list[str]:
    """Dziś (albo wskazany dzień) obok dnia poprzedniego. cur/prev — wynik report.period_totals dla jednego dnia."""
    p = prev if isinstance(prev, dict) and prev.get("days") else None

    def col(t: dict[str, Any] | None, key: str, nd: int = 1, sign: bool = False) -> str:
        return fmt(t.get(key), nd, sign) if t else DASH

    rows = [
        ["Bilans zł", col(cur, "net", 2, True), col(p, "net", 2, True)],
        ["PV kWh", col(cur, "pv_kwh"), col(p, "pv_kwh")],
        ["Dom kWh", col(cur, "load_kwh"), col(p, "load_kwh")],
        ["Z sieci kWh", col(cur, "import_kwh"), col(p, "import_kwh")],
        ["Do sieci kWh", col(cur, "export_kwh"), col(p, "export_kwh")],
        ["Bateria kWh", _bat(cur), _bat(p) if p else DASH],
    ]
    if cur.get("self_consumption_pct") is not None:
        rows.append(["Autokonsumpcja", f"{cur['self_consumption_pct']:.0f}%", (f"{p['self_consumption_pct']:.0f}%" if p and p.get("self_consumption_pct") is not None else DASH)])
    return render(["", "dziś", "wczoraj"], rows)


def week_lines(days: list[tuple[date, dict[str, Any]]], prev_net: float | None = None) -> list[str]:
    """Siedem dni, jeden wiersz na dzień (+ „Razem”). days: (data, period_totals dla jednego dnia), od najstarszego.

    ▲ oznacza najlepszy bilans tygodnia, ▼ najsłabszy (tylko gdy dni z danymi jest co najmniej dwa)."""
    have = [(d, t) for d, t in days if isinstance(t, dict) and t.get("days")]
    best = max(have, key=lambda x: x[1]["net"])[0] if len(have) >= 2 else None
    worst = min(have, key=lambda x: x[1]["net"])[0] if len(have) >= 2 else None
    rows: list[list[str]] = []
    for d, t in days:
        label = f"{DAYS_SHORT[d.weekday()]} {d:%d.%m}"
        if not (isinstance(t, dict) and t.get("days")):
            rows.append([label, DASH, DASH, DASH, DASH])
            continue
        mark = " ▲" if d == best else (" ▼" if d == worst else "")
        rows.append([label + mark, fmt(t["net"], 2, True), fmt(t.get("pv_kwh")), fmt(t.get("load_kwh")), fmt(t.get("import_kwh"))])
    if have:
        def tot(k: str) -> float | None:
            vals = [_num(t.get(k)) for _, t in have if _num(t.get(k)) is not None]
            return sum(vals) if vals else None
        total_net = sum(t["net"] for _, t in have)
        rows.append(["Razem", fmt(total_net, 2, True), fmt(tot("pv_kwh")), fmt(tot("load_kwh")), fmt(tot("import_kwh"))])
        if prev_net is not None:
            rows.append(["Poprz. tydz.", fmt(prev_net, 2, True), "", "", ""])
    return render(["", "bilans zł", "PV", "dom", "z sieci"], rows)


def month_lines(cur: dict[str, Any], prev: dict[str, Any] | None) -> list[str]:
    """Miesiąc (wynik report.monthly_report) obok poprzedniego."""
    p = prev if isinstance(prev, dict) and prev.get("days_with_data") else None

    def col(t: dict[str, Any] | None, key: str, nd: int = 1, sign: bool = False, unit: str = "") -> str:
        return fmt(t.get(key), nd, sign, unit) if t else DASH

    rows = [
        ["Bilans zł", col(cur, "net", 2, True), col(p, "net", 2, True)],
        ["Sprzedaż kWh", col(cur, "export_kwh"), col(p, "export_kwh")],
        ["Zakup kWh", col(cur, "import_kwh"), col(p, "import_kwh")],
        ["PV kWh", col(cur, "pv_kwh", 0), col(p, "pv_kwh", 0)],
        ["Dom kWh", col(cur, "load_kwh", 0), col(p, "load_kwh", 0)],
        ["Autokonsumpcja", col(cur, "self_consumption_pct", 0, unit="%"), col(p, "self_consumption_pct", 0, unit="%")],
        ["Oszczędność zł*", col(cur, "saving_estimate", 0), col(p, "saving_estimate", 0)],
    ]
    return render(["", str(cur.get("title") or "miesiąc"), str(p.get("title")) if p else "poprzedni"], rows)


def week_days(period_totals_fn, start: date, end: date) -> list[tuple[date, dict[str, Any]]]:
    """Wynik period_totals osobno dla każdego dnia z przedziału [start, end]."""
    out = []
    d = start
    while d <= end:
        out.append((d, period_totals_fn(d, d)))
        d += timedelta(days=1)
    return out
