"""Binarne sensory BMS komp-dec."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity

from .direct import is_inverter_entry
from .const import BINARY_SENSORS, CONF_CHARGE_CURRENT, CONF_WORK_MODE, DOMAIN
from .entity import BmsBaseEntity
from .helpers import number_value

PEAK_SHAVING_THRESHOLD_W = 4000
SELF_CONSUMPTION_MIN_SOC = 50
DEFAULT_IMPORT_LIMIT_KWH = 1.0
DEFAULT_SELL_BLOCK_W = 2000.0


async def async_setup_entry(hass, entry, async_add_entities):
    if is_inverter_entry(entry):                      # falownik dodany bezpośrednio (tryb bezpośredni)
        from .direct.p_binary_sensor import async_setup_entry as _direct_setup
        return await _direct_setup(hass, entry, async_add_entities)
    await _async_setup_bms_entry(hass, entry, async_add_entities)


async def _async_setup_bms_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        BmsBinarySensor(coordinator, key, name, icon)
        for key, name, icon in BINARY_SENSORS
    )


class BmsBinarySensor(BmsBaseEntity, BinarySensorEntity):
    def __init__(self, coordinator, key, name, icon):
        super().__init__(key, name, domain="binary_sensor")
        self.coordinator = coordinator
        self._attr_icon = icon

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def extra_state_attributes(self):
        rt = getattr(self.coordinator, "runtime", None)
        if rt is None:
            return None
        if self._key == "dzien_swiateczny":
            return {"nazwa": rt.holiday_label()}
        if self._key == "sprzedaz_nieoplacalna":
            ps = rt.profit_status()
            return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in ps.items()}
        if self._key == "ujemna_cena_aktywna":
            return {"cena_rce": rt.sell_price(), "prog": number_value(self.hass, "low_price_threshold", 0.0),
                    "ograniczenie_eksportu": bool(rt.state["price_reaction"].get("active"))}
        return None

    @property
    def is_on(self) -> bool | None:
        c = self.coordinator
        data = c.data or {}
        rt = getattr(c, "runtime", None)

        if self._key == "sprzedaz_aktywna":
            return c.get_str(CONF_WORK_MODE, "").lower() == "export first"

        if self._key == "blokada_pv_aktywna":
            raw = c.get_str(CONF_CHARGE_CURRENT, "")
            if raw == "":
                return None
            try:
                return float(raw) <= 0.1
            except ValueError:
                return None

        if self._key == "peak_shaving_active":
            return abs(data.get("grid_power") or 0) > PEAK_SHAVING_THRESHOLD_W

        if self._key == "grid_import_legal_blocked":
            imported = data.get("energy_grid_import_today")
            if imported is None:
                return None
            return imported > number_value(self.hass, "grid_import_daily_limit", DEFAULT_IMPORT_LIMIT_KWH)

        if self._key == "self_consumption_ok":
            soc = data.get("soc")
            if soc is None:
                return None
            return soc >= SELF_CONSUMPTION_MIN_SOC

        if self._key == "sprzedaz_zablokowana_importem":
            grid = data.get("grid_power")
            if grid is None:
                return None
            limit = number_value(self.hass, "grid_import_sell_block_w", DEFAULT_SELL_BLOCK_W)
            return limit > 0 and grid > limit

        if rt is None:
            return None

        if self._key == "sprzedaz_zablokowana_arbitraz":
            return rt.arbitrage_status()[0]

        if self._key == "ujemna_cena_aktywna":
            price = rt.sell_price()
            if price is None:
                return None
            return price < number_value(self.hass, "low_price_threshold", 0.0)

        if self._key == "sprzedaz_nieoplacalna":
            ok = rt.profit_status()["ok"]
            return None if ok is None else (not ok)

        if self._key == "dzien_swiateczny":
            return rt.holiday_label() is not None

        return False
