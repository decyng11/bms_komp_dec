"""Data coordinator for EMS komp-dec."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .helpers import entry_settings
from .const import (
    DOMAIN, DEFAULT_CONFIG,
    CONF_PV_POWER, CONF_LOAD_POWER, CONF_BATTERY_POWER, CONF_GRID_POWER, CONF_SOC,
    CONF_ENERGY_PV_TODAY, CONF_ENERGY_LOAD_TODAY,
    CONF_ENERGY_GRID_EXPORT_TODAY, CONF_ENERGY_GRID_IMPORT_TODAY,
    CONF_ENERGY_BATT_CHARGE_TODAY, CONF_ENERGY_BATT_DISCHARGE_TODAY,
    CONF_PV1_VOLTAGE, CONF_PV1_CURRENT, CONF_PV2_VOLTAGE, CONF_PV2_CURRENT,
    CONF_GRID_VOLTAGE_L1, CONF_GRID_CURRENT_L1, CONF_LOAD_VOLTAGE_L1, CONF_LOAD_CURRENT_L1,
    CONF_GRID_POWER_L1, CONF_GRID_POWER_L2, CONF_GRID_POWER_L3, CONF_LOAD_POWER_L1, CONF_LOAD_POWER_L2, CONF_LOAD_POWER_L3,
    CONF_BATTERY_VOLTAGE, CONF_BATTERY_CURRENT,
)
from .load_forecast import LoadForecaster

_LOGGER = logging.getLogger(__name__)

_BAD_STATES = ("unknown", "unavailable", "none", "")


class BmsCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN,
            update_interval=timedelta(seconds=10),
        )
        self.entry = entry
        self.config = {**DEFAULT_CONFIG, **entry_settings(entry)}
        self.load_forecast = LoadForecaster(
            hass, lambda: self.config.get(CONF_ENERGY_LOAD_TODAY)
        )
        # Ustawiane w async_setup_entry (BmsRuntime); encje czytają je przez coordinator.runtime.
        self.runtime = None

    # ------------------------------------------------------------ helpers
    def get_str(self, key: str, default: str = "") -> str:
        """Stan encji źródłowej jako tekst (lub default, gdy niedostępna)."""
        eid = self.config.get(key)
        if not eid:
            return default
        st = self.hass.states.get(eid)
        if not st or str(st.state).lower() in _BAD_STATES:
            return default
        return str(st.state)

    def get_float_opt(self, key: str) -> float | None:
        """Wartość liczbowa encji źródłowej albo None, gdy niedostępna."""
        raw = self.get_str(key, "")
        if raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def get_float(self, key: str, default: float = 0.0) -> float:
        val = self.get_float_opt(key)
        return default if val is None else val

    def _phase_sum(self, keys) -> float | None:
        """Suma mocy z podanych encji fazowych; None, gdy żadna nie jest skonfigurowana i dostępna."""
        vals = [v for v in (self.get_float_opt(k) for k in keys) if v is not None]
        return sum(vals) if vals else None

    # zachowana nazwa dla kompatybilności ze starszym kodem
    _get_float = get_float

    # ------------------------------------------------------------- update
    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}

        pv_calc = (self.get_float(CONF_PV1_VOLTAGE) * self.get_float(CONF_PV1_CURRENT) +
                   self.get_float(CONF_PV2_VOLTAGE) * self.get_float(CONF_PV2_CURRENT))
        batt_calc = self.get_float(CONF_BATTERY_VOLTAGE) * self.get_float(CONF_BATTERY_CURRENT)
        # zapasowe wyliczenie, gdy encja mocy całkowitej milczy: suma mocy faz L1–L3, a bez nich napięcie × prąd fazy L1
        grid_phase = self._phase_sum((CONF_GRID_POWER_L1, CONF_GRID_POWER_L2, CONF_GRID_POWER_L3))
        load_phase = self._phase_sum((CONF_LOAD_POWER_L1, CONF_LOAD_POWER_L2, CONF_LOAD_POWER_L3))
        grid_calc = grid_phase if grid_phase is not None else self.get_float(CONF_GRID_VOLTAGE_L1) * self.get_float(CONF_GRID_CURRENT_L1)
        load_calc = load_phase if load_phase is not None else self.get_float(CONF_LOAD_VOLTAGE_L1) * self.get_float(CONF_LOAD_CURRENT_L1)

        pv_direct = self.get_float(CONF_PV_POWER)
        batt_direct = self.get_float(CONF_BATTERY_POWER)
        grid_direct = self.get_float(CONF_GRID_POWER)
        load_direct = self.get_float(CONF_LOAD_POWER)

        data["pv_power"] = round(max(pv_direct, pv_calc), 1)
        data["battery_power"] = round(batt_direct if abs(batt_direct) > 1 else batt_calc, 1)
        data["grid_power"] = round(grid_direct if abs(grid_direct) > 1 else grid_calc, 1)
        data["load_power"] = round(load_direct if abs(load_direct) > 1 else abs(load_calc), 1)

        # SOC i liczniki energii: None gdy źródło niedostępne. Zwracanie 0 powodowało
        # fałszywe "resety" liczników total_increasing i skoki w statystykach energii.
        data["soc"] = self.get_float_opt(CONF_SOC)
        data["energy_pv_today"] = self.get_float_opt(CONF_ENERGY_PV_TODAY)
        data["energy_load_today"] = self.get_float_opt(CONF_ENERGY_LOAD_TODAY)
        data["energy_grid_export_today"] = self.get_float_opt(CONF_ENERGY_GRID_EXPORT_TODAY)
        data["energy_grid_import_today"] = self.get_float_opt(CONF_ENERGY_GRID_IMPORT_TODAY)
        data["energy_battery_charge_today"] = self.get_float_opt(CONF_ENERGY_BATT_CHARGE_TODAY)
        data["energy_battery_discharge_today"] = self.get_float_opt(CONF_ENERGY_BATT_DISCHARGE_TODAY)

        # Błąd prognozy zużycia nie może zatrzymać całego koordynatora.
        try:
            self.load_forecast.update()
            data["load_forecast"] = self.load_forecast.as_dict()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS: błąd prognozy zużycia: %s", err, exc_info=True)
            data["load_forecast"] = {}

        return data
