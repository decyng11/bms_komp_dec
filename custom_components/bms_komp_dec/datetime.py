"""Platforma „datetime” — używana tylko dla falowników dodanych bezpośrednio (EMS nie ma własnych encji tego typu)."""
from __future__ import annotations

from .direct import is_inverter_entry


async def async_setup_entry(hass, entry, async_add_entities):
    if is_inverter_entry(entry):
        from .direct.p_datetime import async_setup_entry as _direct_setup
        return await _direct_setup(hass, entry, async_add_entities)
    return None
