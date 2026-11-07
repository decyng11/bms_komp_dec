"""Buttons for EMS komp-dec."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .direct import is_inverter_entry
from .const import BUTTONS
from .entity import BmsBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    if is_inverter_entry(entry):                      # falownik dodany bezpośrednio (tryb bezpośredni)
        from .direct.p_button import async_setup_entry as _direct_setup
        return await _direct_setup(hass, entry, async_add_entities)
    await _async_setup_bms_entry(hass, entry, async_add_entities)


async def _async_setup_bms_entry(hass, entry, async_add_entities):
    coordinator = hass.data["bms_komp_dec"][entry.entry_id]
    async_add_entities([BmsButton(coordinator, k, n, i) for k, n, i in BUTTONS])


class BmsButton(BmsBaseEntity, ButtonEntity):
    def __init__(self, coordinator, key, name, icon):
        super().__init__(key, name, domain="button")
        self._coordinator = coordinator
        self._attr_icon = icon

    async def async_press(self) -> None:
        runtime = getattr(self._coordinator, "runtime", None)
        if runtime is None:
            raise HomeAssistantError("EMS nie jest jeszcze gotowy — spróbuj za chwilę.")
        await runtime.run_command(self._key, source="ręcznie")
