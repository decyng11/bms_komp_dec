"""Profile pracy: gotowe zestawy ustawień włączane jednym kliknięciem (zima, lato, urlop, burza).

Profil to tylko lista „ustawienie → wartość” dla przełączników i liczb samej integracji (te same encje, które użytkownik może
zmienić ręcznie) — nic ukrytego. Przed zastosowaniem karta pokazuje, co się zmieni (teraz → po profilu), a po zastosowaniu EMS
zapamiętuje poprzednie wartości, żeby jednym kliknięciem wrócić do stanu sprzed profilu. Wartości, które użytkownik zdążył zmienić
ręcznie po profilu, nie są przy powrocie nadpisywane.

Oprócz czterech gotowych profili użytkownik może zapisać własny (bieżące ustawienia pod nazwą, tylko z listy CUSTOM_KEYS — bez godzin,
prądów, mocy i zabezpieczeń) oraz zaplanować profil na zakres dat (np. urlop od–do: włącza się sam, a po ostatnim dniu wraca do
poprzednich ustawień).

Ten moduł jest czysty (bez Home Assistanta): runtime podaje funkcje odczytu, a zapis robi przez usługi switch / number."""
from __future__ import annotations

import math
import re
from datetime import date
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
)
BY_ID = {p["id"]: p for p in PROFILES}

# ---------------------------------------------------------------- własne profile
# Własny profil zapamiętuje wartości WYŁĄCZNIE tych ustawień. Poza listą zostają: godziny i zestawy harmonogramu, dni tygodnia,
# prądy i moce (sprzęt), znak baterii, ręczne wymuszanie ładowania, autostosowanie oraz zabezpieczenia (blokada sprzedaży po imporcie,
# blokada arbitrażu, dzienny limit importu) — profil nie może ich po cichu zmienić.
CUSTOM_SWITCHES = ("sell_enabled", "grid_charge_enabled", "dynamic_reserve", "auto_enable_sets", "grid_stop_at_target", "negative_price_reaction",
                   "profit_check", "vacation_mode", "pv_forecast_correction", "pv_fallback_forecast", "live_load_correction",
                   "sale_power_fit", "device_control", "notifications_enabled")
CUSTOM_NUMBERS = ("min_soc_for_sell", "min_soc_for_pv_export", "min_soc_for_pv_export_stop", "pv_plan_pessimism_pct", "low_price_threshold",
                  "min_sell_margin", "reserve_floor_soc", "dawn_margin_soc", "auto_apply_max_shift_h", "vacation_load_w",
                  "device_shed_soc", "load_forecast_override")
CUSTOM_KEYS = CUSTOM_SWITCHES + CUSTOM_NUMBERS
MAX_CUSTOM = 8                     # tyle własnych profili
NAME_MAX = 24
CUSTOM_ICONS = ("⭐", "🏠", "🔋", "☀️", "🌙", "🏖", "❄️", "🌧", "💰", "🛡")
DEFAULT_ICON = "⭐"
_CUSTOM_ID = re.compile(r"^u_\d{1,6}$")
_BAD_CHARS = re.compile(r"[\x00-\x1f\x7f<>&\"'`{}\\]")


def get(pid: Any) -> dict[str, Any] | None:
    """Gotowy (wbudowany) profil; własne profile trzyma runtime — patrz find()."""
    return BY_ID.get(pid) if isinstance(pid, str) else None


def is_custom_id(pid: Any) -> bool:
    return isinstance(pid, str) and bool(_CUSTOM_ID.match(pid))


def valid_id(pid: Any) -> bool:
    """Id, który może pojawić się w zapisanym stanie: gotowy profil albo własny (czy jeszcze istnieje — rozstrzyga runtime)."""
    return get(pid) is not None or is_custom_id(pid)


def find(pid: Any, custom: Any) -> dict[str, Any] | None:
    """Profil o danym id: gotowy albo z listy własnych (już oczyszczonej przez clean_custom)."""
    p = get(pid)
    if p is not None:
        return p
    if is_custom_id(pid) and isinstance(custom, list):
        return next((c for c in custom if isinstance(c, dict) and c.get("id") == pid), None)
    return None


def clean_name(v: Any) -> str | None:
    """Nazwa własnego profilu: bez znaków sterujących i HTML-owych, spacje zwinięte, 1–NAME_MAX znaków; inaczej None."""
    if not isinstance(v, str):
        return None
    t = " ".join(_BAD_CHARS.sub(" ", v).split())[:NAME_MAX].strip()
    return t or None


