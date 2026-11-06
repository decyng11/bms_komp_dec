"""Dziennik decyzji BMS — co, kiedy i dlaczego system zrobił (funkcja 4)."""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .helpers import ThrottledStore

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "bms_komp_dec_decision_log"
MAX_ENTRIES = 300

# kind: schedule | guard | price | profit | reserve | command | verify | auto | system
LEVELS = ("info", "ok", "warn", "error")


class DecisionLog:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = ThrottledStore(hass, 1, STORAGE_KEY, delay=30)
        self.entries: deque[dict[str, Any]] = deque(maxlen=MAX_ENTRIES)
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        try:
            data = await self._store.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("BMS log: błąd wczytywania: %s", err)
            return
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            for item in data["entries"][-MAX_ENTRIES:]:
                if isinstance(item, dict) and "ts" in item and "msg" in item:
                    self.entries.append(item)

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)

        def _remove() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)

        return _remove

    def add(self, kind: str, msg: str, level: str = "info", **extra: Any) -> None:
        if level not in LEVELS:
            level = "info"
        entry: dict[str, Any] = {
            "ts": dt_util.now().isoformat(timespec="seconds"),
            "kind": kind,
            "level": level,
            "msg": msg,
        }
        if extra:
            entry["extra"] = {k: v for k, v in extra.items() if v is not None}
        self.entries.append(entry)
        log = {"warn": _LOGGER.warning, "error": _LOGGER.error}.get(level, _LOGGER.info)
        log("BMS [%s] %s", kind, msg)
        self._store.request_save(lambda: {"entries": list(self.entries)})
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    def last(self, n: int = 60) -> list[dict[str, Any]]:
        items = list(self.entries)[-n:]
        items.reverse()  # najnowsze pierwsze
        return items

    @property
    def latest_text(self) -> str:
        if not self.entries:
            return "brak wpisów"
        e = self.entries[-1]
        return str(e["msg"])[:250]

    def last_ts(self) -> datetime | None:
        if not self.entries:
            return None
        return dt_util.parse_datetime(str(self.entries[-1]["ts"]))
