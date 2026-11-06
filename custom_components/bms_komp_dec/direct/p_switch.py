"""Platforma „switch” trybu bezpośredniego (z ha-solarman, MIT). Bez elementów zmieniających ustawienia loggera."""
from __future__ import annotations

from typing import Any
from logging import getLogger

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, STATE_OFF, STATE_ON
from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass, SwitchEntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import *
from .common import *
from .entity import SolarmanEntity, SolarmanWritableEntity, Coordinator

_LOGGER = getLogger(__name__)

_PLATFORM = "switch"

async def async_setup_entry(_: HomeAssistant, config_entry: ConfigEntry[Coordinator], async_add_entities: AddEntitiesCallback) -> bool:
    _LOGGER.debug(f"async_setup_entry: {config_entry.options}")

    async_add_entities([SolarmanSwitchEntity(config_entry.runtime_data, d).init() for d in config_entry.runtime_data.device.profile.parser.get_entity_descriptions(_PLATFORM)])

    return True

class SolarmanSwitchEntity(SolarmanWritableEntity, SwitchEntity):
    def __init__(self, coordinator, sensor):
        SolarmanWritableEntity.__init__(self, coordinator, sensor)
        self._attr_device_class = SwitchDeviceClass.SWITCH

        self._value_on = 1
        self._value_off = 0
        self._value_bit = None
        if "value" in sensor and (value := sensor["value"]) and not isinstance(value, int):
            if True in value:
                self._value_on = value[True]
            if "on" in value:
                self._value_on = value["on"]
            if False in value:
                self._value_off = value[False]
            if "off" in value:
                self._value_off = value["off"]
            if "bit" in value:
                self._value_bit = value["bit"]

    def _to_native_value(self, value: int) -> int:
        if self._value_bit is not None:
            return (self._get_attr_native_value & ~(1 << self._value_bit)) | (value << self._value_bit)
        return value

    @property
    def is_on(self) -> bool | None:
        return (
            self._attr_native_value >> self._value_bit & 1
            if self._attr_native_value is not None and self._value_bit is not None
            else self._attr_native_value
        ) != self._value_off

    async def async_turn_on(self, **kwargs: Any):
        value = self._to_native_value(self._value_on)
        await self.write(value, value)

    async def async_turn_off(self, **kwargs: Any):
        value = self._to_native_value(self._value_off)
        await self.write(value, value)
