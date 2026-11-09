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

import math

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
# Domyślnie historia zużycia zbiera się od zera (bez importu z rekordera HA).
# Ustaw True, by przy pustej historii dociągnąć dane z recordera.
BACKFILL_FROM_RECORDER = False
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
# samostrojenie (0.9.3): co dobę wybór wariantu modelu na podstawie „prognoz wstecz” z własnej historii
TUNE_EVAL_DAYS = 30            # ile ostatnich dni ocenia wariant
TUNE_MIN_EVAL = 10             # tyle dni oceny trzeba, by w ogóle zmieniać parametry
TUNE_MIN_GAIN = 0.03           # wariant musi dać o ≥3% mniejszy średni błąd niż domyślny
DEFAULT_PARAMS = {"alpha": EWMA_ALPHA, "alpha_fast": EWMA_ALPHA_FAST, "wd_w": 0.7, "temp_scale": 1.0,
                  "bias_gain": BIAS_GAIN, "bias_max": BIAS_MAX - 1.0, "bias_days": BIAS_DAYS}
TUNE_CORE = [(a, wd, ts) for a in (0.3, 0.5) for wd in (0.7, 0.4, 0.0) for ts in (1.0, 1.5)]
TUNE_BIAS = [(0.5, 0.25, 14), (0.8, 0.4, 14), (0.8, 0.4, 7), (1.0, 0.5, 7), (0.0, 0.0, 14)]
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
STALE_UNTIL_HOUR = 6         # do tej godziny licznik dzienny może jeszcze pokazywać wynik wczorajszy (reset po północy)
DUP_EPS = 0.011              # dwa kolejne dni z tą samą wartością (do 0,01 kWh) = przepisany wynik poprzedniego dnia
PARTIAL_RATIO = 0.25         # dzień poniżej 25% mediany sąsiednich dni to najpewniej niepełne dane
SUSPECT_NEIGHBOUR_DAYS = 7
SUSPECT_MIN_NEIGHBOURS = 4
CYCLE_MIN_ROWS = 20          # pełny cykl licznika (~24 h) ma co najmniej tyle godzinowych wpisów w rekorderze
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


def suspect_days(days: dict[str, float], today: date | None = None) -> dict[str, str]:
    """Dni z sumą zużycia, której nie należy ufać: {data: "duplicate" | "partial"}.

    duplicate — ta sama wartość (do 0,01 kWh) co dzień wcześniej: licznik falownika resetuje się po północy (zegar
                falownika), a wczorajszy wynik został zapisany jako dzisiejszy. Zostaje pierwszy dzień z pary.
    partial   — poniżej 25% mediany sąsiednich dni (±7 dni, min. 4): niepełne dane (przerwa w pomiarze, start w ciągu dnia).
    Dzień bieżący (i późniejsze) nie jest oceniany — jeszcze trwa."""
    items: dict[date, float] = {}
    for k, v in (days or {}).items():
        try:
            d = date.fromisoformat(str(k))
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f and abs(f) != float("inf") and (today is None or d < today):
            items[d] = f
    flags: dict[str, str] = {}
    for d in sorted(items):
        prev = items.get(d - timedelta(days=1))
        if prev is None or items[d] <= 1.0 or abs(items[d] - prev) > DUP_EPS:
            continue
        # stała historia (np. te same wartości przez cały tydzień) to nie przepisany wynik: licznik rzeczywistego
        # zużycia nie daje identycznych sum przez wiele dni — oznaczamy tylko powtórzenie odstające od sąsiednich dni
        neigh = [items[o] for o in (d + timedelta(days=k) for k in range(-SUSPECT_NEIGHBOUR_DAYS, SUSPECT_NEIGHBOUR_DAYS + 1) if k)
                 if o in items and abs(items[o] - items[d]) > DUP_EPS]
        same = [o for o in (d + timedelta(days=k) for k in range(-SUSPECT_NEIGHBOUR_DAYS, SUSPECT_NEIGHBOUR_DAYS + 1) if k)
                if o in items and abs(items[o] - items[d]) <= DUP_EPS]
        if len(same) > 2 and len(same) >= len(neigh):      # większość okna to ta sama wartość → stała historia
            continue
        flags[d.isoformat()] = "duplicate"
    for d in sorted(items):
        if d.isoformat() in flags or items[d] < MIN_VALID_KWH:
            continue
        neigh = [items[o] for o in (d + timedelta(days=k) for k in range(-SUSPECT_NEIGHBOUR_DAYS, SUSPECT_NEIGHBOUR_DAYS + 1) if k)
                 if o in items and o.isoformat() not in flags and items[o] >= MIN_VALID_KWH]
        if len(neigh) >= SUSPECT_MIN_NEIGHBOURS and items[d] < PARTIAL_RATIO * statistics.median(neigh):
            flags[d.isoformat()] = "partial"
    return flags


