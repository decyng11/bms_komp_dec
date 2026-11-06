"""Sterowanie falownikiem bez „zaszytych” nazw encji i wartości.

Wcześniej przyciski i automaty zakładały encje `select.inverter_work_mode`, `number.inverter_…` oraz
opcje „Export First” / „Zero Export To Load” i prąd 170 A. U innego użytkownika (inny prefiks encji,
inny model, inna moc falownika) kończyło się to błędem albo — gorzej — ustawieniem wartości,
której falownik nie przyjmuje. Tutaj:
  • encje są brane z konfiguracji, a gdy jej nie ma / nie istnieją — wykrywane po prefiksie sąsiednich encji,
  • nazwy opcji select są dobierane z listy `options` encji (bez rozróżniania wielkości liter),
  • wartości number są przycinane do `min`/`max` encji,
  • prąd ładowania „normalny” to zapamiętana wartość sprzed blokady (albo ustawienie użytkownika).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CHARGE_CURRENT_EID, CONF_CHARGE_CURRENT, CONF_EXPORT_SURPLUS, CONF_TOU, CONF_WORK_MODE,
    EXPORT_SURPLUS_EID, NORMAL_CHARGE_CURRENT, TOU_EID, WORK_MODE_EID,
)
from .helpers import number_value, state_float

_LOGGER = logging.getLogger(__name__)

ROLE_CONF = {
    "work_mode": CONF_WORK_MODE,
    "charge_current": CONF_CHARGE_CURRENT,
    "export_surplus": CONF_EXPORT_SURPLUS,
    "tou_select": CONF_TOU,
}
ROLE_DOMAIN = {"work_mode": "select", "charge_current": "number", "export_surplus": "number", "tou_select": "select"}
ROLE_LEGACY = {
    "work_mode": WORK_MODE_EID,
    "charge_current": CHARGE_CURRENT_EID,
    "export_surplus": EXPORT_SURPLUS_EID,
    "tou_select": TOU_EID,
}
# końcówki nazw encji (ha-solarman i pokrewne) — służą do zgadywania po prefiksie sąsiada
ROLE_TAILS = {
    "work_mode": ("work_mode",),
    "charge_current": ("battery_max_charging_current", "max_charging_current"),
    "export_surplus": ("export_surplus_power", "export_surplus"),
    "tou_select": ("time_of_use",),
}

# kandydaci na nazwy opcji (pierwsza pasująca do listy `options` encji wygrywa)
OPTION_CANDIDATES = {
    "export": ("Export First", "Selling First", "Sell First", "Export"),
    "zero": ("Zero Export To Load", "Zero Export To CT", "Zero Export"),
    "tou_off": ("Disabled", "Disable", "Off"),
    "tou_on": ("Week", "Enabled", "Enable", "On"),
}


def _exists(hass: HomeAssistant, eid: str | None) -> bool:
    return bool(eid) and hass.states.get(eid) is not None


def _split(eid: str) -> tuple[str, str]:
    dom, _, obj = eid.partition(".")
    return dom, obj


def resolve(hass: HomeAssistant, cfg: dict[str, Any], role: str) -> str:
    """entity_id dla roli (work_mode / charge_current / export_surplus / tou_select).

    Kolejność: konfiguracja → domyślna nazwa → ta sama nazwa z prefiksem sąsiedniej encji falownika →
    dowolna encja z pasującą końcówką. Gdy nic nie istnieje, zwraca nazwę z konfiguracji/domyślną
    (wywołujący zgłosi czytelny błąd)."""
    cand = (cfg.get(ROLE_CONF[role]) or ROLE_LEGACY[role])
    if _exists(hass, cand):
        return cand
    dom = ROLE_DOMAIN[role]
    # prefiks wyciągamy z innych ról, które istnieją (np. select.deye_work_mode → „deye”)
    for other, conf_key in ROLE_CONF.items():
        if other == role:
            continue
        oc = cfg.get(conf_key) or ROLE_LEGACY[other]
        if not _exists(hass, oc):
            continue
        _d, obj = _split(oc)
        for tail in ROLE_TAILS[other]:
            if obj.endswith(tail):
                prefix = obj[: -len(tail)].rstrip("_")
                for t in ROLE_TAILS[role]:
                    guess = f"{dom}.{prefix}_{t}" if prefix else f"{dom}.{t}"
                    if _exists(hass, guess):
                        return guess
    try:
        for eid in hass.states.async_entity_ids(dom):
            _d, obj = _split(eid)
            if any(obj == t or obj.endswith("_" + t) for t in ROLE_TAILS[role]):
                return eid
    except Exception:  # noqa: BLE001
        pass
    return cand


def prefix_of(work_mode_eid: str) -> str:
    """Prefiks encji falownika z encji trybu pracy (select.deye_work_mode → „deye”); domyślnie „inverter”."""
    _d, obj = _split(work_mode_eid or "")
    tail = ROLE_TAILS["work_mode"][0]
    if obj.endswith(tail):
        return obj[: -len(tail)].rstrip("_") or "inverter"
    return "inverter"


def options_of(hass: HomeAssistant, eid: str) -> list[str] | None:
    st = hass.states.get(eid)
    opts = (getattr(st, "attributes", None) or {}).get("options") if st is not None else None
    if isinstance(opts, (list, tuple)) and opts:
        return [str(o) for o in opts]
    return None


def pick_option(hass: HomeAssistant, eid: str, kind: str) -> str | None:
    """Nazwa opcji select odpowiadająca rodzajowi (export / zero / tou_off / tou_on).

    Gdy encja nie podaje listy opcji — pierwszy kandydat (zachowanie dotychczasowe).
    Gdy podaje, ale żaden kandydat nie pasuje — None (nie zgadujemy, bo zły tryb falownika to realna szkoda)."""
    cands = OPTION_CANDIDATES[kind]
    opts = options_of(hass, eid)
    if opts is None:
        return cands[0]
    lowered = {o.strip().lower(): o for o in opts}
    for c in cands:
        if c.lower() in lowered:
            return lowered[c.lower()]
    return None


def matches_option(hass: HomeAssistant, eid: str, state: str | None, kind: str) -> bool:
    """Czy bieżący stan select odpowiada rodzajowi (bez względu na wielkość liter)."""
    if not state:
        return False
    s = str(state).strip().lower()
    return s in {c.lower() for c in OPTION_CANDIDATES[kind]}


def clamp_to_entity(hass: HomeAssistant, eid: str, value: float) -> float:
    """Przycina wartość do zakresu min/max zadeklarowanego przez encję number."""
    st = hass.states.get(eid)
    attrs = (getattr(st, "attributes", None) or {}) if st is not None else {}
    v = float(value)
    for key, fn in (("max", min), ("min", max)):
        try:
            if attrs.get(key) is not None:
                v = fn(v, float(attrs[key]))
        except (TypeError, ValueError):
            pass
    return v


def normal_charge_current(hass: HomeAssistant, charge_eid: str, remembered: float | None) -> float:
    """Prąd ładowania po „odblokowaniu”: ustawienie użytkownika → zapamiętany sprzed blokady → 170 A,
    zawsze w granicach zakresu encji (np. mały falownik z limitem 37 A nie dostanie 170)."""
    manual = number_value(hass, "normal_charge_current", 0.0)
    if manual and manual > 0:
        base = manual
    elif remembered and remembered > 1:
        base = remembered
    else:
        base = float(NORMAL_CHARGE_CURRENT)
    return clamp_to_entity(hass, charge_eid, base)


def power_setting(hass: HomeAssistant, eid: str, key: str, default: float) -> float:
    """Moc z numberów integracji (sell_export_power_w / surplus_power_w) przycięta do limitu encji falownika."""
    val = number_value(hass, key, default)
    if not val or val <= 0:
        val = default
    return clamp_to_entity(hass, eid, val)


def current_charge(hass: HomeAssistant, eid: str) -> float | None:
    return state_float(hass, eid)
