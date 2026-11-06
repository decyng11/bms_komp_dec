"""Formularze dodawania i opcji falownika (tryb bezpośredni). Układ pól jak w ha-solarman (MIT), plus „Zezwól na zapis”."""
from __future__ import annotations

from logging import getLogger
from socket import getaddrinfo, herror, gaierror, timeout
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import BooleanSelector, SelectSelector, SelectSelectorConfig

from .common import async_listdir, strepr
from .const import (
    CONF_ADDITIONAL_OPTIONS, CONF_ALLOW_WRITE, CONF_BATTERY_LIFE_CYCLE_RATING, CONF_BATTERY_NOMINAL_VOLTAGE,
    CONF_HOST, CONF_LOOKUP_FILE, CONF_MB_SLAVE_ID, CONF_MOD, CONF_MPPT, CONF_PACK, CONF_PHASE, CONF_PORT,
    CONF_TRANSPORT, DEFAULT_, IP_ANY, LOOKUP_CUSTOM_DIRECTORY_PATH, LOOKUP_DIRECTORY_PATH, SUGGESTED_VALUE,
)

_LOGGER = getLogger(__name__)

CONF_NAME = "name"


def creation_schema() -> dict:
    return {vol.Required(CONF_NAME, default=DEFAULT_[CONF_NAME]): str}


def configuration_schema() -> dict:
    def d(key, **extra):
        return {"default": DEFAULT_[key], "description": {SUGGESTED_VALUE: DEFAULT_[key]}, **extra}

    return {
        vol.Required(CONF_HOST, **d(CONF_HOST)): str,
        vol.Optional(CONF_PORT, **d(CONF_PORT)): cv.port,
        vol.Optional(CONF_TRANSPORT, **d(CONF_TRANSPORT)): SelectSelector(SelectSelectorConfig(
            options=["tcp", "modbus_tcp", "modbus_rtu"], mode="dropdown", translation_key="transport")),
        vol.Optional(CONF_LOOKUP_FILE, **d(CONF_LOOKUP_FILE)): str,
        vol.Optional(CONF_ALLOW_WRITE, default=DEFAULT_[CONF_ALLOW_WRITE]): BooleanSelector(),
        vol.Required(CONF_ADDITIONAL_OPTIONS): section(
            vol.Schema({
                vol.Optional(CONF_MOD, **d(CONF_MOD)): vol.All(vol.Coerce(int), vol.Range(min=0, max=2)),
                vol.Optional(CONF_MPPT, **d(CONF_MPPT)): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
                vol.Optional(CONF_PHASE, **d(CONF_PHASE)): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
                vol.Optional(CONF_PACK, **d(CONF_PACK)): vol.All(vol.Coerce(int), vol.Range(min=-1, max=20)),
                vol.Optional(CONF_BATTERY_NOMINAL_VOLTAGE, **d(CONF_BATTERY_NOMINAL_VOLTAGE)): cv.positive_float,
                vol.Optional(CONF_BATTERY_LIFE_CYCLE_RATING, **d(CONF_BATTERY_LIFE_CYCLE_RATING)): cv.positive_int,
                vol.Optional(CONF_MB_SLAVE_ID, **d(CONF_MB_SLAVE_ID)): cv.positive_int,
            }),
            {"collapsed": True},
        ),
    }


async def data_schema(hass: HomeAssistant, schema: dict[str, Any]) -> vol.Schema:
    """Dodaje listę profili: „Auto”, dołączone definicje i własne z podfolderu custom/."""
    schema[CONF_LOOKUP_FILE] = vol.In(
        [DEFAULT_[CONF_LOOKUP_FILE]]
        + await async_listdir(hass.config.path(LOOKUP_DIRECTORY_PATH))
        + await async_listdir(hass.config.path(LOOKUP_CUSTOM_DIRECTORY_PATH), "custom/")
    )
    return vol.Schema(schema)


def validate_connection(user_input: dict[str, Any]) -> dict[str, str] | None:
    """Sprawdza tylko, czy host da się zamienić na adres; nie łączy się z falownikiem."""
    error = "unknown"
    try:
        if host := user_input.get(CONF_HOST, IP_ANY):
            getaddrinfo(host, user_input.get(CONF_PORT, DEFAULT_[CONF_PORT]), family=0, type=0, proto=0, flags=0)
    except herror:
        error = "invalid_host"
    except timeout:
        error = "timeout_connect"
    except gaierror:
        error = "cannot_connect"
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("BMS: walidacja adresu falownika nieudana: %s", strepr(err))
    else:
        return None
    return {"base": error}


def remove_defaults(user_input: dict[str, Any]) -> dict[str, Any]:
    """Zapisuje tylko wartości inne niż domyślne (jak ha-solarman)."""
    for k in list(user_input.keys()):
        if k == CONF_ADDITIONAL_OPTIONS:
            for sub in list(user_input[k].keys()):
                if user_input[k][sub] == DEFAULT_.get(sub):
                    del user_input[k][sub]
            if not user_input[k]:
                del user_input[k]
        elif user_input[k] == DEFAULT_.get(k):
            del user_input[k]
    return user_input
