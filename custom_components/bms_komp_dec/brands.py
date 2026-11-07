"""Sterowanie falownikami różnych marek: te same komendy BMS, różne kroki na falowniku.

Deye (domyślnie): tryb pracy Zero Export / Export First, prąd ładowania, moc nadwyżki, Time of Use — jak dotąd
(inverter_ctl + runtime._steps).

Sofar G3 (HYD 5–20KTL-3PH, HYD 3–6K-EP; definicje sofar_g3 / sofar_g3hyd): tryb magazynu „Storage Control Mode”
i tryb pasywny (Passive) z trzema mocami: sieci, minimalną i maksymalną baterii (dodatnia = ładowanie):
  • praca normalna → Self Use,
  • ładowanie z sieci → Passive, bateria min = max = +moc ładowania,
  • sprzedaż z baterii → Passive, bateria min = max = −moc sprzedaży,
  • blokada ładowania z PV → Passive, bateria min = −moc rozładowania, max = 0 (bateria może oddawać, nie ładuje).
Sofar hybrydowy (HYD 3–6K ES, ME3000SP; definicja sofar_hybrid): „Work Mode” Auto / Timed i okna ładowania
i rozładowania z mocą, a blokada ładowania z PV — maksymalny prąd ładowania 0 (jak w Deye).

Sterowanie Sofarem NIE było sprawdzone na prawdziwym falowniku. Dlatego dopóki włączony jest
switch.bms_brand_test_mode (domyślnie włączony), komendy dla Sofara trafiają tylko do dziennika jako
„ustawiłbym …” i niczego nie zapisują.
"""
from __future__ import annotations

import time
from typing import Any

from homeassistant.core import HomeAssistant

from . import inverter_ctl as ictl
from .helpers import number_value, state_float, state_str

DEYE = "deye"
SOFAR_G3 = "sofar_g3"
SOFAR_HYBRID = "sofar_hybrid"
LABELS = {DEYE: "Deye (i zgodne)", SOFAR_G3: "Sofar G3 (tryb pasywny)", SOFAR_HYBRID: "Sofar hybrydowy (Work Mode)"}

# rola → (domena, końcówki nazwy encji)
ROLES: dict[str, dict[str, tuple[str, tuple[str, ...]]]] = {
    SOFAR_G3: {
        "mode": ("select", ("storage_control_mode",)),
        "grid": ("number", ("passive_grid_power",)),
        "bat_min": ("number", ("passive_minimum_battery_power", "passive_min_battery_power")),
        "bat_max": ("number", ("passive_maximum_battery_power", "passive_max_battery_power")),
    },
    SOFAR_HYBRID: {
        "mode": ("select", ("work_mode",)),
        "tc_start": ("time", ("timed_charge_start",)),
        "tc_end": ("time", ("timed_charge_end",)),
        "tc_power": ("number", ("timed_charge_power",)),
        "td_start": ("time", ("timed_discharge_start",)),
        "td_end": ("time", ("timed_discharge_end",)),
        "td_power": ("number", ("timed_discharge_power",)),
        "charge_current": ("number", ("battery_max_charge_current",)),
    },
}
OPTIONS = {
    "self_use": ("Self Use", "Self-Use", "Self use"),
    "passive": ("Passive", "Passive Mode"),
    "auto": ("Auto", "Self Use", "Self-Use"),
    "timed": ("Timed", "Timing", "Timed Mode"),
}
_CACHE: dict[int, tuple[float, str]] = {}
_CACHE_S = 60.0


def _opts(hass: HomeAssistant, eid: str | None) -> list[str]:
    return [o.lower() for o in (ictl.options_of(hass, eid) or [])] if eid else []


def detect(hass: HomeAssistant, cfg: dict[str, Any]) -> str:
    """Marka po opcjach encji trybu pracy (z konfiguracji albo wykrytej)."""
    key = id(hass)
    hit = _CACHE.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _CACHE_S:
        return hit[1]
    brand = DEYE
    cands = [ictl.resolve(hass, cfg, "work_mode")]
    try:
        cands += [e for e in hass.states.async_entity_ids("select")
                  if e.endswith("_storage_control_mode") or e.endswith("_work_mode")]
    except Exception:  # noqa: BLE001
        pass
    for eid in dict.fromkeys(cands):
        o = set(_opts(hass, eid))
        if not o:
            continue
        if "passive" in o and ("self use" in o or "self-use" in o):
            brand = SOFAR_G3
            break
        if "auto" in o and ("timed" in o or "passive" in o):
            brand = SOFAR_HYBRID
            break
        if any(x in o for x in ("zero export to load", "export first", "selling first", "zero export to ct")):
            brand = DEYE
            break
    _CACHE[key] = (now, brand)
    return brand


