"""Platforma „select” trybu bezpośredniego (z ha-solarman, MIT). Bez elementów zmieniających ustawienia loggera."""
from __future__ import annotations

from logging import getLogger

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import *
from .common import *
from .entity import SolarmanEntity, SolarmanWritableEntity, Coordinator

_LOGGER = getLogger(__name__)

_PLATFORM = "select"

async def async_setup_entry(_: HomeAssistant, config_entry: ConfigEntry[Coordinator], async_add_entities: AddEntitiesCallback) -> bool:
    _LOGGER.debug(f"async_setup_entry: {config_entry.options}")

    async_add_entities([SolarmanSelectEntity(config_entry.runtime_data, d).init() for d in config_entry.runtime_data.device.profile.parser.get_entity_descriptions(_PLATFORM)])

    return True

class SolarmanSelectEntity(SolarmanWritableEntity, SelectEntity):
    def __init__(self, coordinator, sensor):
        SolarmanWritableEntity.__init__(self, coordinator, sensor)

        self.mask = display.get("mask") if (display := sensor.get("display")) else None

        if "lookup" in sensor:
            self.dictionary = sensor["lookup"]

        if len(self.registers) > 1:
            _LOGGER.warning(f"SolarmanSelectEntity.__init__: {self._attr_name} contains {len(self.registers)} registers!")

    def get_key(self, value: str):
        if self.dictionary:
            for o in self.dictionary:
                if o["value"] == value and (key := from_bit_index(o["bit"]) if "bit" in o else o["key"]) is not None:
                    return (key if not "mode" in o else (self._attr_value | key)) if not self.mask else (self._attr_value & (0xFFFFFFFF - self.mask) | key)

        return self.options.index(value)

    @property
    def current_option(self):
        """Return the current option of this select."""
        try:
            return self._attr_state if not self.mask else lookup_value(self._attr_value & self.mask, self.dictionary)
        except Exception as e:
            _LOGGER.debug(f"SolarmanSelectEntity.current_option of {self._attr_name} w/ {self._attr_value}: {strepr(e)}")
        return None

    async def async_select_option(self, option: str):
        """Change the selected option."""
        await self.write(self.get_key(option), option)
