"""Dostawcy konfiguracji, punktu końcowego i profilu (z ha-solarman, MIT).

Zmiana względem oryginału: wykrywanie loggera (UDP) tylko ODCZYTUJE numer seryjny, MAC i adres. Nie ma
żadnych żądań HTTP do loggera, więc nic nie zmienia jego ustawień (tryb TCP, port, chmura, restart).
"""
from __future__ import annotations

import re

from pathlib import Path
from typing import Any
from logging import getLogger
from dataclasses import dataclass
from functools import cached_property
from collections.abc import Awaitable, Callable

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import *
from .common import *
from .discovery import discover
from .parser import ParameterParser

_LOGGER = getLogger(__name__)

@dataclass
class ConfigurationProvider:
    hass: HomeAssistant
    config_entry: ConfigEntry

    @cached_property
    def _options(self):
        return self.config_entry.options

    @cached_property
    def _additional_options(self):
        return self._options.get(CONF_ADDITIONAL_OPTIONS, {})

    @cached_property
    def name(self):
        return protected(self.config_entry.title, "Configuration parameter [title] does not have a value")

    @cached_property
    def host(self) -> str:
        return protected(self._options.get(CONF_HOST), "Configuration parameter [host] does not have a value")

    @cached_property
    def port(self) -> int:
        return self._options.get(CONF_PORT, DEFAULT_[CONF_PORT])

    @cached_property
    def transport(self) -> str:
        return self._options.get(CONF_TRANSPORT, DEFAULT_[CONF_TRANSPORT])

    @cached_property
    def filename(self) -> str:
        return self._options.get(CONF_LOOKUP_FILE, DEFAULT_[CONF_LOOKUP_FILE])

    @cached_property
    def mb_slave_id(self) -> int:
        return self._additional_options.get(CONF_MB_SLAVE_ID, DEFAULT_[CONF_MB_SLAVE_ID])

    @cached_property
    def allow_write(self) -> bool:
        return bool(self._options.get(CONF_ALLOW_WRITE, DEFAULT_[CONF_ALLOW_WRITE]))

    @cached_property
    def directory(self):
        return str(Path(__file__).parent / LOOKUP_DIRECTORY) + "/"

@dataclass
class EndPointProvider:
    config: ConfigurationProvider
    mac = ""
    serial = 0

    def __getattr__(self, attr: str) -> Any:
        return getattr(self.config, attr)

    @cached_property
    def host(self):
        return self.config.host

    @cached_property
    def connection(self) -> tuple[str, int, str, int, int, int]:
        return self.host, self.port, self.transport, self.serial, self.mb_slave_id, TIMINGS_INTERVAL

    @cached_property
    def ip(self):
        return getipaddress(self.host) 

    async def init(self):
        await self.discover()
        return self

    async def discover(self):
        """Odczytuje z rozgłoszenia UDP numer seryjny, MAC i adres loggera. Nie zmienia żadnych jego ustawień."""
        try:
            # nazwa hosta → adres przez DNS w wątku roboczym (nie blokuje pętli zdarzeń HA)
            ip = await async_execute(lambda: getipaddress(self.host))
            if "modbus" not in self.transport and ip.is_private and (d := await anext((v async for v in await discover(self.hass, str(ip)) if v["ip"] == str(ip)))):
                self.serial = d["serial"]
                self.host = d["ip"]
                self.mac = d["mac"]
        except Exception:
            _LOGGER.debug(f"[{self.host}] Error", exc_info = True)

_SAFE_PROFILE = re.compile(r"(custom/)?[A-Za-z0-9_+\-]+(\.[A-Za-z0-9_+\-]+)*\.ya?ml")

@dataclass
class ProfileProvider:
    config: ConfigurationProvider
    endpoint: EndPointProvider
    parser: ParameterParser | None = None

    def __getattr__(self, attr: str):
        return getattr(self.config, attr)

    @cached_property
    def auto(self):
        return not self.filename or self.filename in AUTODETECTION_REDIRECT

    @cached_property
    def parameters(self):
        return {PARAM_[k]: int(self._additional_options.get(k, DEFAULT_[k])) for k in PARAM_}

    @cached_property
    def info(self):
        return self.parser.info

    async def init(self, request: Callable[[int, dict], Awaitable[dict]] | None = None):
        if not self.auto and not _SAFE_PROFILE.fullmatch(str(self.filename or "")):
            # nazwa profilu z opcji wpisu: tylko plik z folderu definicji albo z custom/ (bez „..”, ścieżek bezwzględnych)
            raise ValueError(f"Nieprawidłowa nazwa profilu: {self.filename!r}")
        if (f := await lookup_profile(request, self.parameters) if self.auto else self.filename) and f != DEFAULT_[CONF_LOOKUP_FILE] and (n := process_profile(f, self.parameters)):
            self.parser = await ParameterParser().init(self.config.directory, n, self.parameters)
        return self
