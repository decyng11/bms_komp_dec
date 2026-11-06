"""Rzeczywisty próg odcięcia baterii w falowniku (Deye / Solarman).

Falownik przestaje rozładowywać baterię poniżej:
  • „SOC wyłączenia” (battery_shutdown_soc), oraz
  • SOC aktywnego programu Time of Use (gdy TOU włączone) — w slocie programu bateria nie schodzi niżej.
Planer nie może zakładać, że energia poniżej tego progu jest dostępna dla domu.
"""
from __future__ import annotations

import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .helpers import number_value, state_float, state_str

MAX_FLOOR = 60.0          # wyższe wartości programu (np. 100 = „nie rozładowuj”) nie są progiem planowania
_SHUTDOWN_RE = re.compile(r"^number\.([a-z0-9_]*?)_?battery_shutdown_soc$")


def _prefix(hass: HomeAssistant) -> str:
    """Prefiks encji falownika (np. 'inverter'), wykryty po encji battery_shutdown_soc."""
    try:
        reg = er.async_get(hass)
        for e in reg.entities.values():
            if e.platform in ("solarman", DOMAIN):      # DOMAIN = falownik dodany bezpośrednio
                m = _SHUTDOWN_RE.match(e.entity_id)
                if m:
                    return m.group(1)
    except Exception:  # noqa: BLE001
        pass
    try:
        for st in hass.states.async_all("number"):
            m = _SHUTDOWN_RE.match(st.entity_id)
            if m:
                return m.group(1)
    except Exception:  # noqa: BLE001
        pass
    return "inverter"


def _eid(dom: str, prefix: str, tail: str) -> str:
    return f"{dom}.{prefix}_{tail}" if prefix else f"{dom}.{tail}"


def _minutes(raw: str | None) -> int | None:
    m = re.match(r"^(\d{1,2}):(\d{2})", raw or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _floor_profile(hass: HomeAssistant) -> dict[str, Any]:
    """{'hourly': [24 × %], 'now_h': int→%, 'shutdown', 'source', 'manual'}.

    hourly[h] = próg odcięcia obowiązujący o pełnej godzinie h (0–23)."""
    manual = number_value(hass, "inverter_floor_soc", 0.0)
    if manual and manual > 0:
        v = min(MAX_FLOOR, float(manual))
        return {"hourly": [v] * 24, "shutdown": None, "source": "ustawione ręcznie", "manual": v, "programs": []}

    prefix = _prefix(hass)
    sd = state_float(hass, _eid("number", prefix, "battery_shutdown_soc"))
    base = min(MAX_FLOOR, max(0.0, sd)) if sd is not None else 0.0

    tou_on = (state_str(hass, _eid("select", prefix, "time_of_use")) or "").lower() not in ("", "disabled")
    progs: list[tuple[int, float, str]] = []     # (start_min, soc, charging)
    if tou_on:
        for n in range(1, 7):
            t = _minutes(state_str(hass, _eid("time", prefix, f"program_{n}_time")))
            s = state_float(hass, _eid("number", prefix, f"program_{n}_soc"))
            if t is None or s is None:
                continue
            progs.append((t, float(s), (state_str(hass, _eid("select", prefix, f"program_{n}_charging")) or "")))
    progs.sort(key=lambda x: x[0])

    hourly: list[float] = []
    for h in range(24):
        f = base
        if progs:
            m = h * 60
            cur = [p for p in progs if p[0] <= m]
            act = cur[-1] if cur else progs[-1]          # przed pierwszym startem obowiązuje ostatni program doby
            if act[1] <= MAX_FLOOR:
                f = max(f, act[1])
        hourly.append(f)
    if sd is None and not progs:
        src = "brak danych z falownika"
    else:
        parts = []
        if sd is not None:
            parts.append(f"SOC wyłączenia {base:.0f}%")
        if progs:
            parts.append("programy Time of Use")
        src = " + ".join(parts)
    return {"hourly": hourly, "shutdown": sd, "source": src, "manual": 0.0, "programs": progs}


def floor_profile(hass: HomeAssistant) -> dict[str, Any]:
    """Profil progu odcięcia; przy dowolnym błędzie zwraca neutralny (brak progu falownika)."""
    try:
        return _floor_profile(hass)
    except Exception:  # noqa: BLE001
        return {"hourly": [0.0] * 24, "shutdown": None, "source": "brak danych z falownika", "manual": 0.0, "programs": []}


def floor_at(profile: dict[str, Any], hour: int) -> float:
    return float(profile["hourly"][hour % 24])
