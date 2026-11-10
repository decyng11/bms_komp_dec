"""Switches for EMS komp-dec."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity

from . import inverter_ctl as ictl
from .direct import is_inverter_entry
from .const import SWITCHES, TOU_EID  # noqa: F401  (TOU_EID: nazwa domyślna, zachowana dla zgodności)
from .entity import BmsBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    if is_inverter_entry(entry):                      # falownik dodany bezpośrednio (tryb bezpośredni)
        from .direct.p_switch import async_setup_entry as _direct_setup
        return await _direct_setup(hass, entry, async_add_entities)
    await _async_setup_bms_entry(hass, entry, async_add_entities)


async def _async_setup_bms_entry(hass, entry, async_add_entities):
    async_add_entities([BmsSwitch(k, n, i, d) for k, n, i, d in SWITCHES])


class BmsSwitch(BmsBaseEntity, RestoreEntity, SwitchEntity):
    def __init__(self, key, name, icon, default=False):
        super().__init__(key, name, domain="switch")
        self._attr_icon = icon
        self._is_on = bool(default)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self._is_on = last.state == "on"
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._is_on

    def _cfg(self) -> dict:
        for v in (self.hass.data.get("bms_komp_dec") or {}).values():
            if hasattr(v, "runtime") and isinstance(getattr(v, "config", None), dict):   # koordynator (nie optymalizator)
                return v.config
        return {}

    async def _apply_force_charge(self, enable: bool) -> bool:
        """'Wymuś ładowanie z sieci' ustawia to samo co przyciski włącz/wyłącz ładowanie z sieci."""
        eid = ictl.resolve(self.hass, self._cfg(), "tou_select")
        option = ictl.pick_option(self.hass, eid, "tou_off" if enable else "tou_on")
        if option is None:
            _LOGGER.error("EMS switch %s: encja %s nie ma oczekiwanej opcji TOU (dostępne: %s)",
                          self._key, eid, ictl.options_of(self.hass, eid))
            return False
        if enable:                       # prąd ładowania 0 A (blokada PV) blokuje też ładowanie z sieci
            for v in (self.hass.data.get("bms_komp_dec") or {}).values():
                rt = getattr(v, "runtime", None)
                if rt is not None and hasattr(rt, "pv_charge_blocked"):
                    try:
                        if rt.pv_charge_blocked():
                            await rt.run_command("odblokuj_ladowanie", source="Wymuś ładowanie z sieci", enforce_guard=False)
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.error("EMS switch %s: nie udało się przywrócić prądu ładowania: %s", self._key, err)
                    break
        try:
            await self.hass.services.async_call(
                "select", "select_option", {"entity_id": eid, "option": option}, blocking=True)
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS switch %s: nie udało się ustawić %s: %s", self._key, eid, err)
            return False

    async def async_turn_on(self, **kwargs):
        if self._key == "force_charge_battery" and not await self._apply_force_charge(True):
            return
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        if self._key == "force_charge_battery" and not await self._apply_force_charge(False):
            return
        self._is_on = False
        self.async_write_ha_state()