def clean_custom(items: Any) -> list[dict[str, Any]]:
    """Lista własnych profili po wczytaniu z pliku: poprawne id (bez duplikatów), nazwa, ikona z listy, wartości z CUSTOM_KEYS w zakresach."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not is_custom_id(it.get("id")) or it["id"] in seen:
            continue
        name = clean_name(it.get("name"))
        raw = it.get("set")
        if name is None or not isinstance(raw, dict):
            continue
        vals = {k: check_value(k, v) for k, v in raw.items() if isinstance(k, str) and k in CUSTOM_KEYS}
        vals = {k: v for k, v in vals.items() if v is not None}
        if not vals:
            continue
        icon = it.get("icon") if it.get("icon") in CUSTOM_ICONS else DEFAULT_ICON
        since = it.get("saved") if isinstance(it.get("saved"), str) and len(it["saved"]) <= 40 else ""
        seen.add(it["id"])
        out.append({"id": it["id"], "name": name, "icon": icon, "custom": True, "saved": since, "set": vals,
                    "desc": f"Własny zestaw ustawień zapisany {since[:10]}: {settings_word(len(vals))}." if since else f"Własny zestaw: {settings_word(len(vals))}."})
        if len(out) >= MAX_CUSTOM:
            break
    return out


def make_custom(name: Any, icon: Any, read: Callable[[str], Any], existing: Any, saved: str) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    """Zapisuje bieżące wartości ustawień z CUSTOM_KEYS pod nazwą. Zwraca (nowa lista, profil, czy_zastąpiono_istniejący).

    Profil o tej samej nazwie (bez względu na wielkość liter) jest nadpisywany. ValueError z polskim opisem, gdy nazwa jest zła,
    nie ma co zapisać albo limit profili jest wyczerpany."""
    nm = clean_name(name)
    if nm is None:
        raise ValueError("Podaj nazwę profilu (do 24 znaków, bez znaków specjalnych)")
    vals: dict[str, Any] = {}
    for k in CUSTOM_KEYS:
        v = check_value(k, read(k))
        if v is not None:
            vals[k] = v
    if not vals:
        raise ValueError("Brak ustawień do zapisania (encje EMS są niedostępne)")
    cur = clean_custom(existing)
    same_name = next((c for c in cur if c["name"].casefold() == nm.casefold()), None)
    if same_name is None and len(cur) >= MAX_CUSTOM:
        raise ValueError(f"Limit {MAX_CUSTOM} własnych profili — usuń któryś, żeby zapisać nowy")
    used = {int(c["id"][2:]) for c in cur}
    pid = same_name["id"] if same_name else f"u_{next(i for i in range(1, 10**6) if i not in used)}"
    rec = {"id": pid, "name": nm, "icon": icon if icon in CUSTOM_ICONS else DEFAULT_ICON, "saved": saved, "set": vals}
    new = [c for c in cur if c["id"] != pid] + [rec]
    new = clean_custom(new)
    return new, next(c for c in new if c["id"] == pid), same_name is not None


# ---------------------------------------------------------------- profil z datami (np. urlop od–do)
PLAN_MAX_DAYS = 180


def _day(v: Any) -> date | None:
    try:
        return date.fromisoformat(v) if isinstance(v, str) and len(v) == 10 else None
    except ValueError:
        return None


def check_plan(pid: Any, d_from: Any, d_to: Any, today: date, custom: Any) -> dict[str, Any]:
    """Waliduje plan: znany profil, daty ISO, od ≥ dziś, do ≥ od, najwyżej PLAN_MAX_DAYS dni. ValueError z polskim opisem."""
    if find(pid, custom) is None:
        raise ValueError("Nieznany profil")
    a, b = _day(d_from), _day(d_to)
    if a is None or b is None:
        raise ValueError("Podaj daty „od” i „do”")
    if a < today:
        raise ValueError("Data „od” nie może być z przeszłości")
    if b < a:
        raise ValueError("Data „do” nie może być wcześniejsza niż „od”")
    if (b - a).days + 1 > PLAN_MAX_DAYS:
        raise ValueError(f"Zakres może trwać najwyżej {PLAN_MAX_DAYS} dni")
    return {"id": pid, "from": a.isoformat(), "to": b.isoformat(), "status": "waiting", "resume": None}


def clean_plan(st: Any) -> dict[str, Any] | None:
    """Zapis planu po wczytaniu z pliku: poprawne id i daty, status waiting/active; inaczej None."""
    if not isinstance(st, dict) or not valid_id(st.get("id")):
        return None
    a, b = _day(st.get("from")), _day(st.get("to"))
    if a is None or b is None or b < a or st.get("status") not in ("waiting", "active"):
        return None
    res = st.get("resume")
    return {"id": st["id"], "from": a.isoformat(), "to": b.isoformat(), "status": st["status"], "resume": res if valid_id(res) else None}


def plan_phase(plan: dict[str, Any], today: date) -> str:
    """„before” (przed startem), „during” (od startu do ostatniego dnia włącznie), „after” (po ostatnim dniu)."""
    a, b = _day(plan["from"]), _day(plan["to"])
    if today < a:
        return "before"
    return "during" if today <= b else "after"


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
    if not isinstance(st, dict) or not valid_id(st.get("id")) or not isinstance(st.get("since"), str):
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
