"""Autokorekta ostrożności prognozy PV w planie (ustawienie „pv_plan_pessimism_pct”).

Ostrożność mówi, jak daleko od mediany prognozy PV planer ma się cofnąć w stronę wersji pesymistycznej. Zbyt mała ostrożność
daje plany, w których słońca było mniej, niż zakładano (bateria pusta wcześniej, droższy prąd z sieci); zbyt duża — plany,
które zawsze dokupują energię z sieci, choć słońca wystarczyło. Ten moduł patrzy na błąd prognozy z kilku ostatnich dni
(po korekcie z historii, ale PRZED ostrożnością — tak zapisuje ją insights) i, gdy błąd jest stale jednostronny, PROPONUJE zmianę
ostrożności. Nic nie zmienia sam: użytkownik zatwierdza jednym kliknięciem i jednym kliknięciem może wrócić.

Ponieważ zapisana prognoza nie zawiera ostrożności, docelową ostrożność da się policzyć wprost z błędu (bez eskalacji w kółko):
planer mnoży prognozę przez (1 − ostrożność × (1 − lo)), gdzie lo = stosunek wersji pesymistycznej do mediany. Gdy prognoza jest
średnio zawyżona o b%, potrzebny mnożnik to 1/(1 + b), czyli ostrożność = (1 − 1/(1 + b)) / (1 − lo). Czysty moduł, bez HA."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

KEY = "pv_plan_pessimism_pct"
MAX_STEP = 20.0              # jednorazowo proponujemy zmianę o najwyżej tyle pkt %
MIN_STEP = 10.0              # mniejszych zmian nie proponujemy (szum)
MAX_PCT = 70.0               # powyżej planer prawie nie sprzedaje i ładuje z sieci „na zapas” — wyżej nie proponujemy
MIN_DAYS = 5                 # tyle dób z parą (prognoza, wykonanie) potrzeba
RAISE_BIAS = 12.0            # średnie zawyżenie prognozy (% wykonania), od którego proponujemy podwyżkę…
RAISE_SHARE = 0.6            # …i tyle dób z zawyżeniem ≥ DAY_OVER
LOWER_BIAS = -20.0           # średnie zaniżenie (ujemny błąd), od którego proponujemy obniżkę…
LOWER_SHARE = 0.6            # …i tyle dób z zaniżeniem ≥ DAY_UNDER
DAY_OVER = 10.0              # dobę liczymy jako „zawyżoną”, gdy prognoza > wykonanie o tyle %
DAY_UNDER = 15.0             # dobę liczymy jako „zaniżoną”, gdy prognoza < wykonanie o tyle %
DISMISS_DAYS = 7             # „Nie teraz” ucisza propozycję na tyle dób
SETTLE_DAYS = 3              # po zmianie ostrożności kolejnej propozycji nie pokazujemy przez tyle dób (daj planowi popracować)
LO_DEFAULT = 0.7             # gdy brak prognozy pesymistycznej — typowy stosunek p10 do mediany
LO_MAX = 0.9                 # powyżej tego ostrożność prawie nic nie zmienia, więc nie ma czego proponować


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _day(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _r5(x: float) -> float:
    return round(x / 5.0) * 5.0


def clean_state(st: Any) -> dict[str, Any]:
    """Zapis w stanie runtime po wczytaniu z pliku: ostatnia zmiana (data, z, do) i data uciszenia propozycji."""
    out: dict[str, Any] = {"last": None, "dismissed": None}
    if not isinstance(st, dict):
        return out
    last = st.get("last")
    if isinstance(last, dict) and _day(last.get("date")):
        fr, to = _num(last.get("from")), _num(last.get("to"))
        if fr is not None and to is not None and 0.0 <= fr <= 100.0 and 0.0 <= to <= 100.0:
            out["last"] = {"date": str(last["date"])[:10], "from": fr, "to": to, "reverted": bool(last.get("reverted"))}
    if _day(st.get("dismissed")):
        out["dismissed"] = str(st["dismissed"])[:10]
    return out


def evaluate(pairs: Any, current: Any, today: date, state: Any = None, lo: Any = None) -> dict[str, Any] | None:
    """Propozycja zmiany ostrożności albo None.

    pairs: (data dnia ISO, prognoza [kWh], wykonanie [kWh]) — z dni bez ucięcia produkcji przez falownik;
    current: bieżąca ostrożność (% 0–100) albo None, gdy encja jest niedostępna; lo: stosunek wersji pesymistycznej do mediany."""
    cur = _num(current)
    if cur is None or not 0.0 <= cur <= 100.0:
        return None
    st = clean_state(state)
    if st["dismissed"] and today <= _day(st["dismissed"]) + timedelta(days=DISMISS_DAYS):
        return None
    if st["last"] and today < _day(st["last"]["date"]) + timedelta(days=SETTLE_DAYS):
        return None
    lo_v = _num(lo)
    lo_v = LO_DEFAULT if lo_v is None or not 0.0 < lo_v < 1.0 else min(0.95, max(0.3, lo_v))
    if not isinstance(pairs, (list, tuple)):
        return None
    rows = []
    for item in pairs:
        try:
            d, f, a = item
        except (TypeError, ValueError):
            continue
        dd, fv, av = _day(d), _num(f), _num(a)
        if dd is None or fv is None or av is None or av < 0.5 or fv < 0 or dd >= today or dd < today - timedelta(days=30):
            continue
        rows.append(((fv - av) / av * 100.0, fv, av))
    if len(rows) < MIN_DAYS:
        return None
    n = len(rows)
    bias = (sum(r[1] for r in rows) - sum(r[2] for r in rows)) / sum(r[2] for r in rows) * 100.0
    over = sum(1 for r in rows if r[0] >= DAY_OVER)
    under = sum(1 for r in rows if r[0] <= -DAY_UNDER)
    base = {"days": n, "bias": round(bias, 1), "from": cur, "lo": round(lo_v, 2)}
    if bias >= RAISE_BIAS and over >= math.ceil(RAISE_SHARE * n) and cur < MAX_PCT and lo_v <= LO_MAX:
        need = (1.0 - 1.0 / (1.0 + bias / 100.0)) / (1.0 - lo_v) * 100.0
        to = min(MAX_PCT, cur + MAX_STEP, _r5(need))
        if to - cur >= MIN_STEP:
            return {**base, "dir": "raise", "to": to, "bad_days": over, "need": round(need, 1),
                    "text": (f"W {over} z ostatnich {n} dób prognoza PV była zawyżona (średnio o {abs(bias):.0f}%), a plan liczył na to słońce. "
                             f"Proponuję zwiększyć ostrożność z {cur:.0f}% do {to:.0f}% — plan będzie mniej liczył na PV i bezpieczniej ładował baterię.")}
    if bias <= LOWER_BIAS and under >= math.ceil(LOWER_SHARE * n) and cur > 0.0:
        to = max(0.0, cur - MAX_STEP)
        if cur - to >= MIN_STEP or (cur - to > 0 and cur < MIN_STEP):
            return {**base, "dir": "lower", "to": to, "bad_days": under, "need": 0.0,
                    "text": (f"W {under} z ostatnich {n} dób słońca było wyraźnie więcej, niż zakładała prognoza (średnio o {abs(bias):.0f}% za niska). "
                             f"Proponuję zmniejszyć ostrożność z {cur:.0f}% do {to:.0f}% — plan będzie mniej dokupował energii z sieci.")}
    return None


def can_revert(state: Any, current: Any) -> dict[str, Any] | None:
    """Ostatnia zmiana, którą da się cofnąć: tylko jeśli wartość nadal jest taka, jaką ustawiliśmy (ręczna zmiana wygrywa)."""
    st = clean_state(state)
    last, cur = st["last"], _num(current)
    if not last or last.get("reverted") or cur is None or abs(cur - last["to"]) > 1e-6:
        return None
    return last
