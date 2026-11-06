"""Numbers for BMS komp-dec."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .direct import is_inverter_entry
from .const import NUMBERS, NUMBER_DEFAULTS


async def async_setup_entry(hass, entry, async_add_entities):
    if is_inverter_entry(entry):                      # falownik dodany bezpośrednio (tryb bezpośredni)
        from .direct.p_number import async_setup_entry as _direct_setup
        return await _direct_setup(hass, entry, async_add_entities)
    await _async_setup_bms_entry(hass, entry, async_add_entities)


async def _async_setup_bms_entry(hass, entry, async_add_entities):
    async_add_entities([BmsNumber(k, n, mn, mx, st, u) for k, n, mn, mx, st, u in NUMBERS])


class BmsNumber(RestoreEntity, NumberEntity):
    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, key: str, name: str, mn: float, mx: float, step: float, unit: str):
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"bms_komp_dec_v7_{key}"
        self.entity_id = f"number.bms_{key}"
        self._attr_native_min_value = mn
        self._attr_native_max_value = mx
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        # Wartość startowa (gdy brak zapamiętanego stanu) — wcześniej zawsze = min (0),
        # przez co progi SOC były domyślnie wyłączone.
        default = NUMBER_DEFAULTS.get(key, mn)
        self._value = min(max(float(default), mn), mx)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state and last.state not in ("unknown", "unavailable", ""):
            try:
                restored = float(last.state)
                self._value = min(max(restored, self._attr_native_min_value), self._attr_native_max_value)
            except (ValueError, TypeError):
                pass
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        self.async_write_ha_state()
