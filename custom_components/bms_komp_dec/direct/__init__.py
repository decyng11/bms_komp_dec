"""Tryb bezpośredni: falownik dodawany do integracji EMS bez integracji ha-solarman.

Klient Solarman V5 / Modbus, parser definicji YAML i warstwa encji pochodzą z projektu ha-solarman
(https://github.com/davidrapan/ha-solarman, licencja MIT) oraz dołączonego w nim klienta Modbus uModbus
(licencja MPL-2.0); pliki licencji leżą obok. Najważniejsze różnice względem oryginału:
  * nic nie zmienia ustawień loggera (brak żądań HTTP do jego strony, brak przełączników chmury / trybu / AP);
  * zapis do falownika jest domyślnie wyłączony i włącza się osobno dla każdego falownika;
  * po każdym zapisie następuje odczyt kontrolny rejestru;
  * brak usług „zapisz dowolny rejestr” — zapis przechodzi tylko przez encje (number / select / switch / time / ...).

Wpis konfiguracji falownika ma w `entry.data` klucz `kind: "inverter"`; wpis EMS (planer) go nie ma.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_KIND, KIND_INVERTER

_LOGGER = logging.getLogger(__name__)

DIRECT_PLATFORMS = ["sensor", "binary_sensor", "number", "select", "switch", "time", "datetime", "button"]


def is_inverter_entry(entry: ConfigEntry) -> bool:
    return (getattr(entry, "data", None) or {}).get(CONF_KIND) == KIND_INVERTER


async def async_setup_inverter_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .coordinator import Coordinator

    coordinator = Coordinator(hass, entry)
    entry.runtime_data = await coordinator.init()
    entry.async_on_unload(coordinator.async_shutdown)
    await hass.config_entries.async_forward_entry_setups(entry, DIRECT_PLATFORMS)

    async def _reload(hass_: HomeAssistant, changed: ConfigEntry) -> None:
        await hass_.config_entries.async_reload(changed.entry_id)

    entry.async_on_unload(entry.add_update_listener(_reload))
    _LOGGER.info("EMS: falownik „%s” (%s) połączony bezpośrednio; zapis %s", entry.title,
                 (entry.options or {}).get("host"), "włączony" if (entry.options or {}).get("allow_write") else "wyłączony")
    return True


async def async_unload_inverter_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, DIRECT_PLATFORMS)
