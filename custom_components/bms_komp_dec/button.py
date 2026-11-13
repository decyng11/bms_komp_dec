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
    async_add_entities([BmsButton(coordinator, k, n, i) for k, n, i in BUTTONS]
                        + [BmsClearHistoryButton(coordinator), BmsResetPvLearningButton(coordinator)])


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


class BmsClearHistoryButton(BmsBaseEntity, ButtonEntity):
    """Czyści zebraną historię zużycia (dni, profile godzinowe, historia prognoz) — zbieranie zaczyna się od zera."""

    def __init__(self, coordinator):
        super().__init__("wyczysc_historie_zuzycia", "Wyczyść historię zużycia", domain="button")
        self._coordinator = coordinator
        self._attr_icon = "mdi:database-remove"

    async def async_press(self) -> None:
        lf = getattr(self._coordinator, "load_forecast", None)
        if lf is None:
            raise HomeAssistantError("EMS nie jest jeszcze gotowy — spróbuj za chwilę.")
        lf.clear_history()
        runtime = getattr(self._coordinator, "runtime", None)
        if runtime is not None:
            runtime.log.add("command", "Wyczyszczono historię zużycia — zbieranie od zera (ręcznie)", "ok")
        refresh = getattr(self._coordinator, "async_request_refresh", None)
        if refresh is not None:
            await refresh()


class BmsResetPvLearningButton(BmsBaseEntity, ButtonEntity):
    """Zeruje naukę korekty prognozy PV (np. po zmianie ustawień źródła prognozy) — korekta wraca do ×1 i uczy się od nowa."""

    def __init__(self, coordinator):
        super().__init__("wyzeruj_korekte_pv", "Wyzeruj naukę korekty prognozy PV", domain="button")
        self._coordinator = coordinator
        self._attr_icon = "mdi:solar-power-variant-outline"

    async def async_press(self) -> None:
        runtime = getattr(self._coordinator, "runtime", None)
        if runtime is None or getattr(runtime, "insights", None) is None:
            raise HomeAssistantError("EMS nie jest jeszcze gotowy — spróbuj za chwilę.")
        n = runtime.insights.reset_pv_learning()
        runtime._plan_ts = 0.0  # noqa: SLF001 — plan policzy się od nowa bez starej korekty
        runtime.log.add("command", f"Wyzerowano naukę korekty prognozy PV (usunięto prognozy z {n} dni) — korekta uczy się od nowa (ręcznie)", "ok")
        refresh = getattr(self._coordinator, "async_request_refresh", None)
        if refresh is not None:
            await refresh()
