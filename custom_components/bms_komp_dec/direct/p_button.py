"""Platforma „button” trybu bezpośredniego (z ha-solarman, MIT). Bez elementów zmieniających ustawienia loggera."""
from __future__ import annotations

import re
from logging import getLogger

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, STATE_OFF, STATE_ON
from homeassistant.components.button import ButtonEntity, ButtonDeviceClass, ButtonEntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import *
from .common import *
from .entity import SolarmanEntity, SolarmanWritableEntity, Coordinator

_LOGGER = getLogger(__name__)

_PLATFORM = "button"

async def async_setup_entry(_: HomeAssistant, config_entry: ConfigEntry[Coordinator], async_add_entities: AddEntitiesCallback) -> bool:
    _LOGGER.debug(f"async_setup_entry: {config_entry.options}")

    async_add_entities([SolarmanButtonEntity(config_entry.runtime_data, d).init() for d in config_entry.runtime_data.device.profile.parser.get_entity_descriptions(_PLATFORM)])

    return True

# przyciski, których jedno naciśnięcie robi coś nieodwracalnego albo przerywa pracę falownika
_DANGEROUS = re.compile(r"reset|restart|reboot|clear|factory|delete|erase|format|wipe|default", re.IGNORECASE)


class SolarmanButtonEntity(SolarmanWritableEntity, ButtonEntity):
    def __init__(self, coordinator, sensor):
        SolarmanWritableEntity.__init__(self, coordinator, sensor)
        # niebezpieczne przyciski (np. „Factory reset”, „Clear records”, „Restart”) są domyślnie WYŁĄCZONE w rejestrze encji:
        # nie trafią na pulpit, do asystenta głosowego ani do automatyzacji „wszystkie przyciski”, dopóki ich świadomie nie włączysz
        if _DANGEROUS.search(str(sensor.get("name") or "")):
            self._attr_entity_registry_enabled_default = False

        self._value = 1
        self._value_bit = None
        if "value" in sensor and (value := sensor["value"]) and not isinstance(value, int):
            if True in value:
                self._value = value[True]
            if "on" in value:
                self._value = value["on"]
            if "bit" in value:
                self._value_bit = value["bit"]

    def _to_native_value(self, value: int) -> int:
        if self._value_bit:
            return (self._get_attr_native_value & ~(1 << self._value_bit)) | (value << self._value_bit) 
        return value

    async def async_press(self):
        """Handle the button press."""
        await self.write(self._to_native_value(self._value))