def reset_cache() -> None:
    _CACHE.clear()


def role_eid(hass: HomeAssistant, cfg: dict[str, Any], brand: str, role: str) -> str | None:
    """Encja roli marki: najpierw z tym samym prefiksem co encja trybu pracy, potem dowolna z pasującą końcówką."""
    dom, tails = ROLES[brand][role]
    wm = ictl.resolve(hass, cfg, "work_mode")
    obj = wm.partition(".")[2]
    prefix = None
    for t in ("storage_control_mode", "work_mode"):
        if obj.endswith(t):
            prefix = obj[: -len(t)].rstrip("_")
            break
    if role == "mode" and wm.startswith("select.") and any(obj.endswith(t) for t in tails) and hass.states.get(wm) is not None:
        return wm
    for t in tails:
        guess = f"{dom}.{prefix}_{t}" if prefix else f"{dom}.{t}"
        if hass.states.get(guess) is not None:
            return guess
    try:
        for eid in hass.states.async_entity_ids(dom):
            obj = eid.partition(".")[2]
            if any(obj == t or obj.endswith("_" + t) for t in tails):
                return eid
    except Exception:  # noqa: BLE001
        pass
    return None


def control_entities(hass: HomeAssistant, cfg: dict[str, Any]) -> dict[str, str | None]:
    """Encje, którymi BMS steruje falownikiem (do sprawdzenia i podglądu)."""
    brand = detect(hass, cfg)
    if brand == DEYE:
        return {r: ictl.resolve(hass, cfg, r) for r in ("work_mode", "charge_current", "export_surplus", "tou_select")}
    return {r: role_eid(hass, cfg, brand, r) for r in ROLES[brand]}


def pick(hass: HomeAssistant, eid: str, kind: str) -> str | None:
    opts = ictl.options_of(hass, eid)
    if opts is None:
        return None
    low = {o.strip().lower(): o for o in opts}
    for c in OPTIONS[kind]:
        if c.lower() in low:
            return low[c.lower()]
    return None


def _num(v: float) -> float:
    return int(v) if float(v).is_integer() else round(float(v), 1)


class StepError(Exception):
    """Brak encji albo opcji — komenda nie może być zbudowana."""


def steps(hass: HomeAssistant, cfg: dict[str, Any], brand: str, key: str, *, sell_w: float, charge_w: float,
          discharge_w: float, normal_current: float | None) -> list[tuple[str, str, Any]]:
    """Kroki komendy BMS dla Sofara (domena, encja, wartość)."""
    r = {role: role_eid(hass, cfg, brand, role) for role in ROLES[brand]}

    def need(*roles: str) -> None:
        miss = [ROLES[brand][x][1][0] for x in roles if not r.get(x)]
        if miss:
            raise StepError("nie znaleziono encji falownika: " + ", ".join(miss))

    def opt(kind: str) -> str:
        val = pick(hass, r["mode"], kind)
        if val is None:
            raise StepError(f"encja {r['mode']} nie ma opcji {' / '.join(OPTIONS[kind])}; dostępne: "
                            f"{', '.join(ictl.options_of(hass, r['mode']) or [])}")
        return val

    def clamp(role: str, v: float) -> float:
        return _num(ictl.clamp_to_entity(hass, r[role], v))

    if brand == SOFAR_G3:
        need("mode", "grid", "bat_min", "bat_max")
        normal = lambda: [("select", r["mode"], opt("self_use"))]  # noqa: E731

        def passive(bmin: float, bmax: float) -> list[tuple[str, str, Any]]:
            # moce najpierw, tryb na końcu — falownik nie wchodzi w Passive ze starymi wartościami
            return [("number", r["grid"], 0), ("number", r["bat_min"], clamp("bat_min", bmin)),
                    ("number", r["bat_max"], clamp("bat_max", bmax)), ("select", r["mode"], opt("passive"))]

        table = {
            "sprzedaz_6000w": lambda: passive(-sell_w, -sell_w),
            "nadwyzka_9700w": normal,
            "eksport_pv_blokada": lambda: passive(-discharge_w, 0),
            "przywroc_ladowanie": normal,
            "zablokuj_ladowanie": lambda: passive(-discharge_w, 0),
            "odblokuj_ladowanie": normal,
            "wlacz_ladowanie_siec": lambda: passive(charge_w, charge_w),
            "wylacz_ladowanie_siec": normal,
        }
    else:
        need("mode")
        auto = lambda: [("select", r["mode"], opt("auto"))]  # noqa: E731

        def timed(charge: bool) -> list[tuple[str, str, Any]]:
            need("tc_start", "tc_end", "td_start", "td_end", "tc_power" if charge else "td_power")
            on, off = ("tc", "td") if charge else ("td", "tc")
            pw = charge_w if charge else sell_w
            return [("time", r[f"{off}_start"], "00:00:00"), ("time", r[f"{off}_end"], "00:00:00"),
                    ("time", r[f"{on}_start"], "00:00:00"), ("time", r[f"{on}_end"], "23:59:00"),
                    ("number", r[f"{on}_power"], clamp(f"{on}_power", pw)), ("select", r["mode"], opt("timed"))]

        def cc(v: float | None) -> list[tuple[str, str, Any]]:
            need("charge_current")
            return [("number", r["charge_current"], clamp("charge_current", v if v and v > 0 else 0))]

        table = {
            "sprzedaz_6000w": lambda: timed(False),
            "nadwyzka_9700w": auto,
            "eksport_pv_blokada": lambda: cc(0),
            "przywroc_ladowanie": lambda: cc(normal_current) + auto(),
            "zablokuj_ladowanie": lambda: cc(0),
            "odblokuj_ladowanie": lambda: cc(normal_current),
            "wlacz_ladowanie_siec": lambda: timed(True),
            "wylacz_ladowanie_siec": auto,
        }
    build = table.get(key)
    return build() if build else []


