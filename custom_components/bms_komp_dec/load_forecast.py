"""Prognoza zużycia domu (dziennie, kWh) dla EMS komp-dec.

v2 — wszystkie ulepszenia:
  • outliery MAD (3 × 1.4826 × MAD)
  • EWMA (α=0.3) zamiast prostej średniej
  • adaptacyjne wagi tygodniowe (0.5 / 0.7 zależnie od rozrzutu)
  • korekta HDD/CDD (auto-dopasowanie z historii temperatur)
  • profil godzinowy (24h) — z próbkowania mocy co 30s
  • korekta dnia bieżącego (ekstrapolacja wg profilu)
  • przedział ufności ±1.5σ
  • walidacja MAPE z 14 dni
  • override przez number.bms_load_forecast_override
  • prognoza 7-dniowa
  • sezonowość (365 dni backfill, miesięczne czynniki)
  • dni specjalne (binary_sensor.workday)
  • min. 5 dni historii przed prognozą
  • ochrona północy + retencja + sanity check profilu
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .helpers import ThrottledStore
from .holidays_pl import polish_holidays

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "bms_komp_dec_load_history"
STORAGE_VERSION = 1
KEEP_DAYS = 60            # profile godzinowe
KEEP_DAYS_DAILY = 400     # sumy dzienne i temperatury (potrzebne do sezonowości)
MODEL_WINDOW_DAYS = 60    # okno historii dla bazy prognozy / MAD / sigma
BACKFILL_DAYS = 365
MIN_VALID_KWH = 0.2
MAX_VALID_KWH = 500.0
MIN_HISTORY_FOR_FORECAST = 5
MAD_K = 3.0
EWMA_ALPHA = 0.3
EWMA_ALPHA_FAST = 0.6      # gdy dwa ostatnie dni odbiegają w tę samą stronę
PERSIST_THRESHOLD = 0.25
MIN_TYPED_HISTORY = 3     # min. dni danego typu (roboczy/wolny) dla modelu typowanego
BIAS_DAYS = 14
BIAS_MIN_SAMPLES = 6
BIAS_GAIN = 0.5
BIAS_MIN = 0.75
BIAS_MAX = 1.25
WEATHER_REFRESH_SEC = 1800
HDD_BASE = 18.0
CDD_BASE = 24.0
DEFAULT_HDD_COEF = 0.05
DEFAULT_CDD_COEF = 0.08
CONFIDENCE_SIGMA = 1.5
SAME_WEEKDAY_RANGE_DAYS = 35
SAME_WEEKDAY_SAMPLES = 4
SEASONAL_STRENGTH = 0.5
PROFILE_MIN_DAYS = 3
PROFILE_MAX_DAYS = 14
PROFILE_TYPED_MIN_DAYS = 4   # tyle dni danego typu (roboczy / wolny), by użyć osobnego profilu godzinowego
OVERRIDE_EID = "number.bms_load_forecast_override"


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _stdev(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    try:
        return statistics.stdev(vals)
    except statistics.StatisticsError:
        return 0.0


def _mad_filter(values: list[float], k: float = MAD_K) -> list[float]:
    if len(values) < 5:
        return list(values)
    try:
        med = statistics.median(values)
        mad = statistics.median([abs(v - med) for v in values])
    except statistics.StatisticsError:
        return list(values)
    if mad <= 0:
        return list(values)
    threshold = k * 1.4826 * mad
    return [v for v in values if abs(v - med) <= threshold]


class LoadForecaster:
    def __init__(self, hass: HomeAssistant, load_eid_getter: Callable[[], str | None]) -> None:
        self.hass = hass
        self._get_eid = load_eid_getter
        self._store = ThrottledStore(hass, STORAGE_VERSION, STORAGE_KEY, delay=60)
        self.days: dict[str, float] = {}
        self.profiles: dict[str, list[float]] = {}
        # prognoza z podziałem na duże urządzenia (ustawiane przez runtime): fn(forecaster, target, today) -> dict | None
        self.split_hook = None
        self.forecast_history: dict[str, float] = {}
        self.temperatures: dict[str, float] = {}
        self.seasonal_factors: dict[int, float] = {}
        self.hdd_coef: float = DEFAULT_HDD_COEF
        self.cdd_coef: float = DEFAULT_CDD_COEF
        self._loaded = False
        self._last_weather_fetch: float = 0.0
        self._weather_eid: str | None = None
        self._hourly_accum: list[float] = [0.0] * 24
        self._hourly_cov: list[float] = [0.0] * 24      # sekundy faktycznie zmierzone w danej godzinie
        self._hourly_last_sample: datetime | None = None
        self._hourly_sample_date: date | None = None
        self._load_power_eid_cache: str | None = None
        self._last_accum_save: float = 0.0

    # ---------------------------------------------------------------- I/O
    async def async_load(self) -> None:
        try:
            data = await self._store.async_load()
            if isinstance(data, dict):
                self._load_from_storage(data)
        except Exception as err:
            _LOGGER.warning("EMS forecast: błąd wczytywania: %s", err)
        self._loaded = True

        if len(self._valid_history_before(dt_util.now().date())) < 7:
            await self._async_backfill()
        if len(self.profiles) < PROFILE_MAX_DAYS:
            await self._async_backfill_profiles()

        self._fit_temperature_coefficients()
        self._compute_seasonal_factors()

    def _load_from_storage(self, data: dict) -> None:
        days = data.get("days")
        if isinstance(days, dict):
            for k, v in days.items():
                try:
                    self.days[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue

        profiles = data.get("profiles")
        if isinstance(profiles, dict):
            for k, v in profiles.items():
                if isinstance(v, list) and len(v) == 24:
                    try:
                        self.profiles[str(k)] = [float(x) for x in v]
                    except (TypeError, ValueError):
                        continue

        fh = data.get("forecast_history")
        if isinstance(fh, dict):
            for k, v in fh.items():
                try:
                    self.forecast_history[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue

        temps = data.get("temperatures")
        if isinstance(temps, dict):
            for k, v in temps.items():
                try:
                    self.temperatures[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue

        sf = data.get("seasonal_factors")
        if isinstance(sf, dict):
            for k, v in sf.items():
                try:
                    self.seasonal_factors[int(k)] = float(v)
                except (TypeError, ValueError):
                    continue

        acc = data.get("hourly_accum")
        if isinstance(acc, dict) and isinstance(acc.get("values"), list) and len(acc["values"]) == 24 and acc.get("date"):
            try:
                self._hourly_accum = [float(x) for x in acc["values"]]
                self._hourly_sample_date = date.fromisoformat(str(acc["date"]))
                cov = acc.get("cov")
                if isinstance(cov, list) and len(cov) == 24:
                    self._hourly_cov = [max(0.0, float(x)) for x in cov]
                else:   # zapis sprzed 0.6.6 nie znał pokrycia — zakładamy pełne godziny
                    self._hourly_cov = [3600.0] * 24
            except (TypeError, ValueError):
                self._hourly_accum = [0.0] * 24
                self._hourly_cov = [0.0] * 24
                self._hourly_sample_date = None

        if isinstance(data.get("hdd_coef"), (int, float)):
            self.hdd_coef = float(data["hdd_coef"])
        if isinstance(data.get("cdd_coef"), (int, float)):
            self.cdd_coef = float(data["cdd_coef"])

    def _schedule_save(self) -> None:
        self._store.request_save(
            lambda: {
                "days": self.days,
                "profiles": self.profiles,
                "forecast_history": self.forecast_history,
                "temperatures": self.temperatures,
                "seasonal_factors": {str(k): v for k, v in self.seasonal_factors.items()},
                "hdd_coef": self.hdd_coef,
                "cdd_coef": self.cdd_coef,
                "hourly_accum": {
                    "date": self._hourly_sample_date.isoformat() if self._hourly_sample_date else None,
                    "values": self._hourly_accum,
                    "cov": self._hourly_cov,
                },
            },
        )

    async def _async_backfill(self) -> None:
        eid = self._get_eid()
        if not eid:
            return
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import statistics_during_period

            now = dt_util.now()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=BACKFILL_DAYS)
            stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                dt_util.as_utc(start),
                dt_util.as_utc(now),
                {eid},
                "hour",
                None,
                {"state", "max"},
            )
            rows = stats.get(eid) or []
            by_day: dict[str, float] = {}
            for row in rows:
                raw_start = row.get("start")
                if isinstance(raw_start, (int, float)):
                    ts = raw_start / 1000 if raw_start > 1e11 else raw_start
                    st = datetime.fromtimestamp(ts, tz=timezone.utc)
                elif isinstance(raw_start, datetime):
                    st = raw_start
                else:
                    continue
                val = row.get("max")
                if val is None:
                    val = row.get("state")
                if val is None:
                    continue
                try:
                    v = float(val)
                except (TypeError, ValueError):
                    continue
                day = dt_util.as_local(st).date().isoformat()
                by_day[day] = max(by_day.get(day, 0.0), v)

            today = now.date().isoformat()
            added = 0
            for day, val in by_day.items():
                if day >= today or day in self.days:
                    continue
                if MIN_VALID_KWH <= val <= MAX_VALID_KWH:
                    self.days[day] = round(val, 2)
                    added += 1
            if added:
                _LOGGER.info("EMS forecast: dociągnięto %d dni historii z rekordera", added)
                self._schedule_save()
        except Exception as err:
            _LOGGER.warning("EMS forecast: backfill nieudany: %s", err)

    async def _async_backfill_profiles(self) -> None:
        """Profil godzinowy z długoterminowych statystyk rekordera (średnia moc na godzinę).

        Bez tego profil zbierał się tylko w pamięci i po każdym restarcie HA zaczynał od zera
        (panel pokazywał wiecznie "1/3 dni")."""
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import statistics_during_period

            now = dt_util.now()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=PROFILE_MAX_DAYS + 2)
            best: dict[str, list[float | None]] = {}
            for eid in ("sensor.bms_load_power", "sensor.inverter_load_power"):
                if not self.hass.states.get(eid):
                    continue
                stats = await get_instance(self.hass).async_add_executor_job(
                    statistics_during_period, self.hass, dt_util.as_utc(start), dt_util.as_utc(now),
                    {eid}, "hour", None, {"mean"},
                )
                by_day: dict[str, list[float | None]] = {}
                for row in stats.get(eid) or []:
                    raw_start = row.get("start")
                    if isinstance(raw_start, (int, float)):
                        ts = raw_start / 1000 if raw_start > 1e11 else raw_start
                        st = datetime.fromtimestamp(ts, tz=timezone.utc)
                    elif isinstance(raw_start, datetime):
                        st = raw_start
                    else:
                        continue
                    mean = row.get("mean")
                    if mean is None or mean < 0:
                        continue
                    loc = dt_util.as_local(st)
                    arr = by_day.setdefault(loc.date().isoformat(), [None] * 24)
                    arr[loc.hour] = float(mean)
                if len(by_day) > len(best):
                    best = by_day
            today = now.date().isoformat()
            added = 0
            for day, arr in best.items():
                if day >= today or day in self.profiles:
                    continue
                if sum(1 for v in arr if v is not None) < 20:
                    continue  # niepełny dzień
                vals = [v if v is not None else 0.0 for v in arr]
                total = sum(vals)
                if total <= 0:
                    continue
                self.profiles[day] = [round(v / total, 4) for v in vals]
                added += 1
            if added:
                _LOGGER.info("EMS forecast: odtworzono %d profili godzinowych z rekordera", added)
                self._schedule_save()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS forecast: backfill profili nieudany: %s", err)

    # ------------------------------------------------------- update (10 s)
    def update(self) -> None:
        if not self._loaded:
            return
        now = dt_util.now()
        today = now.date()
        today_key = today.isoformat()

        # Profil godzinowy próbkujemy niezależnie od dostępności licznika dziennego.
        self._sample_hourly_power(now)

        value = self._read_today_value()
        if value is None or value < 0 or value > MAX_VALID_KWH:
            return

        if now.hour == 0 and now.minute < 15:
            yesterday = self.days.get((today - timedelta(days=1)).isoformat())
            if yesterday and value > 0 and value >= yesterday - 0.01:
                return

        value = round(value, 2)
        if value > self.days.get(today_key, -1.0):
            self.days[today_key] = value
            self._schedule_save()

        if (now.timestamp() - self._last_weather_fetch) > WEATHER_REFRESH_SEC:
            self._last_weather_fetch = now.timestamp()
            try:
                self.hass.async_create_task(self._async_fetch_weather_forecast())
            except Exception:
                pass

        cutoff_short = (today - timedelta(days=KEEP_DAYS)).isoformat()
        cutoff_long = (today - timedelta(days=KEEP_DAYS_DAILY)).isoformat()
        for attr, cutoff in (("days", cutoff_long), ("temperatures", cutoff_long),
                             ("profiles", cutoff_short), ("forecast_history", cutoff_short)):
            d = getattr(self, attr)
            for k in list(d.keys()):
                if k < cutoff:
                    d.pop(k, None)

    def _read_today_value(self) -> float | None:
        eid = self._get_eid()
        if not eid:
            return None
        st = self.hass.states.get(eid)
        if not st or st.state in ("unknown", "unavailable", ""):
            return None
        try:
            return float(st.state)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------- profil godzinowy
    def _sample_hourly_power(self, now: datetime) -> None:
        today = now.date()

        if self._hourly_sample_date is None:
            self._hourly_sample_date = today
            self._hourly_accum = [0.0] * 24
            self._hourly_cov = [0.0] * 24
            self._hourly_last_sample = None
        elif self._hourly_sample_date < today:
            self._save_daily_profile()
            self._hourly_sample_date = today
            self._hourly_accum = [0.0] * 24
            self._hourly_cov = [0.0] * 24
            self._hourly_last_sample = None

        if self._hourly_last_sample and (now - self._hourly_last_sample).total_seconds() < 30:
            return

        power_eid = self._get_load_power_eid()
        if not power_eid:
            self._hourly_last_sample = now
            return

        st = self.hass.states.get(power_eid)
        if not st or st.state in ("unknown", "unavailable", ""):
            self._hourly_last_sample = now
            return

        try:
            power_w = float(st.state)
        except (TypeError, ValueError):
            self._hourly_last_sample = now
            return

        if power_w < 0 or power_w > 100000:
            self._hourly_last_sample = now
            return

        if self._hourly_last_sample:
            dt_sec = (now - self._hourly_last_sample).total_seconds()
            if 0 < dt_sec < 120:
                h = now.hour
                if 0 <= h < 24:
                    self._hourly_accum[h] += power_w * dt_sec / 3600000.0
                    self._hourly_cov[h] += dt_sec

        self._hourly_last_sample = now
        if (now.timestamp() - self._last_accum_save) > 600:
            self._last_accum_save = now.timestamp()
            self._schedule_save()

    def _save_daily_profile(self) -> None:
        if self._hourly_sample_date is None:
            return
        total = sum(self._hourly_accum)
        if total < MIN_VALID_KWH or total > MAX_VALID_KWH:
            return
        expected = self.days.get(self._hourly_sample_date.isoformat())
        if expected and expected > 0:
            ratio = total / expected
            if ratio < 0.6 or ratio > 1.5:
                _LOGGER.debug(
                    "EMS forecast: pomijam profil %s (ratio=%.2f)",
                    self._hourly_sample_date.isoformat(), ratio,
                )
                return
        normalized = [v / total for v in self._hourly_accum]
        s = sum(normalized)
        if s <= 0:
            return
        self.profiles[self._hourly_sample_date.isoformat()] = [round(v / s, 4) for v in normalized]
        self._schedule_save()

    def _get_load_power_eid(self) -> str | None:
        if self._load_power_eid_cache and self.hass.states.get(self._load_power_eid_cache):
            return self._load_power_eid_cache
        for eid in ("sensor.bms_load_power", "sensor.inverter_load_power", "sensor.inverter_load_power_l1"):
            if self.hass.states.get(eid):
                self._load_power_eid_cache = eid
                return eid
        return None

    def _average_profile(self, off_day: bool | None = None) -> list[float] | None:
        """Średni profil godzinowy (udziały 24 godzin, suma 1). off_day=True/False: tylko dni wolne / robocze,
        gdy jest ich co najmniej PROFILE_TYPED_MIN_DAYS — inaczej profil ze wszystkich dni."""
        keys = sorted(self.profiles.keys(), reverse=True)
        recent = keys[:PROFILE_MAX_DAYS]
        if off_day is not None:
            typed = []
            for k in keys:
                try:
                    if self._is_off_day(date.fromisoformat(k)) == off_day:
                        typed.append(k)
                except ValueError:
                    continue
            if len(typed) >= PROFILE_TYPED_MIN_DAYS:
                recent = typed[:PROFILE_MAX_DAYS]
        if len(recent) < PROFILE_MIN_DAYS:
            return None
        avg = [0.0] * 24
        for k in recent:
            prof = self.profiles[k]
            if len(prof) == 24:
                for i in range(24):
                    avg[i] += prof[i]
        total = sum(avg)
        if total <= 0:
            return None
        return [v / total for v in avg]

    def _fraction_of_day_elapsed(self, hour: int) -> float:
        avg = self._average_profile(self._is_off_day(dt_util.now().date()))
        if avg is None:
            return (hour + 0.5) / 24.0
        hour = max(0, min(23, hour))
        return sum(avg[: hour + 1])

    # ----------------------------------------------------------- pogoda
    def _find_weather_eid(self) -> str | None:
        if self._weather_eid and self.hass.states.get(self._weather_eid):
            return self._weather_eid
        try:
            for eid in self.hass.states.async_entity_ids("weather"):
                self._weather_eid = eid
                return eid
        except Exception:
            pass
        return None

    def _extract_forecast(self, res: Any, eid: str) -> list | None:
        if not res:
            return None
        data: Any = res
        if isinstance(data, dict) and "response" in data and isinstance(data["response"], dict):
            data = data["response"]
        if not isinstance(data, dict):
            return None
        if eid in data and isinstance(data[eid], dict):
            fc = data[eid].get("forecast")
            if isinstance(fc, list):
                return fc
        fc = data.get("forecast")
        if isinstance(fc, list):
            return fc
        return None

    async def _async_fetch_weather_forecast(self) -> None:
        weather_eid = self._find_weather_eid()
        if not weather_eid:
            return

        fc: list | None = None
        try:
            res = await self.hass.services.async_call(
                "weather", "get_forecasts",
                {"entity_id": weather_eid, "type": "daily"},
                blocking=True, return_response=True,
            )
            fc = self._extract_forecast(res, weather_eid)
        except Exception:
            pass

        if not fc:
            try:
                res = await self.hass.services.async_call(
                    "weather", "get_forecast",
                    {"entity_id": weather_eid, "type": "daily"},
                    blocking=True, return_response=True,
                )
                fc = self._extract_forecast(res, weather_eid)
            except Exception:
                fc = None

        if not fc:
            st = self.hass.states.get(weather_eid)
            if st and isinstance(st.attributes.get("forecast"), list):
                fc = st.attributes["forecast"]

        if not isinstance(fc, list) or not fc:
            return

        updated = 0
        for day_data in fc[:8]:
            if not isinstance(day_data, dict):
                continue
            dt_str = day_data.get("datetime")
            if not dt_str:
                continue
            try:
                d = dt_util.parse_datetime(str(dt_str))
                if d is None:
                    continue
                d_date = dt_util.as_local(d).date()
            except Exception:
                continue
            temp = day_data.get("temperature")
            templow = day_data.get("templow")
            if temp is None and templow is None:
                continue
            try:
                if temp is not None and templow is not None:
                    avg = (float(temp) + float(templow)) / 2.0
                elif temp is not None:
                    avg = float(temp)
                else:
                    avg = float(templow)
            except (TypeError, ValueError):
                continue
            self.temperatures[d_date.isoformat()] = round(avg, 1)
            updated += 1
        if updated:
            self._schedule_save()

    # ------------------------------------------ dopasowanie współczynników
    def _fit_temperature_coefficients(self) -> None:
        data: list[tuple[float, float]] = []
        for d_str, temp in self.temperatures.items():
            if d_str in self.days:
                data.append((temp, self.days[d_str]))
        if len(data) < 14:
            return

        mild = [y for t, y in data if CDD_BASE >= t >= HDD_BASE]
        baseline = _mean(mild) if mild else _mean([y for t, y in data])
        if baseline <= 0:
            return

        winter = [(t, y) for t, y in data if t < HDD_BASE]
        summer = [(t, y) for t, y in data if t > CDD_BASE]

        if len(winter) >= 7:
            hdds = [HDD_BASE - t for t, y in winter]
            ratios = [y / baseline for t, y in winter]
            mean_hdd = _mean(hdds)
            mean_ratio = _mean(ratios)
            if mean_hdd > 0:
                coef = max(0.0, min(0.5, (mean_ratio - 1.0) / mean_hdd))
                self.hdd_coef = coef

        if len(summer) >= 3:
            cdds = [t - CDD_BASE for t, y in summer]
            ratios = [y / baseline for t, y in summer]
            mean_cdd = _mean(cdds)
            mean_ratio = _mean(ratios)
            if mean_cdd > 0:
                coef = max(0.0, min(0.5, (mean_ratio - 1.0) / mean_cdd))
                self.cdd_coef = coef

    def _compute_seasonal_factors(self) -> None:
        month_vals: dict[int, list[float]] = {}
        for d_str, val in self.days.items():
            if not (MIN_VALID_KWH <= val <= MAX_VALID_KWH):
                continue
            try:
                d = date.fromisoformat(d_str)
            except ValueError:
                continue
            month_vals.setdefault(d.month, []).append(val)

        if len(month_vals) < 3:
            return

        overall = _mean([v for vals in month_vals.values() for v in vals])
        if overall <= 0:
            return

        self.seasonal_factors = {
            m: _mean(vals) / overall
            for m, vals in month_vals.items() if len(vals) >= 3
        }

    # ----------------------------------------------------------- historia
    def _valid_history_before(self, cutoff: date) -> dict[date, float]:
        out: dict[date, float] = {}
        for k, v in self.days.items():
            try:
                d = date.fromisoformat(k)
            except ValueError:
                continue
            if d < cutoff and MIN_VALID_KWH <= v <= MAX_VALID_KWH:
                out[d] = v
        return out

    # ------------------------------------------------------------ prognoza
    def _is_off_day(self, d: date) -> bool:
        """Dzień wolny: weekend lub polskie święto ustawowe."""
        if d.weekday() >= 5:
            return True
        try:
            return d in polish_holidays(d.year)
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _ewma(series: list[float], alpha: float) -> float:
        e = series[0]
        for v in series[1:]:
            e = alpha * v + (1 - alpha) * e
        return e

    def _adaptive_ewma(self, series: list[float]) -> float:
        """EWMA; gdy dwa ostatnie dni odbiegają w tę samą stronę o >25% — szybsza reakcja."""
        alpha = EWMA_ALPHA
        if len(series) >= 5:
            prior = self._ewma(series[:-2], EWMA_ALPHA)
            if prior > 0:
                devs = [(v - prior) / prior for v in series[-2:]]
                if (all(x > 0 for x in devs) or all(x < 0 for x in devs)) and min(abs(x) for x in devs) > PERSIST_THRESHOLD:
                    alpha = EWMA_ALPHA_FAST
        return self._ewma(series, alpha)

    def _model_core(self, target: date, today: date) -> float | None:
        """Model bazowy: typ dnia (roboczy / wolny), EWMA adaptacyjny, ten sam dzień tygodnia,
        temperatura i sezon. Bez korekty obciążenia i bez korekty „na żywo”."""
        cutoff = min(target, today)
        window_start = cutoff - timedelta(days=MODEL_WINDOW_DAYS)
        hist = {
            d: v for d, v in self._valid_history_before(cutoff).items()
            if d >= window_start
        }
        if len(hist) < MIN_HISTORY_FOR_FORECAST:
            return None

        off = self._is_off_day(target) or self._is_special_holiday(target)
        typed = {d: v for d, v in hist.items() if self._is_off_day(d) == off}
        if len(typed) < MIN_TYPED_HISTORY:
            typed = dict(hist)   # za mało dni tego typu — model ogólny

        vals = list(typed.values())
        if len(vals) >= 5:
            try:
                med = statistics.median(vals)
                mad = statistics.median([abs(v - med) for v in vals])
                if mad > 0:
                    threshold = MAD_K * 1.4826 * mad
                    cleaned = {d: v for d, v in typed.items() if abs(v - med) <= threshold}
                    if len(cleaned) >= MIN_TYPED_HISTORY:
                        typed = cleaned
            except statistics.StatisticsError:
                pass

        ordered = sorted(typed.keys(), reverse=True)
        recent = [typed[d] for d in ordered[:7]]
        base = self._adaptive_ewma(list(reversed(recent))) if recent else _mean(list(typed.values()))

        same = [
            d for d in ordered
            if d.weekday() == target.weekday()
            and (cutoff - d).days <= SAME_WEEKDAY_RANGE_DAYS
        ][:SAME_WEEKDAY_SAMPLES]

        wd: float | None = None
        wd_spread = 0.0
        if len(same) >= 2:
            weights = [4, 3, 2, 1][: len(same)]
            same_vals = [typed[d] for d in same]
            wd = sum(v * w for v, w in zip(same_vals, weights)) / sum(weights)
            wd_spread = _stdev(same_vals)

        base_spread = _stdev(recent) if len(recent) >= 2 else 0.0

        if wd is not None:
            w_wd = 0.7 if wd_spread <= base_spread else 0.5
            result = w_wd * wd + (1 - w_wd) * base
        else:
            result = base

        # Poprawki temperatury i sezonu WZGLĘDEM dni, z których policzono bazę: ostatnie dni już zawierają
        # zimno / pórę roku, więc mnożenie przez czynnik liczony od „ciepłego” poziomu liczyło je drugi raz
        # (listopad: prognoza zawyżona o kilkadziesiąt procent).
        ref = list(ordered[:7]) + [d for d in same if d not in ordered[:7]]
        result = self._apply_temperature_correction(target, result, ref)
        result = self._apply_seasonal_correction(target, result, ref)
        return result

    def _bias_factor(self, today: date) -> float:
        """Samokorekta: mediana (rzeczywiste / model liczony wstecz) z 14 dni, połowa różnicy, ±25%."""
        sig = (today.isoformat(), tuple(
            round(self.days.get((today - timedelta(days=i)).isoformat(), 0.0), 1) for i in range(1, BIAS_DAYS + 1)
        ))
        cached = getattr(self, "_bias_cache", None)
        if cached and cached[0] == sig:
            return cached[1]
        ratios: list[float] = []
        for i in range(1, BIAS_DAYS + 1):
            d = today - timedelta(days=i)
            actual = self.days.get(d.isoformat())
            if not actual or actual < MIN_VALID_KWH:
                continue
            pred = self._model_core(d, today)
            if pred and pred > 0:
                ratios.append(actual / pred)
        factor = 1.0
        if len(ratios) >= BIAS_MIN_SAMPLES:
            med = statistics.median(ratios)
            factor = min(BIAS_MAX, max(BIAS_MIN, 1.0 + BIAS_GAIN * (med - 1.0)))
        self._bias_cache = (sig, round(factor, 4))
        return round(factor, 4)

    def predict(self, target: date, today: date, live: bool = True) -> float | None:
        if target == today + timedelta(days=1):
            ov_st = self.hass.states.get(OVERRIDE_EID)
            if ov_st and ov_st.state not in ("unknown", "unavailable", ""):
                try:
                    ov = float(ov_st.state)
                    if ov > 0:
                        return round(ov, 2)
                except (TypeError, ValueError):
                    pass

        result = self._model_core(target, today)
        if result is None:
            return None
        if target >= today:
            result *= self._bias_factor(today)

        if live and target == today:
            actual_so_far = self.days.get(today.isoformat())
            if actual_so_far and actual_so_far > 0:
                now = dt_util.now()
                frac_done = self._fraction_of_day_elapsed(now.hour)
                if frac_done and frac_done > 0.1:
                    extrapolated = actual_so_far / frac_done
                    blend = min(0.9, frac_done)
                    result = blend * extrapolated + (1 - blend) * result

        return round(max(0.0, result), 2)

    def _is_special_holiday(self, target: date) -> bool:
        if target != dt_util.now().date():
            return False
        try:
            for eid in self.hass.states.async_entity_ids("binary_sensor"):
                if "workday" in eid.lower():
                    st = self.hass.states.get(eid)
                    if st and st.state in ("on", "off"):
                        return st.state == "off"
        except Exception:
            pass
        return False

    def _temp_factor(self, d: date) -> float | None:
        temp = self.temperatures.get(d.isoformat())
        if temp is None:
            return None
        hdd = max(0.0, HDD_BASE - temp)
        cdd = max(0.0, temp - CDD_BASE)
        return 1.0 + self.hdd_coef * hdd + self.cdd_coef * cdd

    def _apply_temperature_correction(self, target: date, base: float, ref: list[date] | None = None) -> float:
        """Poprawka temperaturowa względem średniego czynnika dni bazowych (ref). Bez temperatur dni bazowych —
        bez poprawki (nie wiadomo, od jakiego poziomu liczyć)."""
        ft = self._temp_factor(target)
        if ft is None:
            return base
        refs = [f for f in (self._temp_factor(d) for d in (ref or [])) if f is not None]
        if not refs:
            return base
        fr = _mean(refs)
        return base * (ft / fr) if fr > 0 else base

    def _apply_seasonal_correction(self, target: date, base: float, ref: list[date] | None = None) -> float:
        """Poprawka sezonowa względem miesięcy dni bazowych — zmienia wynik tylko na przełomie miesięcy / dla dalszych dni."""
        if not self.seasonal_factors:
            return base
        ft = self.seasonal_factors.get(target.month)
        if ft is None:
            return base
        refs = [self.seasonal_factors[d.month] for d in (ref or []) if d.month in self.seasonal_factors]
        if not refs:
            return base
        fr = _mean(refs)
        st = 1.0 + SEASONAL_STRENGTH * (ft - 1.0)
        sr = 1.0 + SEASONAL_STRENGTH * (fr - 1.0)
        return base * (st / sr) if sr > 0 else base

    # --------------------------------------------------------- metryki
    def _compute_mape(self, days_back: int = 14) -> float | None:
        errors: list[float] = []
        today = dt_util.now().date()
        for i in range(1, days_back + 1):
            d = today - timedelta(days=i)
            d_str = d.isoformat()
            actual = self.days.get(d_str)
            predicted = self.forecast_history.get(d_str)
            if actual and predicted and actual > 0:
                errors.append(abs(actual - predicted) / actual)
        if not errors:
            return None
        return round(_mean(errors) * 100, 1)

    def _confidence_interval(self, forecast: float | None, target: date | None = None) -> dict | None:
        if forecast is None:
            return None
        today = dt_util.now().date()
        window_start = today - timedelta(days=MODEL_WINDOW_DAYS)
        hist = {d: v for d, v in self._valid_history_before(today).items() if d >= window_start}
        if target is not None:
            off = self._is_off_day(target)
            typed = {d: v for d, v in hist.items() if self._is_off_day(d) == off}
            if len(typed) >= 4:
                hist = typed
        if len(hist) < 3:
            return None
        vals = _mad_filter(list(hist.values()))
        sigma = _stdev(vals) if len(vals) >= 2 else 0.0
        margin = CONFIDENCE_SIGMA * sigma
        return {
            "low": round(max(0.0, forecast - margin), 2),
            "high": round(forecast + margin, 2),
            "sigma": round(sigma, 2),
        }

    def _hourly_forecast(self, total_kwh: float | None, d: date | None = None) -> list[float] | None:
        if total_kwh is None:
            return None
        avg = self._average_profile(None if d is None else self._is_off_day(d))
        if avg is None:
            return None
        return [round(avg[i] * total_kwh, 2) for i in range(24)]

    def _remaining_today(self, now: datetime, nowcast: float | None, actual: float | None) -> tuple[float | None, list[float | None] | None]:
        """Ile dom zużyje jeszcze DZIŚ (prognoza bieżąca z tempem dnia − zużycie dotychczas) i rozkład na godziny
        wg profilu dnia (None dla godzin minionych; bieżąca godzina proporcjonalnie do pozostałych minut)."""
        if nowcast is None:
            return None, None
        remaining = max(0.0, float(nowcast) - float(actual or 0.0))
        avg = self._average_profile(self._is_off_day(now.date()))
        if avg is None:
            avg = [1.0 / 24.0] * 24
        w = [0.0] * 24
        for h in range(now.hour, 24):
            w[h] = avg[h] * ((60 - now.minute) / 60.0 if h == now.hour else 1.0)
        tot = sum(w)
        if tot <= 0:
            return round(remaining, 2), None
        return round(remaining, 2), [None if h < now.hour else round(remaining * w[h] / tot, 3) for h in range(24)]

    def _hourly_today(self, now: datetime) -> list[float | None] | None:
        """Zużycie dziś w kWh dla zakończonych godzin; None dla godziny bieżącej, przyszłych
        oraz tych, w których pomiar obejmował <80% czasu (np. restart HA) — żeby nie zaniżać wyniku."""
        if self._hourly_sample_date != now.date():
            return None
        out: list[float | None] = []
        for h in range(24):
            cov = self._hourly_cov[h]
            ok = h < now.hour and cov >= 0.8 * 3600.0
            val = max(0.0, self._hourly_accum[h])
            if cov > 1.5 * 3600.0:      # jesienna zmiana czasu: godzina 02:00 wystąpiła dwa razy → średnia z obu
                val *= 3600.0 / cov
            out.append(round(val, 3) if ok else None)
        return out if any(v is not None for v in out) else None

    # -------------------------------------------------------- publiczny
    def as_dict(self) -> dict[str, Any]:
        today = dt_util.now().date()
        items = []
        for offset, label in ((-1, "Wczoraj"), (0, "Dziś"), (1, "Jutro")):
            d = today + timedelta(days=offset)
            actual = None if offset == 1 else self.days.get(d.isoformat())
            item: dict[str, Any] = {
                "date": d.isoformat(),
                "label": label,
                "actual": None if actual is None else round(actual, 2),
            }
            if offset == 1:
                item["forecast"] = self.predict(d, today)
            else:
                # Prognoza „wydana” dzień wcześniej (zapisana jako prognoza na jutro) — stała
                # w ciągu dnia i po północy. Brak wpisu (np. pierwsza doba) → model bez korekty na żywo.
                issued = self.forecast_history.get(d.isoformat())
                item["forecast"] = issued if issued is not None else self.predict(d, today, live=False)
                item["forecast_source"] = "issued" if issued is not None else "model"
                if offset == 0:
                    item["nowcast"] = self.predict(d, today)   # tempo dnia: model + zużycie dotychczas
            items.append(item)

        tomorrow = today + timedelta(days=1)
        split = None
        if self.split_hook is not None:
            try:
                split = self.split_hook(self, tomorrow, today)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("EMS: prognoza z podziałem na urządzenia nieudana: %s", err)
                split = None
            ov_st = self.hass.states.get(OVERRIDE_EID)
            try:
                ov = float(ov_st.state) if ov_st is not None else 0.0
            except (TypeError, ValueError):
                ov = 0.0
            if split and split.get("use") and isinstance(split.get("total"), (int, float)) and not ov > 0:
                items[2]["forecast"] = round(float(split["total"]), 2)
                items[2]["forecast_source"] = "devices"
        tomorrow_fc = items[2]["forecast"]
        if tomorrow_fc is not None:
            key = tomorrow.isoformat()
            if self.forecast_history.get(key) != tomorrow_fc:
                self.forecast_history[key] = tomorrow_fc
                self._schedule_save()

        rem_kwh, rem_h = self._remaining_today(dt_util.now(), items[1].get("nowcast"), items[1].get("actual"))

        forecast_7d = []
        for i in range(1, 8):
            d = today + timedelta(days=i)
            forecast_7d.append({
                "date": d.isoformat(),
                "forecast": self.predict(d, today),
            })

        history_14d = []
        for i in range(1, 15):
            d = today - timedelta(days=i)
            key = d.isoformat()
            actual = self.days.get(key)
            issued = self.forecast_history.get(key)
            try:
                from .holidays_pl import polish_holidays
                hol = polish_holidays(d.year).get(d)
            except Exception:  # noqa: BLE001
                hol = None
            history_14d.append({
                "date": key,
                "weekday": d.weekday(),
                "holiday": hol,
                "actual": None if actual is None else round(actual, 2),
                "issued": issued,
                "model": self.predict(d, today, live=False),
                "temp": self.temperatures.get(key),
            })

        return {
            "days": items,
            "history_14d": history_14d,
            "tomorrow_forecast": tomorrow_fc,
            "history_days": len(self._valid_history_before(today)),
            "forecast_7d": forecast_7d,
            "mape_14d": self._compute_mape(),
            "confidence_interval": self._confidence_interval(tomorrow_fc, tomorrow),
            "forecast_bias": self._bias_factor(today),
            "forecast_split": split,
            "hourly_forecast": self._hourly_forecast(tomorrow_fc, tomorrow),
            "hourly_forecast_today": self._hourly_forecast(items[1]["forecast"], today),   # profil × prognoza wydana na dziś
            "remaining_today": rem_kwh,                 # ile jeszcze dziś (prognoza bieżąca − zużycie dotychczas)
            "hourly_remaining_today": rem_h,            # to samo na godziny (planer: godziny do północy)
            "hourly_today": self._hourly_today(dt_util.now()),
            "hourly_today_hour": dt_util.now().hour,
            "temperature_correction": {
                "hdd_coef": round(self.hdd_coef, 4),
                "cdd_coef": round(self.cdd_coef, 4),
                "days_with_temp": len(self.temperatures),
            },
            "seasonal_factors": {str(k): round(v, 3) for k, v in self.seasonal_factors.items()},
            "profiles_days": len(self.profiles),
        }