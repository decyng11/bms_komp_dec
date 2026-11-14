"""Widoki planu dla panelu: tabela godzina po godzinie (13), „Dlaczego?” (17), historia SOC z oknami (20).

Same funkcje czyste (bez HA) — liczą na danych, które plan i Insights już mają."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

# kolejność pól koszyka Insights (zgodna z insights.py: LOAD, PV, IMP, EXP, BCH, BDIS, BUY_S, BUY_T, SELL_S, SELL_T, SOC)
_LOAD, _PV, _IMP, _EXP, _BCH, _BDIS, _BUY_S, _BUY_T, _SELL_S, _SELL_T, _SOC = range(11)

ACTIONS = {
    "grid": "Ładuj z sieci",
    "sell": "Sprzedaj z baterii",
    "pv": "Ładuj z PV",
    "home": "Bateria zasila dom",
    "idle": "Bez zmian",
}
MOVE_KWH = 0.05          # zmiana energii w baterii poniżej tego progu w godzinie = „bez zmian”


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def plan_table(curve: dict | None, cap_kwh: float) -> dict[str, Any]:
    """Tabela planu z krzywej: godzina, akcja, ceny, PV, zużycie, SOC i szacunkowy koszt godziny (zł; ujemny = przychód).

    Koszt = (import × cena zakupu) − (eksport × cena sprzedaży), gdzie przepływ z siecią wynika z bilansu godziny:
    PV − zużycie − zmiana energii w baterii. To SZACUNEK z planu (bez strat i opłat stałych)."""
    if not isinstance(curve, dict) or not curve.get("soc"):
        return {"rows": [], "totals": None}
    try:
        t0 = datetime.fromisoformat(str(curve.get("start")))
    except (TypeError, ValueError):
        return {"rows": [], "totals": None}
    soc = [_num(x) for x in curve["soc"]]
    n = len(soc)

    def col(name: str) -> list:
        arr = curve.get(name) or []
        return list(arr) + [None] * (n - len(arr))

    pv, load, buy, sell = col("pv"), col("load"), col("buy"), col("sell")
    peak, grid, sale, floor = col("peak"), col("grid"), col("sale"), col("floor")
    prev = _num(curve.get("soc_now"))
    cap = max(0.1, float(cap_kwh or 0.1))
    rows: list[dict[str, Any]] = []
    tot = {"import_kwh": 0.0, "export_kwh": 0.0, "cost": 0.0, "grid_kwh": 0.0, "sell_kwh": 0.0}
    for i in range(n):
        s = soc[i]
        if s is None:
            continue
        d_kwh = 0.0 if prev is None else (s - prev) / 100.0 * cap
        prev = s
        p, l = _num(pv[i]) or 0.0, _num(load[i]) or 0.0
        flow = p - l - d_kwh                       # > 0 = nadwyżka do sieci, < 0 = pobór z sieci
        imp, exp = max(0.0, -flow), max(0.0, flow)
        b, sl = _num(buy[i]), _num(sell[i])
        cost = (imp * b if b is not None else 0.0) - (exp * sl if sl is not None else 0.0)
        if grid[i]:
            kind = "grid"
        elif sale[i]:
            kind = "sell"
        elif d_kwh > MOVE_KWH:
            kind = "pv" if p > l else "grid" if imp > 0.2 else "pv"
        elif d_kwh < -MOVE_KWH:
            kind = "home"
        else:
            kind = "idle"
        if kind == "grid":
            tot["grid_kwh"] += max(0.0, d_kwh)
        if kind == "sell":
            tot["sell_kwh"] += max(0.0, -d_kwh)
        tot["import_kwh"] += imp
        tot["export_kwh"] += exp
        tot["cost"] += cost
        t = t0 + timedelta(hours=i)
        rows.append({
            "t": t.isoformat(), "h": t.hour, "day": t.date().isoformat(),
            "action": kind, "label": ACTIONS[kind], "peak": bool(peak[i]),
            "buy": b, "sell": sl, "pv": round(p, 2), "load": round(l, 2),
            "soc": round(s, 1), "floor": _num(floor[i]),
            "import_kwh": round(imp, 2), "export_kwh": round(exp, 2), "cost": round(cost, 2),
        })
    return {"rows": rows, "totals": {k: round(v, 2) for k, v in tot.items()}}


def soc_history(buckets_by_day: dict[str, list], plan_by_day: dict[str, list | None] | None = None,
                days: int = 7, today: date | None = None) -> list[dict[str, Any]]:
    """Godzinowy SOC z kilku ostatnich dób wraz ze znacznikami: ładowanie z sieci / sprzedaż (z koszyków Insights).

    Ładowanie z sieci = import ≥ 0,3 kWh i ładowanie baterii ≥ 0,3 kWh w tej godzinie; sprzedaż = eksport ≥ 0,3 kWh
    przy rozładowaniu baterii ≥ 0,3 kWh i produkcji PV poniżej eksportu. To oszacowanie z liczników godzinowych."""
    today = today or date.today()
    out = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        b = buckets_by_day.get(d) or [None] * 24
        soc, grid, sale = [], [], []
        for h in range(24):
            x = b[h] if h < len(b) else None
            if x is None:
                soc.append(None); grid.append(0); sale.append(0)
                continue
            s = _num(x[_SOC])
            soc.append(None if s is None else round(s, 1))
            grid.append(1 if x[_IMP] >= 0.3 and x[_BCH] >= 0.3 else 0)
            sale.append(1 if x[_EXP] >= 0.3 and x[_BDIS] >= 0.3 and x[_PV] < x[_EXP] else 0)
        if not any(v is not None for v in soc):
            out.append({"date": d, "soc": soc, "grid": grid, "sale": sale, "plan": None, "empty": True})
            continue
        plan = (plan_by_day or {}).get(d)
        out.append({"date": d, "soc": soc, "grid": grid, "sale": sale,
                    "plan": plan if isinstance(plan, list) else None, "empty": False})
    return out


def why_now(rt: Any, now: datetime) -> dict[str, Any]:
    """Jedno zdanie: co EMS teraz robi i dlaczego (+ krótkie powody poboczne). Kolejność = ważność."""
    parts: list[str] = []
    kind, text = "idle", ""

    def add(p: str | None) -> None:
        if p:
            parts.append(p)

    soc = None
    try:
        soc = rt.soc()
    except Exception:  # noqa: BLE001
        pass
    ovr = rt.override_active(now) if hasattr(rt, "override_active") else []
    selling = grid_chg = False
    try:
        selling, grid_chg = bool(rt.is_selling()), bool(rt.grid_charging_on())
    except Exception:  # noqa: BLE001
        pass
    block = None
    try:
        block = rt.sell_block_reason(strict_grid=False)
    except Exception:  # noqa: BLE001
        pass
    for o in ovr:
        add(rt.override_text(o))
    if rt.storm_active():
        kind, text = "storm", "Tryb burzowy: bateria zostaje naładowana na wypadek awarii sieci, nic nie sprzedaję."
    elif rt.vacation_active():
        kind, text = "vacation", "Tryb urlopowy: ograniczam zużycie, bateria pracuje oszczędnie."
    elif selling:
        px = rt.sell_price()
        kind = "sell"
        text = "Sprzedaję energię z baterii do sieci" + (f" (cena {px:.2f} zł/kWh)" if px is not None else "") + \
               " — to najdroższe godziny, a plan zostawia rezerwę na noc."
    elif grid_chg:
        kind = "grid"
        tgt = (rt.state.get("grid_target_plan") or {}).get("target")
        text = "Ładuję baterię z sieci, bo teraz prąd jest tani" + (f" — do {tgt:.0f}%." if isinstance(tgt, (int, float)) else ".")
    else:
        pvw = None
        try:
            pvw = float((rt.coordinator.data or {}).get("pv_power"))
        except (TypeError, ValueError):
            pass
        if soc is not None and pvw is not None and pvw > 300 and soc < 99:
            kind, text = "pv", "Ładuję baterię z własnej produkcji PV; nadwyżka trafi do sieci dopiero po naładowaniu."
        elif soc is not None and soc >= 99:
            kind, text = "full", "Bateria jest pełna — dom korzysta z PV, nadwyżka idzie do sieci."
        else:
            kind, text = "home", "Bateria zasila dom; czekam na tanie godziny albo okno sprzedaży z planu."
    if block and not selling:
        add("Sprzedaż zablokowana: " + str(block) + ".")
    gb = None
    try:
        gb = rt.grid_batt_kwh()
    except Exception:  # noqa: BLE001
        pass
    if gb and gb >= 0.5 and not block:
        add(f"W baterii jest ~{gb:.1f} kWh energii z sieci — nie sprzedaję jej.")
    nxt = None
    try:
        nxt = rt.next_window_text(now)
    except Exception:  # noqa: BLE001
        pass
    if nxt:
        add(nxt)
    return {"kind": kind, "text": text, "details": parts[:5], "soc": None if soc is None else round(float(soc), 1)}