# ------------------------------------------------------------------ stan (co falownik teraz robi)
def _f(hass: HomeAssistant, eid: str | None) -> float | None:
    return state_float(hass, eid) if eid else None


def _mode_is(hass: HomeAssistant, eid: str | None, kind: str) -> bool:
    s = (state_str(hass, eid) or "").strip().lower() if eid else ""
    return bool(s) and s in {c.lower() for c in OPTIONS[kind]}


def state(hass: HomeAssistant, cfg: dict[str, Any], brand: str) -> dict[str, Any]:
    """{'selling', 'grid_charging', 'pv_blocked', 'charge_current', 'mode'} dla Sofara."""
    r = {role: role_eid(hass, cfg, brand, role) for role in ROLES[brand]}
    mode = state_str(hass, r.get("mode")) if r.get("mode") else None
    out = {"selling": False, "grid_charging": False, "pv_blocked": False, "charge_current": None, "mode": mode}
    if brand == SOFAR_G3:
        if _mode_is(hass, r.get("mode"), "passive"):
            bmin, bmax = _f(hass, r.get("bat_min")), _f(hass, r.get("bat_max"))
            out["selling"] = bmax is not None and bmax < -1
            out["grid_charging"] = bmin is not None and bmin > 1
            out["pv_blocked"] = bmax is not None and abs(bmax) <= 1
    else:
        if _mode_is(hass, r.get("mode"), "timed"):
            def win(p: str) -> bool:
                a, b = state_str(hass, r.get(f"{p}_start")), state_str(hass, r.get(f"{p}_end"))
                return bool(a and b and a[:5] != b[:5])
            out["selling"] = win("td") and (_f(hass, r.get("td_power")) or 0) > 0
            out["grid_charging"] = win("tc") and (_f(hass, r.get("tc_power")) or 0) > 0
        cc = _f(hass, r.get("charge_current"))
        out["charge_current"] = cc
        out["pv_blocked"] = cc is not None and cc <= 0.1
    return out


def powers(hass: HomeAssistant, cfg: dict[str, Any]) -> tuple[float, float, float]:
    """(moc sprzedaży, moc ładowania z sieci, moc rozładowania) w W — z ustawień BMS."""
    sell = number_value(hass, "sell_export_power_w", 6000.0) or 6000.0
    try:
        chg = float(cfg.get("max_charge_power_w") or 5000.0)
    except (TypeError, ValueError):
        chg = 5000.0
    try:
        dis = float(cfg.get("max_discharge_power_w") or 5000.0)
    except (TypeError, ValueError):
        dis = 5000.0
    return float(sell), chg, dis
