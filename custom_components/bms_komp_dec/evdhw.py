"""Logika ładowarki EV i CWU na bazie sterowania urządzeniami (device_ctl): czyste funkcje, bez Home Assistanta.

EV: prąd płynnie za nadwyżką PV (6–16 A albo własne granice), ograniczenie przez limit przyłącza, cel sesji (kWh albo % SOC auta).
CWU: temperatura z czujnika — komfort (minimum o wskazanej porze), zadana „na zapas” (pv/tanie/ujemna), twardy limit
bezpieczeństwa, antylegionella raz w tygodniu. Wszystko zwraca decyzję i powód po polsku; sterownik decyduje, co z tym zrobić."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

DOW = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
LEG_MIN_C = 50.0              # poniżej tej temperatury antylegionella nie ma sensu
TEMP_MAX_SANE_C = 95.0        # odczyt powyżej tego uznajemy za błąd czujnika
TEMP_MIN_SANE_C = -20.0
COMFORT_LEAD_H = 3            # komfort włącza się najpóźniej tyle godzin przed wskazaną porą


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def sane_temp(v: Any) -> float | None:
    x = _num(v)
    return x if x is not None and TEMP_MIN_SANE_C <= x <= TEMP_MAX_SANE_C else None


# ----------------------------------------------------------------------------- EV
def amps_for_power(power_w: Any, volts: Any = 230.0, phases: Any = 1, min_a: Any = 6.0, max_a: Any = 16.0) -> int:
    """Prąd [A] (całkowity, zaokrąglony w dół), jaki da się zasilić podaną mocą; 0, gdy mniej niż minimum ładowarki."""
    p, v, ph = _num(power_w), _num(volts) or 230.0, 3 if _num(phases) == 3 else 1
    lo, hi = _num(min_a) or 6.0, _num(max_a) or 16.0
    if p is None or p <= 0 or v <= 0 or hi < lo:
        return 0
    a = int(math.floor(p / (v * ph)))
    if a < lo:
        return 0
    return int(min(a, hi))


def limit_amps(amps: Any, grid_import_w: Any, limit_w: Any, own_w: Any, volts: Any = 230.0, phases: Any = 1, min_a: Any = 6.0) -> int:
    """Zmniejsza prąd, gdy pobór z sieci (z autem) przekroczyłby limit przyłącza; poniżej minimum → 0 (wstrzymaj ładowanie)."""
    a = int(_num(amps) or 0)
    lim, imp = _num(limit_w), _num(grid_import_w)
    if a <= 0 or lim is None or lim <= 0 or imp is None:
        return a
    v, ph = _num(volts) or 230.0, 3 if _num(phases) == 3 else 1
    over = imp + (a * v * ph - (_num(own_w) or 0.0)) - lim              # import po zmianie prądu względem lim
    if over <= 0:
        return a
    a -= int(math.ceil(over / (v * ph)))
    return a if a >= (_num(min_a) or 6.0) else 0


def ev_goal(session_kwh: Any, target_kwh: Any, car_soc: Any, target_pct: Any) -> tuple[bool, str | None]:
    """(cel osiągnięty, powód). Cel: energia sesji (kWh) albo SOC auta (%), gdy jest czujnik; 0 = bez celu."""
    t, s = _num(target_kwh), _num(session_kwh)
    if t is not None and t > 0 and s is not None and s >= t:
        return True, f"cel sesji osiągnięty ({s:.1f} z {t:.1f} kWh)"
    cs, tp = _num(car_soc), _num(target_pct)
    if cs is not None and tp is not None and 0 < tp <= 100 and cs >= tp:
        return True, f"auto naładowane do {cs:.0f}% (cel {tp:.0f}%)"
    return False, None


def ev_hours_needed(target_kwh: Any, session_kwh: Any, car_soc: Any, target_pct: Any, car_kwh: Any, power_w: Any) -> float | None:
    """Ile godzin ładowania brakuje do celu (do wyboru najtańszych godzin); None, gdy nie umiemy tego policzyć."""
    p = _num(power_w)
    if p is None or p <= 0:
        return None
    need = None
    t, s = _num(target_kwh), _num(session_kwh)
    if t is not None and t > 0:
        need = max(0.0, t - (s or 0.0))
    cs, tp, ck = _num(car_soc), _num(target_pct), _num(car_kwh)
    if need is None and cs is not None and tp is not None and ck is not None and ck > 0 and 0 < tp <= 100:
        need = max(0.0, (tp - cs) / 100.0 * ck)
    if need is None:
        return None
    return round(need / (p / 1000.0), 2)


# ----------------------------------------------------------------------------- CWU
def week_key(now: datetime) -> str:
    y, w, _d = now.isocalendar()
    return f"{y}-W{w:02d}"


def legionella_due(now: datetime, dow: Any, done_week: Any) -> bool:
    """Antylegionella jest „na dziś” w wybrany dzień tygodnia (0 = poniedziałek), jeśli w tym tygodniu jeszcze jej nie zrobiono."""
    d = _num(dow)
    return d is not None and int(d) == now.weekday() and done_week != week_key(now)


def dhw_decide(temp: Any, now: datetime, cfg: dict[str, Any], leg_due: bool) -> dict[str, Any]:
    """Bramka temperaturowa CWU. Zwraca {"block": bool, "force": bool, "boost_ok": bool, "reason": str|None, "target": float|None}.

    block — nie wolno grzać (temperatura ≥ limit bezpieczeństwa albo ≥ zadana dla trybów oszczędnych),
    force — trzeba grzać mimo cen (poniżej komfortu w porze komfortu albo antylegionella po terminie),
    boost_ok — tryby pv/tanie/ujemna mogą grzać (jest miejsce do zadanej).
    Bez czujnika (temp None) bramka nic nie blokuje i nie wymusza: zostaje zwykły tryb (np. najtańsze godziny)."""
    t = sane_temp(temp)
    cmax, boost, comfort = _num(cfg.get("dhw_max_c")) or 0.0, _num(cfg.get("dhw_boost_c")) or 0.0, _num(cfg.get("dhw_comfort_c")) or 0.0
    leg_c = _num(cfg.get("dhw_leg_c")) or 0.0
    out: dict[str, Any] = {"block": False, "force": False, "boost_ok": True, "reason": None, "target": boost or None}
    if t is None:
        out["reason"] = "brak odczytu temperatury" if cfg.get("dhw_temp_eid") else None
        if cfg.get("dhw_temp_eid") and cmax > 0:
            out["block"] = True                                   # czujnik skonfigurowany, ale milczy → bezpieczniej nie grzać
        return out
    if cmax > 0 and t >= cmax:
        return {**out, "block": True, "boost_ok": False, "reason": f"temperatura {t:.0f} °C ≥ limit {cmax:.0f} °C"}
    if leg_due and cfg.get("dhw_leg") and leg_c >= LEG_MIN_C:
        if t < leg_c - 0.5:
            return {**out, "boost_ok": True, "target": leg_c, "leg": True, "reason": f"antylegionella: {t:.0f} → {leg_c:.0f} °C"}
        out["leg_done"] = True
    if comfort > 0:
        h = int(_num(cfg.get("dhw_comfort_h")) or 0)
        hour = now.hour + now.minute / 60.0
        due = (h - hour) % 24 <= COMFORT_LEAD_H
        if t < comfort and due:
            return {**out, "force": True, "reason": f"komfort: {t:.0f} °C < {comfort:.0f} °C przed {h:02d}:00"}
    if boost > 0 and t >= boost:
        return {**out, "block": True, "boost_ok": False, "reason": f"osiągnięto temperaturę zadaną {boost:.0f} °C"}
    return out