def day_totals_from_rows(rows: list, tz) -> dict[str, float]:
    """Sumy dzienne z godzinowych wpisów rekordera licznika dziennego: [(początek godziny UTC, max w godzinie)].

    Licznik resetuje się o godzinie zegara falownika, nie koniecznie o północy lokalnej — liczenie „max w dobie
    lokalnej” przypisywało więc początkowi doby wynik poprzedniego dnia. Tu dzielimy wpisy na CYKLE licznika
    (spadek wartości = reset) i bierzemy tylko cykle pełne (zamknięte resetem z obu stron, ≥ 20 godzinowych wpisów);
    cykl dostaje datę lokalną swojego środka. Niepełne cykle (początek i koniec danych, przerwy) są pomijane."""
    clean = []
    for st, v in rows or []:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f and isinstance(st, datetime):
            clean.append((st, f))
    clean.sort(key=lambda r: r[0])
    segs: list[list] = []
    cur: list = []
    prev = None
    for st, v in clean:
        if prev is not None and v < prev * 0.5 and prev - v >= 1.0:
            segs.append(cur)
            cur = []
        cur.append((st, v))
        prev = v
    segs.append(cur)
    out: dict[str, float] = {}
    for seg in segs[1:-1]:                       # pierwszy cykl nie ma znanego początku, ostatni trwa
        if len(seg) < CYCLE_MIN_ROWS:
            continue
        first, last = seg[0][0], seg[-1][0]
        hours = (last - first).total_seconds() / 3600.0 + 1.0
        total = max(v for _, v in seg)
        if not (20.0 <= hours <= 28.0) or not (MIN_VALID_KWH <= total <= MAX_VALID_KWH):
            continue
        mid = first + (last + timedelta(hours=1) - first) / 2
        key = mid.astimezone(tz).date().isoformat()
        out[key] = round(max(out.get(key, 0.0), total), 2)
    return out


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
        self.params: dict[str, float] = dict(DEFAULT_PARAMS)
        self.tune: dict[str, Any] = {}
        self._maint_date: date | None = None
        self._loaded = False
        self._last_weather_fetch: float = 0.0
        self._weather_eid: str | None = None
        self._hourly_accum: list[float] = [0.0] * 24
        self._hourly_cov: list[float] = [0.0] * 24      # sekundy faktycznie zmierzone w danej godzinie
        self._hourly_last_sample: datetime | None = None
        self._hourly_sample_date: date | None = None
        self._load_power_eid_cache: str | None = None
        self._last_accum_save: float = 0.0
        self._ewma_kw: float | None = None      # wygładzone bieżące zużycie domu (stała czasowa ~15 min)
        self._ewma_at: datetime | None = None
        self._ewma_since: datetime | None = None

    # ---------------------------------------------------------------- I/O
    async def async_load(self) -> None:
        try:
            data = await self._store.async_load()
            if isinstance(data, dict):
                self._load_from_storage(data)
        except Exception as err:
            _LOGGER.warning("EMS forecast: błąd wczytywania: %s", err)
        self._loaded = True

        if BACKFILL_FROM_RECORDER:
            if len(self._valid_history_before(dt_util.now().date())) < 7:
                await self._async_backfill()
            if len(self.profiles) < PROFILE_MAX_DAYS:
                await self._async_backfill_profiles()

        self._fit_temperature_coefficients()
        self._compute_seasonal_factors()
        self._maintenance(dt_util.now(), force=True)

    # ------------------------------------------------- codzienne uczenie (0.9.3)
    def _maintenance(self, now: datetime, force: bool = False) -> None:
        """Raz na dobę (po 6:00, gdy wynik wczoraj jest już ostateczny) albo przy starcie: przelicza współczynniki
        temperatury i sezonu oraz wybiera wariant modelu na podstawie prognoz liczonych wstecz z własnej historii."""
        today = now.date()
        if self._maint_date == today or (not force and now.hour < STALE_UNTIL_HOUR):
            return
        self._maint_date = today
        try:
            self._fit_temperature_coefficients()
            self._compute_seasonal_factors()
            self._autotune(today)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Prognoza zużycia: codzienne uczenie nie powiodło się: %s", err)
        self._bias_cache = None
        self._schedule_save()

    def _backtest(self, today: date) -> list[tuple[tuple, float, float, int]] | None:
        """Średni błąd bezwzględny (kWh) i trafienia ±20% każdego wariantu na ostatnich dniach — prognoza dnia X liczona
        wyłącznie z danych sprzed X (jak naprawdę wydana)."""
        valid = self._valid_history_before(today)
        days = sorted(valid)
        eval_days = days[-TUNE_EVAL_DAYS:]
        if len(eval_days) < TUNE_MIN_EVAL:
            return None
        start = eval_days[0] - timedelta(days=14)
        series = [d for d in days if d >= start]
        saved = self.params
        out: list[tuple[tuple, float, float, int]] = []
        try:
            for a, wd, ts in TUNE_CORE:
                self.params = dict(saved, alpha=a, wd_w=wd, temp_scale=ts)
                core: dict[date, float] = {}
                for d in series:
                    v = self._model_core(d, d)
                    if v and v > 0:
                        core[d] = v
                for g, mx, nb in TUNE_BIAS:
                    errs: list[float] = []
                    hits = 0
                    for d in eval_days:
                        if d not in core:
                            continue
                        ratios = [valid[x] / core[x] for x in (d - timedelta(days=i) for i in range(1, nb + 1))
                                  if x in core and x in valid]
                        f = 1.0
                        if g > 0 and len(ratios) >= (BIAS_MIN_SAMPLES if nb >= 14 else 4):
                            f = min(1.0 + mx, max(1.0 - mx, 1.0 + g * (statistics.median(ratios) - 1.0)))
                        err = abs(core[d] * f - valid[d])
                        errs.append(err)
                        hits += 1 if err <= 0.2 * valid[d] else 0
                    if len(errs) >= TUNE_MIN_EVAL:
                        out.append(((a, wd, ts, g, mx, nb), _mean(errs), hits / len(errs), len(errs)))
        finally:
            self.params = saved
        return out or None

    @staticmethod
    def _variant_label(v: tuple) -> str:
        a, wd, ts, g, mx, nb = v
        parts = []
        if (g, mx, nb) != (0.5, 0.25, 14):
            parts.append("bez korekty błędu" if g <= 0 else f"szybsza korekta błędu ({nb} dni, waga {g:g}, do ±{mx * 100:.0f}%)")
        if a != 0.3:
            parts.append("większa waga ostatnich dni")
        if wd != 0.7:
            parts.append("bez wpływu tego samego dnia tygodnia" if wd <= 0 else "mniejszy wpływ tego samego dnia tygodnia")
        if ts != 1.0:
            parts.append("mocniejsza poprawka temperatury")
        return ", ".join(parts) or "standardowy"

    def _autotune(self, today: date) -> None:
        res = self._backtest(today)
        if not res:
            self.tune = {"at": today.isoformat(), "n": 0, "note": "za mało dni historii (min. 10 dni oceny)"}
            return
        dv = (0.3, 0.7, 1.0, 0.5, 0.25, 14)
        default = next((r for r in res if r[0] == dv), None)
        best = min(res, key=lambda r: r[1])
        if default is None:
            return
        use = best if (default[1] - best[1]) >= TUNE_MIN_GAIN * default[1] and best[1] < default[1] else default
        v = use[0]
        self.params = dict(DEFAULT_PARAMS, alpha=v[0], wd_w=v[1], temp_scale=v[2], bias_gain=v[3], bias_max=v[4], bias_days=v[5])
        self.tune = {"at": today.isoformat(), "n": use[3], "tried": len(res), "variant": self._variant_label(v),
                     "mae": round(use[1], 2), "mae_default": round(default[1], 2),
                     "hit": round(use[2] * 100), "hit_default": round(default[2] * 100)}
        _LOGGER.info("Prognoza zużycia: wariant „%s”, błąd %.2f kWh (standardowy %.2f), trafienia ±20%%: %d%% (std %d%%)",
                     self.tune["variant"], use[1], default[1], use[2] * 100, default[2] * 100)

    def clear_history(self) -> None:
        """Kasuje zebraną historię zużycia; model i prognoza startują od zera (wymagane ≥5 dni)."""
        self.days.clear()
        self.profiles.clear()
        self.forecast_history.clear()
        self.seasonal_factors = {}
        self.params = dict(DEFAULT_PARAMS)
        self.tune = {}
        self._hourly_accum = [0.0] * 24
        self._hourly_cov = [0.0] * 24
        self._hourly_last_sample = None
        self._hourly_sample_date = None
        self._ewma_kw = self._ewma_at = self._ewma_since = None
        self._fit_temperature_coefficients()
        self._schedule_save()

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
        pr = data.get("params")
        if isinstance(pr, dict):
            for k, dv in DEFAULT_PARAMS.items():
                if isinstance(pr.get(k), (int, float)):
                    self.params[k] = float(pr[k])
        if isinstance(data.get("tune"), dict):
            self.tune = data["tune"]

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
                "params": self.params,
                "tune": self.tune,
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
            series: list[tuple[datetime, float]] = []
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
                    series.append((st, float(val)))
                except (TypeError, ValueError):
                    continue
            by_day = day_totals_from_rows(series, now.tzinfo)

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
        self._maintenance(now)

        value = self._read_today_value()
        if value is None or value < 0 or value > MAX_VALID_KWH:
            return

        # Licznik dzienny falownika resetuje się o godzinie jego zegara, nie zawsze o północy lokalnej: do resetu
        # pokazuje jeszcze wynik WCZORAJSZY (i dalej rośnie). Taki odczyt dopisujemy do wczoraj, a nie do dziś —
        # inaczej dziś zostaje z wczorajszą wartością (dwa dni z tym samym wynikiem), bo realne zużycie rzadko ją przebija.
        if now.hour < STALE_UNTIL_HOUR and today_key not in self.days:
            ykey = (today - timedelta(days=1)).isoformat()
            yesterday = self.days.get(ykey)
            if yesterday and yesterday > 1.0 and value >= yesterday - DUP_EPS:
                if value > yesterday and value <= MAX_VALID_KWH:
                    self.days[ykey] = round(value, 2)
                    self._schedule_save()
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
                self._update_live(power_w / 1000.0, dt_sec, now)
                h = now.hour
                if 0 <= h < 24:
                    self._hourly_accum[h] += power_w * dt_sec / 3600000.0
                    self._hourly_cov[h] += dt_sec

        self._hourly_last_sample = now
        if (now.timestamp() - self._last_accum_save) > 600:
            self._last_accum_save = now.timestamp()
            self._schedule_save()

    def _update_live(self, kw: float, dt_sec: float, now: datetime) -> None:
        """Średnia krocząca zużycia (τ ≈ 15 min): pojedynczy skok (czajnik) ledwo ją rusza, dłuższa zmiana tak."""
        if self._ewma_kw is None or self._ewma_at is None or (now - self._ewma_at).total_seconds() > 300:
            self._ewma_kw, self._ewma_since = kw, now          # przerwa w danych — zaczynamy od nowa
        else:
            a = 1.0 - math.exp(-dt_sec / 900.0)
            self._ewma_kw += a * (kw - self._ewma_kw)
        self._ewma_at = now

    def live_load_kw(self, now: datetime) -> float | None:
        """Bieżące zużycie domu (kW, wygładzone) — tylko gdy mierzymy je ciągle od ≥ 10 min i odczyt jest świeży."""
        if self._ewma_kw is None or self._ewma_at is None or self._ewma_since is None:
            return None
        if (now - self._ewma_at).total_seconds() > 300 or (now - self._ewma_since).total_seconds() < 600:
            return None
        return float(self._ewma_kw)

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
        bad = self.suspects()
        for d_str, val in self.days.items():
            if d_str in bad or not (MIN_VALID_KWH <= val <= MAX_VALID_KWH):
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
    def suspects(self) -> dict[str, str]:
        """Podejrzane dni (patrz suspect_days) — przeliczane tylko po zmianie historii."""
        today = dt_util.now().date()
        sig = (today, len(self.days), round(sum(self.days.values()), 3))
        cached = getattr(self, "_suspect_cache", None)
        if cached and cached[0] == sig:
            return cached[1]
        flags = suspect_days(self.days, today)
        self._suspect_cache = (sig, flags)
        return flags

    def _valid_history_before(self, cutoff: date) -> dict[date, float]:
        out: dict[date, float] = {}
        bad = self.suspects()
        for k, v in self.days.items():
            if k in bad:
                continue
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
        base_a = float(self.params.get("alpha", EWMA_ALPHA))
        alpha = base_a
        if len(series) >= 5:
            prior = self._ewma(series[:-2], base_a)
            if prior > 0:
                devs = [(v - prior) / prior for v in series[-2:]]
                if (all(x > 0 for x in devs) or all(x < 0 for x in devs)) and min(abs(x) for x in devs) > PERSIST_THRESHOLD:
                    alpha = max(base_a, float(self.params.get("alpha_fast", EWMA_ALPHA_FAST)))
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
            wd_w = float(self.params.get("wd_w", 0.7))
            w_wd = wd_w if wd_spread <= base_spread else max(0.0, wd_w - 0.2)
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
        """Samokorekta: mediana (rzeczywiste / model liczony wstecz) z ostatnich dni, z wagą i sufitem z parametrów
        (domyślnie połowa różnicy, ±25%, 14 dni; samostrojenie może wybrać szybszy wariant)."""
        n_days = int(self.params.get("bias_days", BIAS_DAYS))
        gain = float(self.params.get("bias_gain", BIAS_GAIN))
        mx = float(self.params.get("bias_max", BIAS_MAX - 1.0))
        sig = (today.isoformat(), n_days, gain, mx, tuple(
            round(self.days.get((today - timedelta(days=i)).isoformat(), 0.0), 1) for i in range(1, n_days + 1)
        ))
        cached = getattr(self, "_bias_cache", None)
        if cached and cached[0] == sig:
            return cached[1]
        ratios: list[float] = []
        for i in range(1, n_days + 1):
            d = today - timedelta(days=i)
            actual = self.days.get(d.isoformat())
            if not actual or actual < MIN_VALID_KWH or d.isoformat() in self.suspects():
                continue
            pred = self._model_core(d, today)
            if pred and pred > 0:
                ratios.append(actual / pred)
        factor = 1.0
        if len(ratios) >= (BIAS_MIN_SAMPLES if n_days >= 14 else 4) and gain > 0:
            med = statistics.median(ratios)
            factor = min(1.0 + mx, max(1.0 - mx, 1.0 + gain * (med - 1.0)))
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
        k = float(self.params.get("temp_scale", 1.0))
        return 1.0 + k * (self.hdd_coef * hdd + self.cdd_coef * cdd)

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
            if actual and predicted and actual > 0 and d_str not in self.suspects():
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
            if actual is not None and offset < 0 and d.isoformat() in self.suspects():
                actual = None          # podejrzana suma (duplikat / niepełne dane) nie trafia na wykres „wczoraj”
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
                "suspect": self.suspects().get(key),      # "duplicate" | "partial" | None
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
            "tuning": dict(self.tune),
        }