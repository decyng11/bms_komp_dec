"""Magazyn danych Diagnostyki w Home Assistant (zamiast localStorage przeglądarki).

Dziennik zmian parametrów, kopie bezpieczeństwa, profile, alarmy — wcześniej tylko w jednej przeglądarce
(czyszczenie danych witryny kasowało historię; na telefonie i komputerze były różne). Teraz wspólny magazyn
po stronie HA, dostępny tylko dla administratorów (kontrola w usługach)."""
from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.util import dt as dt_util

from .helpers import ThrottledStore

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "bms_komp_dec_diag"
ALLOWED_KEYS = ("log", "auto", "profiles", "prefix", "watch", "alarms", "backups")
MAX_VALUE_BYTES = 400_000
MAX_TOTAL_BYTES = 1_500_000


class DiagStore:
    def __init__(self, hass) -> None:
        self.hass = hass
        self._store = ThrottledStore(hass, 1, STORAGE_KEY, delay=5)
        self.data: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        try:
            raw = await self._store.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("BMS diag store: błąd wczytywania: %s", err)
            return
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in ALLOWED_KEYS and isinstance(v, dict) and "v" in v:
                    self.data[k] = {"v": v["v"], "t": v.get("t")}

    def get_all(self) -> dict[str, Any]:
        return {k: {"value": v["v"], "updated": v.get("t")} for k, v in self.data.items()}

    @staticmethod
    def _size(value: Any) -> int:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    def set(self, key: str, value: Any) -> dict[str, Any]:
        if key not in ALLOWED_KEYS:
            raise ValueError(f"nieznany klucz „{key}” (dozwolone: {', '.join(ALLOWED_KEYS)})")
        try:
            size = self._size(value)
        except (TypeError, ValueError) as err:
            raise ValueError(f"wartość nie jest poprawnym JSON: {err}") from err
        if size > MAX_VALUE_BYTES:
            raise ValueError(f"wartość za duża ({size // 1024} KB > {MAX_VALUE_BYTES // 1024} KB)")
        others = sum(self._size(v["v"]) for k, v in self.data.items() if k != key)
        if others + size > MAX_TOTAL_BYTES:
            raise ValueError("magazyn Diagnostyki jest pełny — usuń stare wpisy")
        ts = dt_util.now().isoformat()
        self.data[key] = {"v": value, "t": ts}
        self._store.request_save(lambda: dict(self.data))
        return {"key": key, "updated": ts, "bytes": size}

    def delete(self, key: str) -> bool:
        if key in self.data:
            self.data.pop(key)
            self._store.request_save(lambda: dict(self.data))
            return True
        return False
