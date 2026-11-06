"""Base entity for BMS komp-dec."""
from __future__ import annotations
from homeassistant.helpers.entity import Entity

class BmsBaseEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, key: str, name: str, domain: str = "sensor"):
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"bms_komp_dec_v7_{key}"
        self.entity_id = f"{domain}.bms_{key}"