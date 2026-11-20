"""Profile pracy: gotowe zestawy ustawień włączane jednym kliknięciem (zima, lato, urlop, burza).

Profil to tylko lista „ustawienie → wartość” dla przełączników i liczb samej integracji (te same encje, które użytkownik może
zmienić ręcznie) — nic ukrytego. Przed zastosowaniem karta pokazuje, co się zmieni (teraz → po profilu), a po zastosowaniu EMS
zapamiętuje poprzednie wartości, żeby jednym kliknięciem wrócić do stanu sprzed profilu. Wartości, które użytkownik zdążył zmienić
ręcznie po profilu, nie są przy powrocie nadpisywane.

Ten moduł jest czysty (bez Home Assistanta): runtime podaje funkcje odczytu, a zapis robi przez usługi switch / number."""
from __future__ import annotations

import math
from typing import Any, Callable

from .const import NUMBERS, SWITCHES

SW_LABEL = {k: n for k, n, _i, _d in SWITCHES}
NUM_META = {k: (n, lo, hi, step, unit) for k, n, lo, hi, step, unit in NUMBERS}
EPS = 1e-6

PROFILES: tuple[dict[str, Any], ...] = (
    {"id": "winter", "name": "Zima", "icon": "❄️",
     "desc": "Krótkie dni i mało słońca: większa rezerwa baterii, ostrożniejsza prognoza PV i ładowanie z sieci w tanich godzinach.",
     "set": {"pv_plan_pessimism_pct": 40, "reserve_floor_soc": 30, "dawn_margin_soc": 15, "dynamic_reserve": True,
             "grid_charge_enabled": True, "pv_forecast_correction": True}},
    {"id": "summer", "name": "Lato", "icon": "☀️",
     "desc": "Dużo słońca: prognoza PV bez dodatkowej ostrożności, mniejsza rezerwa, sprzedaż z baterii od niższego poziomu.",
     "set": {"pv_plan_pessimism_pct": 0, "reserve_floor_soc": 15, "dawn_margin_soc": 10, "sell_enabled": True, "min_soc_for_sell": 40}},
    {"id": "vacation", "name": "Urlop", "icon": "🏖",
     "desc": "Nikogo nie ma w domu: plan zakłada stałe, minimalne zużycie, bateria może sprzedawać, powiadomienia o usterkach zostają włączone.",
     "set": {"vacation_mode": True, "sell_enabled": True, "notifications_enabled": True}},
    {"id": "storm", "name": "Burza", "icon": "⛈",
     "desc": "Ryzyko awarii sieci: bateria zostaje naładowana na zapas i nic nie sprzedaje. Tryb wyłącza się sam po ustawionym czasie.",
     "set": {"storm_mode": True}},
)
BY_ID = {p["id"]: p for p in PROFILES}


def get(pid: Any) -> dict[str, Any] | None:
    return BY_ID.get(pid) if isinstance(pid, str) else None


def kind(key: str) -> str | None:
    if key in SW_LABEL:
        return "switch"
    if key in NUM_META:
        return "number"
    return None


def label(key: str) -> str:
    return SW_LABEL.get(key) or (NUM_META.get(key) or (key,))[0]


def unit(key: str) -> str:
    return (NUM_META.get(key) or (None, None, None, None, ""))[4]


def check_value(key: str, value: Any) -> Any | None:
    """Wartość zgodna z typem i zakresem encji (bool dla przełącznika, liczba z [min, max] dla liczby) albo None."""
    k = kind(key)
    if k == "switch":
        return value if isinstance(value, bool) else None
    if k == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        _n, lo, hi, _s, _u = NUM_META[key]
        return float(value) if lo <= value <= hi else None
    return None


def same(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or (isinstance(a, bool) and isinstance(b, bool) and a == b)
    try:
        return abs(float(a) - float(b)) <= EPS
    except (TypeError, ValueError):
        return False


def settings_word(n: int) -> str:
    """„1 ustawienie”, „2 ustawienia”, „5 ustawień” — poprawna odmiana po liczebniku."""
    n = abs(int(n))
    if n == 1:
        return "1 ustawienie"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} ustawienia"
    return f"{n} ustawień"


def fmt(key: str, value: Any) -> str:
    if value is None:
        return "—"
    if kind(key) == "switch":
        return "włączone" if value else "wyłączone"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "—"
    txt = f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    u = unit(key)
    return f"{txt} {u}".strip()


def changes(profile: dict[str, Any], read: Callable[[str], Any]) -> list[dict[str, Any]]:
    """Co zmieni profil: dla każdego ustawienia wartość teraz (None = encja niedostępna) i po profilu."""
    out = []
    for key, target in profile["set"].items():
        now = read(key)
        out.append({"key": key, "label": label(key), "kind": kind(key), "available": now is not None,
                    "now": now, "target": target, "now_text": fmt(key, now), "target_text": fmt(key, target),
                    "differs": now is not None and not same(now, target)})
    return out


def drifted(applied: dict[str, Any], read: Callable[[str], Any]) -> list[str]:
    """Ustawienia z profilu, których wartość jest dziś inna niż zastosowana (zmiana ręczna, wygaśnięcie trybu burzowego…)."""
    out = []
    for key, val in applied.items():
        now = read(key)
        if now is None or not same(now, val):
            out.append(key)
    return out


def clean_state(st: Any) -> dict[str, Any] | None:
    """Zapis `state["profile"]` po wczytaniu z pliku: poprawny profil, wartości zgodne z zakresami; w przeciwnym razie None."""
    if not isinstance(st, dict) or get(st.get("id")) is None or not isinstance(st.get("since"), str):
        return None
    out: dict[str, Any] = {"id": st["id"], "since": st["since"], "prev": {}, "applied": {}, "ended": None}
    for fld in ("prev", "applied"):
        src = st.get(fld)
        if not isinstance(src, dict):
            return None
        for k, v in src.items():
            cv = check_value(k, v) if isinstance(k, str) else None
            if cv is not None:
                out[fld][k] = cv
    end = st.get("ended")
    if isinstance(end, dict) and isinstance(end.get("at"), str):
        out["ended"] = {"at": end["at"], "keys": [k for k in (end.get("keys") or []) if isinstance(k, str)][:20]}
    return out if out["applied"] else None
