"""Prognoza PV niezależna od integracji: Solcast albo Forecast.Solar.

Solcast podaje prognozę godzinową w atrybutach encji (detailedHourly / detailedForecast). Forecast.Solar ma
w encjach tylko sumy dzienne, a dane godzinowe udostępnia przez platformę „energy” Home Assistanta
(ta sama funkcja, z której korzysta panel Energia). Tu oba źródła są sprowadzone do jednej postaci:
{'YYYY-MM-DD': [24 wartości kWh/h]} oraz sumy dziennej w kWh.

Kilka wpisów Forecast.Solar (kilka połaci) jest sumowanych.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

FS_DOMAIN = "forecast_solar"
FS_REFRESH_S = 600            # Forecast.Solar odświeża dane co 30–60 min; 10 min wystarczy
SOLCAST_DAY_ENTITIES = [      # (EN, PL) — dni 3–7 tylko Solcast
    ("sensor.solcast_pv_forecast_forecast_today", "sensor.solcast_pv_forecast_prognoza_na_dzisiaj"),
    ("sensor.solcast_pv_forecast_forecast_tomorrow", "sensor.solcast_pv_forecast_prognoza_na_jutro"),
    ("sensor.solcast_pv_forecast_forecast_day_3", "sensor.solcast_pv_forecast_prognoza_na_dzien_3"),
    ("sensor.solcast_pv_forecast_forecast_day_4", "sensor.solcast_pv_forecast_prognoza_na_dzien_4"),
    ("sensor.solcast_pv_forecast_forecast_day_5", "sensor.solcast_pv_forecast_prognoza_na_dzien_5"),
    ("sensor.solcast_pv_forecast_forecast_day_6", "sensor.solcast_pv_forecast_prognoza_na_dzien_6"),
    ("sensor.solcast_pv_forecast_forecast_day_7", "sensor.solcast_pv_forecast_prognoza_na_dzien_7"),
]
_ENERGY_TO_KWH = {"kwh": 1.0, "wh": 0.001, "mwh": 1000.0}


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def state_kwh(hass: HomeAssistant, eid: str | None) -> float | None:
    """Stan encji energii w kWh (przeliczenie z Wh / MWh wg jednostki encji)."""
    st = hass.states.get(eid) if eid else None
    if not st or st.state in ("unknown", "unavailable", ""):
        return None
    try:
        val = float(st.state)
    except (TypeError, ValueError):
        return None
    unit = str((st.attributes or {}).get("unit_of_measurement") or "kWh").strip().lower()
    val *= _ENERGY_TO_KWH.get(unit, 1.0)
    return val if math.isfinite(val) and val >= 0 else None


def solcast_hourly(hass: HomeAssistant, eid: str | None, target: date) -> list[float | None] | None:
    """24 wartości kWh/h dla dnia target z atrybutów Solcast (moc średnia w okresie; okresy 30-min uśredniane)."""
    st = hass.states.get(eid) if eid else None
    if not st:
        return None
    attrs = st.attributes or {}
    arr = attrs.get("detailedHourly") or attrs.get("detailedForecast") or attrs.get("forecast")
    if not isinstance(arr, list):
        return None
    sums = [0.0] * 24
    counts = [0] * 24
    for item in arr:
        if not isinstance(item, dict):
            continue
        ps = item.get("period_start") or item.get("datetime")
        if not ps:
            continue
        try:
            dt = dt_util.parse_datetime(str(ps))
            if dt is None:
                continue
            dt = dt_util.as_local(dt)
            if dt.date() != target:
                continue
            v = item.get("pv_estimate")
            if v is None:
                v = item.get("estimate")
            if v is None:
                v = item.get("power")
            if v is None:
                continue
            fv = float(v)
            if not math.isfinite(fv):
                continue
            sums[dt.hour] += fv
            counts[dt.hour] += 1
        except (ValueError, TypeError):
            continue
    hourly: list[float | None] = [(sums[h] / counts[h]) if counts[h] else None for h in range(24)]
    return hourly if any(v is not None for v in hourly) else None


class PvForecast:
    """Wspólne źródło prognozy PV dla planera, rezerwy i karty."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._fs: dict[str, list[float]] = {}
        self._fs_at = 0.0
        self._fs_entries = 0
        self.fs_error: str | None = None

    # ------------------------------------------------------------- Forecast.Solar
    def _fs_loaded_entries(self) -> list:
        try:
            entries = self.hass.config_entries.async_entries(FS_DOMAIN)
        except Exception:  # noqa: BLE001
            return []
        out = []
        for e in entries:
            st = getattr(getattr(e, "state", None), "value", getattr(e, "state", None))
            if st in (None, "loaded"):
                out.append(e)
        return out

    def has_forecast_solar(self) -> bool:
        return bool(self._fs_loaded_entries())

    async def async_refresh(self, force: bool = False) -> None:
        """Pobiera prognozę godzinową ze wszystkich wpisów Forecast.Solar (co FS_REFRESH_S)."""
        now_ts = dt_util.now().timestamp()
        if not force and self._fs_at and now_ts - self._fs_at < FS_REFRESH_S:
            return
        entries = self._fs_loaded_entries()
        self._fs_at = now_ts
        if not entries:
            self._fs, self._fs_entries, self.fs_error = {}, 0, None
            return
        try:
            from homeassistant.components.forecast_solar.energy import async_get_solar_forecast
        except Exception as err:  # noqa: BLE001
            self.fs_error = f"brak platformy energy Forecast.Solar: {err}"
            return
        days: dict[str, list[float]] = {}
        used = 0
        for e in entries:
            try:
                res = await async_get_solar_forecast(self.hass, e.entry_id)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("EMS: Forecast.Solar %s: %s", e.entry_id, err)
                continue
            wh = (res or {}).get("wh_hours") if isinstance(res, dict) else None
            if not isinstance(wh, dict) or not wh:
                continue
            used += 1
            for ts, val in wh.items():
                try:
                    dt = ts if hasattr(ts, "tzinfo") else dt_util.parse_datetime(str(ts))
                    if dt is None or not _finite(val):
                        continue
                    dt = dt_util.as_local(dt)
                    days.setdefault(dt.date().isoformat(), [0.0] * 24)[dt.hour] += max(0.0, float(val)) / 1000.0
                except (TypeError, ValueError):
                    continue
        self._fs_entries = used
        self.fs_error = None if used else "Forecast.Solar nie zwrócił prognozy godzinowej"
        if used:
            self._fs = {k: [round(x, 4) for x in v] for k, v in days.items()}

    def fs_hourly(self, d: date) -> list[float | None] | None:
        arr = self._fs.get(d.isoformat())
        return list(arr) if arr and any(x > 0 for x in arr) else None

    def fs_daily(self, d: date) -> float | None:
        arr = self.fs_hourly(d)
        return round(sum(x or 0.0 for x in arr), 2) if arr else None

    def is_fs_entity(self, eid: str | None) -> bool:
        if not eid:
            return False
        try:
            from homeassistant.helpers import entity_registry as er
            ent = er.async_get(self.hass).async_get(eid)
            return bool(ent and ent.platform == FS_DOMAIN)
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------- wspólne API
    def hourly(self, eid: str | None, d: date) -> tuple[list[float | None] | None, str | None]:
        """(24 × kWh/h, źródło) dla dnia d: atrybuty Solcast skonfigurowanej encji, a gdy ich brak — Forecast.Solar."""
        arr = solcast_hourly(self.hass, eid, d)
        if arr:
            return arr, "Solcast"
        arr = self.fs_hourly(d)
        if arr:
            return arr, "Forecast.Solar"
        return None, None

    def daily_kwh(self, eid: str | None, d: date) -> float | None:
        """Suma dzienna (kWh): encja z konfiguracji (z przeliczeniem jednostki); dla Forecast.Solar — suma wszystkich
        połaci z prognozy godzinowej (encja jednego wpisu pokazuje tylko swoją połać)."""
        if self.is_fs_entity(eid) and self._fs_entries > 1:
            v = self.fs_daily(d)
            if v is not None:
                return v
        v = state_kwh(self.hass, eid)
        if v is None and self.is_fs_entity(eid):
            v = self.fs_daily(d)
        return v

    def source(self, eid: str | None) -> str | None:
        today = dt_util.now().date()
        return self.hourly(eid, today)[1] or self.hourly(eid, today + timedelta(days=1))[1] or (
            "Forecast.Solar" if self.is_fs_entity(eid) else ("Solcast" if eid and "solcast" in eid else None))

    def card_payload(self, eid_today: str | None, eid_tomorrow: str | None) -> dict[str, Any]:
        """Atrybuty dla karty: prognoza godzinowa dziś/jutro i sumy do 7 dni (ta sama, której używa planer)."""
        today = dt_util.now().date()
        out: dict[str, Any] = {"pv_forecast_source": self.source(eid_today)}
        for key, eid, off in (("pv_hourly_today", eid_today, 0), ("pv_hourly_tomorrow", eid_tomorrow, 1)):
            arr = self.hourly(eid, today + timedelta(days=off))[0]
            out[key] = [None if v is None else round(float(v), 3) for v in arr] if arr else None
        daily = []
        for i in range(7):
            d = today + timedelta(days=i)
            if i == 0:
                v = self.daily_kwh(eid_today, d)
            elif i == 1:
                v = self.daily_kwh(eid_tomorrow, d)
            else:
                v = None
                for cand in SOLCAST_DAY_ENTITIES[i]:
                    v = state_kwh(self.hass, cand)
                    if v is not None:
                        break
                if v is None:
                    v = self.fs_daily(d)
            daily.append({"date": d.isoformat(), "kwh": None if v is None else round(v, 2)})
        out["pv_daily"] = daily
        return out
