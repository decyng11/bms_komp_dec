"""Powiadomienie „plan na jutro”: po opublikowaniu cen na jutro jedno krótkie zdanie z planu 24–48 h — kiedy ładowanie
z sieci, kiedy sprzedaż z baterii, ile można na tym zarobić i ile PV jest prognozowane. Czyste funkcje, bez Home Assistanta."""
from __future__ import annotations

import math
from typing import Any

# Zestawy (start, stop) w tej samej kolejności co w planerze: zestaw 1 i zestaw 2.
SALE_SETS = (("bateria_sprzedaz_start", "bateria_sprzedaz_stop"), ("bateria_sprzedaz_start_2", "bateria_sprzedaz_stop_2"))
CHARGE_SETS = (("start_grid_charge", "stop_grid_charge"), ("start_grid_charge_2", "stop_grid_charge_2"))
TOMORROW = 1            # „sale_day” z planera: 0 = dziś, 1 = jutro


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _hm(v: Any) -> str | None:
    """Godzina z propozycji planera („18:00”, „06:00”) — tylko poprawny zapis HH:MM, inaczej None."""
    s = str(v or "").strip()[:5]
    if len(s) == 5 and s[2] == ":" and s[:2].isdigit() and s[3:].isdigit() and int(s[:2]) < 24 and int(s[3:]) < 60:
        return s
    return None


def _active(p: Any) -> bool:
    return isinstance(p, dict) and bool(p.get("proposed")) and not p.get("skip")


def summarize(proposals: Any, pv_kwh: float | None = None) -> dict[str, Any]:
    """Z propozycji planera wybiera to, co dotyczy jutra: okna ładowania z sieci i sprzedaży z baterii (tylko niepominięte)."""
    props = proposals if isinstance(proposals, dict) else {}
    charges, sales = [], []
    for ks, ke in CHARGE_SETS:
        a, b = props.get(ks), props.get(ke)
        if _active(a) and _active(b) and _hm(a.get("proposed")) and _hm(b.get("proposed")):
            charges.append({"start": _hm(a["proposed"]), "stop": _hm(b["proposed"])})
    gain = 0.0
    for ks, ke in SALE_SETS:
        a, b = props.get(ks), props.get(ke)
        if not (_active(a) and _active(b) and a.get("sale_day") == TOMORROW and _hm(a.get("proposed")) and _hm(b.get("proposed"))):
            continue
        kwh, net = _num(a.get("sale_kwh")), _num(a.get("gain_pln"))
        sales.append({"start": _hm(a["proposed"]), "stop": _hm(b["proposed"]), "kwh": kwh, "gain": net})
        if net is not None:
            gain += net
    return {"charges": charges, "sales": sales, "gain": round(gain, 2) if any(s["gain"] is not None for s in sales) else None,
            "pv_kwh": _num(pv_kwh)}


def _f(v: float, n: int = 1) -> str:
    return f"{v:.{n}f}".replace(".", ",")


def message(info: dict[str, Any], day_label: str = "jutro") -> str:
    """Jedno–dwa zdania po polsku. Gdy plan niczego nie przewiduje, mówi to wprost (też to jest informacja)."""
    parts = []
    for c in info.get("charges") or []:
        parts.append(f"ładowanie z sieci {c['start']}–{c['stop']}")
    for s in info.get("sales") or []:
        extra = []
        if s.get("kwh") is not None:
            extra.append(f"~{_f(s['kwh'])} kWh")
        if s.get("gain") is not None:
            extra.append(f"zysk ~{_f(s['gain'], 2)} zł")
        parts.append(f"sprzedaż z baterii {s['start']}–{s['stop']}" + (f" ({', '.join(extra)})" if extra else ""))
    if parts:
        txt = f"Plan na {day_label}: " + "; ".join(parts) + "."
        if info.get("gain") is not None and len(info.get("sales") or []) > 1:
            txt += f" Razem ze sprzedaży ok. {_f(info['gain'], 2)} zł."
    else:
        txt = f"Plan na {day_label}: bez ładowania z sieci i bez sprzedaży z baterii — dom jedzie na własnym PV i baterii."
    if info.get("pv_kwh") is not None:
        txt += f" Prognoza PV: {_f(info['pv_kwh'])} kWh."
    if info.get("windows"):
        txt += f" Ceny zakupu: {info['windows']} Dobry czas na pralkę, zmywarkę czy bojler."
    return txt
