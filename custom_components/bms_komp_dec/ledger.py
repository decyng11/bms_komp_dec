"""Księga zysków/strat w PLN: energia wyeksportowana × RCE − energia zaimportowana × cena zakupu (funkcja 5)."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .helpers import ThrottledStore

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "bms_komp_dec_ledger"
KEEP_DAYS = 400
MAX_GAP_S = 120          # dłuższe przerwy w próbkowaniu nie są całkowane (restart, awaria)
MAX_POWER_W = 100000


def _empty_day() -> dict[str, float]:
    return {"export_kwh": 0.0, "import_kwh": 0.0, "revenue": 0.0, "cost": 0.0, "neg_export_kwh": 0.0}


class Ledger:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = ThrottledStore(hass, 1, STORAGE_KEY, delay=300)
        self.days: dict[str, dict[str, float]] = {}
        self._last_ts: datetime | None = None

    async def async_load(self) -> None:
        try:
            data = await self._store.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS ledger: błąd wczytywania: %s", err)
            return
        if isinstance(data, dict) and isinstance(data.get("days"), dict):
            for k, v in data["days"].items():
                if not isinstance(v, dict):
                    continue
                day = _empty_day()
                for f in day:
                    try:
                        day[f] = float(v.get(f, 0.0))
                    except (TypeError, ValueError):
                        pass
                self.days[str(k)] = day

    def update(self, now: datetime, grid_power_w: float | None,
               sell_price: float | None, buy_price: float | None) -> None:
        """grid_power_w > 0 = import z sieci, < 0 = eksport do sieci (jak w całej integracji)."""
        prev = self._last_ts
        self._last_ts = now
        if prev is None or grid_power_w is None:
            return
        dt_s = (now - prev).total_seconds()
        if dt_s <= 0 or dt_s > MAX_GAP_S:
            return
        if abs(grid_power_w) > MAX_POWER_W:
            return
        kwh = abs(grid_power_w) * dt_s / 3_600_000.0
        key = dt_util.as_local(now).date().isoformat()
        day = self.days.setdefault(key, _empty_day())
        if grid_power_w < 0:
            day["export_kwh"] += kwh
            if sell_price is not None:
                day["revenue"] += kwh * sell_price
                if sell_price < 0:
                    day["neg_export_kwh"] += kwh
        elif grid_power_w > 0:
            day["import_kwh"] += kwh
            if buy_price is not None:
                day["cost"] += kwh * buy_price
        self._store.request_save(self._data)
        self._prune(key)

    def _prune(self, today_key: str) -> None:
        if len(self.days) <= KEEP_DAYS + 5:
            return
        for k in sorted(self.days)[: len(self.days) - KEEP_DAYS]:
            self.days.pop(k, None)

    def _data(self) -> dict[str, Any]:
        return {"days": {k: {f: round(x, 5) for f, x in v.items()} for k, v in self.days.items()}}

    # ------------------------------------------------------------ agregaty
    @staticmethod
    def net(day: dict[str, float]) -> float:
        return day["revenue"] - day["cost"]

    def day_net(self, d: date) -> float:
        v = self.days.get(d.isoformat())
        return self.net(v) if v else 0.0

    def month_net(self, d: date) -> float:
        prefix = f"{d.year:04d}-{d.month:02d}-"
        return sum(self.net(v) for k, v in self.days.items() if k.startswith(prefix))

    def total_net(self) -> float:
        return sum(self.net(v) for v in self.days.values())

    def sums(self, d: date | None = None, scope: str = "day") -> dict[str, float]:
        """Sumy przychodu/kosztu/kWh dla dnia, miesiąca lub całej księgi (scope: day|month|total)."""
        if scope == "day":
            rows = [self.days.get(d.isoformat())] if d else []
        elif scope == "month" and d:
            prefix = f"{d.year:04d}-{d.month:02d}-"
            rows = [v for k, v in self.days.items() if k.startswith(prefix)]
        else:
            rows = list(self.days.values())
        out = _empty_day()
        for v in rows:
            if v:
                for f in out:
                    out[f] += v.get(f, 0.0)
        out["net"] = out["revenue"] - out["cost"]
        return {k: round(x, 4) for k, x in out.items()}

    def history(self, n: int = 31) -> list[dict[str, Any]]:
        out = []
        for k in sorted(self.days)[-n:]:
            v = self.days[k]
            out.append({
                "date": k,
                "net": round(self.net(v), 2),
                "revenue": round(v["revenue"], 2),
                "cost": round(v["cost"], 2),
                "export_kwh": round(v["export_kwh"], 2),
                "import_kwh": round(v["import_kwh"], 2),
                "neg_export_kwh": round(v["neg_export_kwh"], 2),
            })
        return out
