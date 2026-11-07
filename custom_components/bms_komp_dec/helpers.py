"""Wspólne funkcje pomocnicze EMS komp-dec (bez zależności od innych modułów integracji)."""
from __future__ import annotations

import math
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN

UID_PREFIX = "bms_komp_dec_v7_"
BAD_STATES = ("unknown", "unavailable", "none", "")


def find_eid(hass: HomeAssistant, domain: str, key: str) -> str:
    """entity_id encji integracji (przez unique_id; fallback na domyślny)."""
    try:
        eid = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{UID_PREFIX}{key}")
    except Exception:  # noqa: BLE001
        eid = None
    return eid or f"{domain}.bms_{key}"


def state_str(hass: HomeAssistant, eid: str | None) -> str | None:
    if not eid:
        return None
    st = hass.states.get(eid)
    if st is None or str(st.state).lower() in BAD_STATES:
        return None
    return str(st.state)


def state_float(hass: HomeAssistant, eid: str | None, default: float | None = None) -> float | None:
    raw = state_str(hass, eid)
    if raw is None:
        return default
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return default
    return val if math.isfinite(val) else default      # „nan”/„inf” z sensorów szablonowych


def number_value(hass: HomeAssistant, key: str, default: float) -> float:
    val = state_float(hass, find_eid(hass, "number", key))
    return default if val is None else val


def switch_on(hass: HomeAssistant, key: str, default: bool = False) -> bool:
    raw = state_str(hass, find_eid(hass, "switch", key))
    if raw is None:
        return default
    return raw == "on"


def wear_cost_per_kwh(hass: HomeAssistant, capacity_kwh: float) -> float:
    """Koszt zużycia baterii (zł) na każdą kWh, która przez nią przechodzi: cena baterii / (cykle × pojemność).

    0, gdy cena baterii nie jest ustawiona (number.bms_battery_price_pln = 0) — wtedy planer działa jak dotąd."""
    price = number_value(hass, "battery_price_pln", 0.0)
    cycles = number_value(hass, "battery_cycles", 6000.0)
    try:
        cap = float(capacity_kwh)
    except (TypeError, ValueError):
        return 0.0
    if not (math.isfinite(price) and math.isfinite(cycles) and math.isfinite(cap)) or price <= 0 or cycles <= 0 or cap <= 0:
        return 0.0
    return price / (cycles * cap)


def normalize_price(value: float | None) -> float | None:
    """Ceny > 20 traktujemy jako PLN/MWh (RCE z PSE) i przeliczamy na PLN/kWh."""
    if value is None or not math.isfinite(value):
        return None
    return value / 1000.0 if abs(value) > 20 else value


class ThrottledStore:
    """Store z opóźnionym zapisem, który NIE przesuwa terminu przy każdym wywołaniu.

    Store.async_delay_save() przy każdym wywołaniu kasuje poprzedni timer i ustawia
    nowy — przy wołaniu co kilka sekund dane nigdy nie trafiały na dysk.
    """

    def __init__(self, hass: HomeAssistant, version: int, key: str, delay: float = 60) -> None:
        self._store: Store = Store(hass, version, key)
        self._delay = delay
        self._pending = False

    async def async_load(self) -> Any:
        return await self._store.async_load()

    def request_save(self, data_func: Callable[[], Any]) -> None:
        if self._pending:
            return
        self._pending = True

        def _wrapped() -> Any:
            self._pending = False
            return data_func()

        self._store.async_delay_save(_wrapped, self._delay)

    async def async_save_now(self, data: Any) -> None:
        self._pending = False
        await self._store.async_save(data)


def entry_settings(entry) -> dict:
    """Ustawienia wpisu: options (po rekonfiguracji) zastępują data w całości."""
    return dict(entry.options) if getattr(entry, "options", None) else dict(entry.data)
