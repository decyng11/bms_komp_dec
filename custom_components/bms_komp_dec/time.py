"""Time entities for BMS komp-dec."""
from __future__ import annotations
from datetime import time as dt_time
from homeassistant.components.time import TimeEntity
from homeassistant.helpers.restore_state import RestoreEntity
from .direct import is_inverter_entry
from .const import TIMES

async def async_setup_entry(hass, entry, async_add_entities):
    if is_inverter_entry(entry):                      # falownik dodany bezpośrednio (tryb bezpośredni)
        from .direct.p_time import async_setup_entry as _direct_setup
        return await _direct_setup(hass, entry, async_add_entities)
    await _async_setup_bms_entry(hass, entry, async_add_entities)


async def _async_setup_bms_entry(hass, entry, async_add_entities):
    async_add_entities([BmsTime(k, n) for k, n in TIMES])

class BmsTime(RestoreEntity, TimeEntity):
    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, key: str, name: str):
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"bms_komp_dec_v7_{key}"
        self.entity_id = f"time.bms_{key}"
        self._value = dt_time(0, 0)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state and last.state not in ("unknown", "unavailable", ""):
            try:
                parts = str(last.state).split(":")
                self._value = dt_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                pass
        self.async_write_ha_state()

    @property
    def native_value(self) -> dt_time:
        return self._value

    async def async_set_value(self, value) -> None:
        if isinstance(value, str):
            try:
                parts = value.split(":")
                value = dt_time(int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                return
        self._value = value
        self.async_write_ha_state()