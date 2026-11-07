"""Raport miesięczny: bilans z/do sieci, bateria, autokonsumpcja i (oznaczone jako szacunek) oszczędności."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Any

MONTHS_PL = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień",
             "wrzesień", "październik", "listopad", "grudzień"]


def _r(v: float | None, n: int = 2) -> float | None:
    return None if v is None else round(float(v), n)


def monthly_report(ledger, stats, year: int, month: int, cap_kwh: float) -> dict[str, Any]:
    """Raport za miesiąc na podstawie księgi zysków (ledger) i dziennych liczników (stats).

    Wartości z księgi (przychód, koszt, kWh z/do sieci) są całkowane z mocy sieci i cen chwilowych.
    „Oszczędność” to SZACUNEK: ile kosztowałby prąd zużyty w domu po średniej cenie zakupu z tego miesiąca,
    pomniejszone o faktyczny bilans z siecią — nie uwzględnia opłat stałych."""
    prefix = f"{year:04d}-{month:02d}-"
    ndays = monthrange(year, month)[1]
    days = {k: v for k, v in ledger.days.items() if k.startswith(prefix)}
    sdays = {k: v for k, v in stats.days.items() if k.startswith(prefix)}

    revenue = sum(d["revenue"] for d in days.values())
    cost = sum(d["cost"] for d in days.values())
    exp_kwh = sum(d["export_kwh"] for d in days.values())
    imp_kwh = sum(d["import_kwh"] for d in days.values())
    neg_kwh = sum(d["neg_export_kwh"] for d in days.values())
    net = revenue - cost

    def tot(f: str) -> tuple[float, int]:
        vals = [d[f] for d in sdays.values() if f in d]
        return sum(vals), len(vals)

    pv, n_pv = tot("pv")
    load, n_load = tot("load")
    chg, _ = tot("chg")
    dis, _ = tot("dis")
    m_exp, _ = tot("exp")
    m_imp, _ = tot("imp")

    avg_sell = revenue / exp_kwh if exp_kwh > 0 else None
    avg_buy = cost / imp_kwh if imp_kwh > 0 else None
    self_cons = ((pv - m_exp) / pv * 100.0) if n_pv >= 3 and pv > 1 and m_exp >= 0 else None
    self_suff = ((1.0 - m_imp / load) * 100.0) if n_load >= 3 and load > 1 and m_imp >= 0 else None
    saving = None
    if avg_buy is not None and n_load >= 3 and load > 1:
        saving = load * avg_buy + net        # rachunek bez PV/baterii − faktyczny koszt netto (szacunek)

    nets = sorted(((k, ledger.net(v)) for k, v in days.items()), key=lambda x: x[1])
    eff, n_eff = stats.period_efficiency(prefix, cap_kwh)
    out = {
        "year": year, "month": month, "title": f"{MONTHS_PL[month - 1].capitalize()} {year}",
        "days_with_data": len(days), "days_in_month": ndays,
        "revenue": _r(revenue), "cost": _r(cost), "net": _r(net),
        "export_kwh": _r(exp_kwh), "import_kwh": _r(imp_kwh), "neg_export_kwh": _r(neg_kwh),
        "avg_sell_price": _r(avg_sell, 3), "avg_buy_price": _r(avg_buy, 3),
        "pv_kwh": _r(pv, 1) if n_pv else None, "load_kwh": _r(load, 1) if n_load else None,
        "battery_charge_kwh": _r(chg, 1) if sdays else None, "battery_discharge_kwh": _r(dis, 1) if sdays else None,
        "self_consumption_pct": _r(self_cons, 0), "self_sufficiency_pct": _r(self_suff, 0),
        "saving_estimate": _r(saving),
        "best_day": ({"date": nets[-1][0], "net": _r(nets[-1][1])} if nets else None),
        "worst_day": ({"date": nets[0][0], "net": _r(nets[0][1])} if nets else None),
        "cycle_efficiency_pct": _r(eff * 100.0, 1) if eff is not None else None,
        "cycle_efficiency_days": n_eff,
        "days": [{"date": k, "net": _r(ledger.net(v)), "export_kwh": _r(v["export_kwh"]), "import_kwh": _r(v["import_kwh"])}
                 for k, v in sorted(days.items())],
        "complete": len(days) >= ndays - 1,
    }
    return out


def report_text(rep: dict[str, Any]) -> str:
    """Krótka wersja tekstowa do powiadomienia."""
    lines = [f"Raport EMS — {rep['title']}",
             f"Bilans z siecią: {rep['net']:+.2f} zł (sprzedaż {rep['revenue']:.2f} zł − zakup {rep['cost']:.2f} zł)",
             f"Energia: eksport {rep['export_kwh']:.1f} kWh, import {rep['import_kwh']:.1f} kWh"]
    if rep.get("pv_kwh") is not None:
        extra = f"Produkcja PV {rep['pv_kwh']:.0f} kWh"
        if rep.get("self_consumption_pct") is not None:
            extra += f", autokonsumpcja {rep['self_consumption_pct']:.0f}%"
        lines.append(extra)
    if rep.get("saving_estimate") is not None:
        lines.append(f"Szacowana oszczędność względem braku PV i baterii: ok. {rep['saving_estimate']:.0f} zł (orientacyjnie)")
    if rep.get("best_day"):
        lines.append(f"Najlepszy dzień: {rep['best_day']['date']} ({rep['best_day']['net']:+.2f} zł)")
    if rep.get("days_with_data", 0) < rep.get("days_in_month", 0) - 1:
        lines.append(f"Uwaga: dane z {rep['days_with_data']} z {rep['days_in_month']} dni.")
    return "\n".join(lines)


def period_totals(ledger, stats, start: date, end: date) -> dict[str, Any]:
    """Sumy za dni [start, end] (włącznie): bilans, energia z/do sieci, PV, dom, bateria; najlepszy i najgorszy dzień."""
    keys = []
    d = start
    while d <= end:
        keys.append(d.isoformat())
        d += timedelta(days=1)
    lds = {k: ledger.days[k] for k in keys if k in ledger.days}
    sds = {k: stats.days[k] for k in keys if k in stats.days}
    rev = sum(v["revenue"] for v in lds.values())
    cost = sum(v["cost"] for v in lds.values())

    def tot(f: str) -> float | None:
        vals = [v[f] for v in sds.values() if f in v]
        return round(sum(vals), 1) if vals else None

    nets = sorted(((k, ledger.net(v)) for k, v in lds.items()), key=lambda x: x[1])
    pv, exp_ = tot("pv"), tot("exp")
    return {
        "days": len(lds), "revenue": round(rev, 2), "cost": round(cost, 2), "net": round(rev - cost, 2),
        "export_kwh": round(sum(v["export_kwh"] for v in lds.values()), 1),
        "import_kwh": round(sum(v["import_kwh"] for v in lds.values()), 1),
        "pv_kwh": pv, "load_kwh": tot("load"), "chg_kwh": tot("chg"), "dis_kwh": tot("dis"),
        "self_consumption_pct": (round((pv - exp_) / pv * 100.0) if pv and pv > 1 and exp_ is not None else None),
        "best": nets[-1] if nets else None, "worst": nets[0] if nets else None,
    }


def _zl(v: float | None) -> str:
    return "—" if v is None else f"{v:+.2f} zł".replace(".", ",")


def _kwh(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f} kWh".replace(".", ",")


def totals_lines(t: dict[str, Any]) -> list[str]:
    lines = [f"Bilans z siecią: {_zl(t['net'])} (sprzedaż {t['revenue']:.2f} zł − zakup {t['cost']:.2f} zł)".replace(".", ","),
             f"Sieć: eksport {_kwh(t['export_kwh'])}, import {_kwh(t['import_kwh'])}"]
    parts = []
    if t.get("pv_kwh") is not None:
        parts.append(f"PV {_kwh(t['pv_kwh'])}" + (f" (autokonsumpcja {t['self_consumption_pct']}%)" if t.get("self_consumption_pct") is not None else ""))
    if t.get("load_kwh") is not None:
        parts.append(f"dom {_kwh(t['load_kwh'])}")
    if parts:
        lines.append("Energia: " + ", ".join(parts))
    if t.get("chg_kwh") is not None:
        lines.append(f"Bateria: ładowanie {_kwh(t['chg_kwh'])}, rozładowanie {_kwh(t.get('dis_kwh'))}")
    return lines


def compare_line(cur: float | None, prev: float | None, label: str) -> str | None:
    if cur is None or prev is None:
        return None
    d = cur - prev
    return f"Względem {label}: {_zl(d)} ({'lepiej' if d >= 0 else 'gorzej'})"
