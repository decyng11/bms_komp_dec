"""Inteligentny optymalizator harmonogramu EMS."""
from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

try:  # wschód/zachód z konfiguracji HA (lokalizacja domu); bez tego liczymy z prognozy PV
    from homeassistant.helpers.sun import get_astral_event_date
except Exception:  # noqa: BLE001
    get_astral_event_date = None

from .const import (
    CONF_BATTERY_CAPACITY_KWH, CONF_MAX_CHARGE_POWER_W, CONF_MAX_DISCHARGE_POWER_W,
    CONF_TARGET_SOC_CHARGE, CONF_PRICE_BUY_ENTITY, CONF_PRICE_SELL_ENTITY,
    CONF_PV_FORECAST_TODAY, CONF_PV_FORECAST_TOMORROW,
    CONF_SOC,
    DEFAULT_BATTERY_CAPACITY_KWH, DEFAULT_MAX_CHARGE_POWER_W, DEFAULT_MAX_DISCHARGE_POWER_W,
    DEFAULT_TARGET_SOC_CHARGE, DEFAULT_PRICE_BUY_ENTITY, DEFAULT_PRICE_SELL_ENTITY,
    DEFAULT_PV_FORECAST_TODAY, DEFAULT_PV_FORECAST_TOMORROW, DEFAULT_MIN_SELL_MARGIN,
)
from .reserve import compute_reserve
from .helpers import find_eid, normalize_price, number_value, state_str, switch_on, wear_cost_per_kwh
from .tariff import G12wTariff, get_profile, is_g12w_peak
from .inverter_floor import floor_profile
from .pv_forecast import PvForecast

_LOGGER = logging.getLogger(__name__)

MORNING_PEAK = (6, 13)
EVENING_PEAK = (15, 22)
PV_BLOCK_MAX_SOC = 30       # nie blokuj PV gdy SOC < 30
URGENT_MARGIN_PCT = 5.0       # SOC ≤ próg falownika + tyle pkt = „pilnie” (ładowanie od bieżącej godziny)
HARD_FLOOR_SOC = 10         # poniżej tego SOC nigdy nie planujemy rozładowania

# Mapowanie klucza time entity -> (label, para start/stop, faza)
TIME_LABELS = {
    "bateria_sprzedaz_start":   ("Sprzedaż baterii START (zestaw 1)", "bateria_sprzedaz", "start"),
    "bateria_sprzedaz_stop":    ("Sprzedaż baterii STOP (zestaw 1)",  "bateria_sprzedaz", "stop"),
    "bateria_sprzedaz_start_2": ("Sprzedaż baterii START (zestaw 2)", "bateria_sprzedaz_2", "start"),
    "bateria_sprzedaz_stop_2":  ("Sprzedaż baterii STOP (zestaw 2)",  "bateria_sprzedaz_2", "stop"),
    "pv_export_start":          ("Blokada PV START",  "pv_export", "start"),
    "pv_export_stop":           ("Blokada PV STOP",   "pv_export", "stop"),
    "start_grid_charge":        ("Ładowanie sieci START (zestaw 1)", "grid_charge", "start"),
    "stop_grid_charge":         ("Ładowanie sieci STOP (zestaw 1)",  "grid_charge", "stop"),
    "start_grid_charge_2":      ("Ładowanie sieci START (zestaw 2)", "grid_charge_2", "start"),
    "stop_grid_charge_2":       ("Ładowanie sieci STOP (zestaw 2)",  "grid_charge_2", "stop"),
}


# encje z cenami wykrywane po nazwie (jak w karcie): „jutro” oraz „dziś”
_RE_TOMORROW_ENTITY = re.compile(r"rce.*cena.*jutro|prices?_tomorrow|cena.*jutro|rce.*tomorrow|tomorrow.*rce")
_RE_TODAY_ENTITY = re.compile(r"rce.*cena|prices?_today|cena.*pradu")
# encje z cenami ZAKUPU: nigdy nie zgadujemy ich jako źródła cen sprzedaży
_RE_BUY_ENTITY = re.compile(r"buy|zakup|kupn|kupow|purchase|import|pob[oó]r|g1[12]|taryf|tariff")
# encje tej samej integracji co skonfigurowana encja zakupu, które mogą mieć pełne listy cen godzinowych
_BUY_SIBLINGS = {"pstryk": ("sensor.pstryk_json_buy", "sensor.pstryk_buy_price", "sensor.pstryk_current_buy_price")}


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class ScheduleOptimizer:
    def __init__(self, hass: HomeAssistant, coordinator, config: dict) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.config = config
        buy_eid = config.get(CONF_PRICE_BUY_ENTITY, DEFAULT_PRICE_BUY_ENTITY)
        self.tariff = G12wTariff(hass, buy_eid, hourly_fn=self.buy_hourly_for)
        self._rce_info: dict[str, Any] | None = None   # ostatni odczyt cen RCE (patrz rce_report)
        self._buy_info: dict[str, Any] | None = None   # ostatni odczyt godzinowych cen zakupu (patrz buy_report)
        self._buy_cache: tuple[tuple, dict] | None = None
        self._rce_cache: tuple[tuple, dict] | None = None
        self.pv_fc = PvForecast(hass)                      # Solcast albo Forecast.Solar — jedno źródło dla planu i karty

    # ---------------------------------------------------------------- I/O
    async def async_load(self) -> None:
        await self.tariff.async_load()

    # --------------------------------------------------------------- helpers
    def _cfg(self, key, default):
        return self.config.get(key, default)

    def _cfg_num(self, key, default: float, lo: float | None = None) -> float:
        """Wartość liczbowa z konfiguracji; przy błędnej (tekst, nan, poniżej `lo`) wraca wartość domyślna."""
        try:
            val = float(self.config.get(key, default))
        except (TypeError, ValueError):
            return float(default)
        if not math.isfinite(val) or (lo is not None and val < lo):
            return float(default)
        return val

    def _read_soc(self) -> float | None:
        eid = self.config.get(CONF_SOC, "sensor.inverter_battery")
        for cand in (eid, "sensor.inverter_battery", "sensor.bms_soc"):
            st = self.hass.states.get(cand)
            if st and st.state not in ("unknown", "unavailable", ""):
                try:
                    val = float(st.state)
                except (ValueError, TypeError):
                    continue
                if math.isfinite(val):
                    return min(100.0, max(0.0, val))
        return None

    def _read_current_time(self, key: str) -> str:
        raw = state_str(self.hass, find_eid(self.hass, "time", key))
        return raw[:5] if raw else "—"

    def _read_pv_forecast_kwh(self, eid_key: str, default_eid: str) -> float | None:
        """Suma prognozy PV na dziś / jutro w kWh (Solcast albo Forecast.Solar, z przeliczeniem jednostki)."""
        eid = self.config.get(eid_key, default_eid)
        offset = 1 if eid_key == CONF_PV_FORECAST_TOMORROW else 0
        return self.pv_fc.daily_kwh(eid, dt_util.now().date() + timedelta(days=offset))

    def _read_pv_hourly(self, offset: int = 0) -> list[float | None] | None:
        """Lista 24 prognoz PV (kWh/h) na dziś (offset=0) lub jutro (offset=1): Solcast albo Forecast.Solar."""
        if offset == 0:
            eid = self.config.get(CONF_PV_FORECAST_TODAY, DEFAULT_PV_FORECAST_TODAY)
        else:
            eid = self.config.get(CONF_PV_FORECAST_TOMORROW, DEFAULT_PV_FORECAST_TOMORROW)
        return self.pv_fc.hourly(eid, dt_util.now().date() + timedelta(days=offset))[0]

    def pv_card_payload(self) -> dict[str, Any]:
        return self.pv_fc.card_payload(self.config.get(CONF_PV_FORECAST_TODAY, DEFAULT_PV_FORECAST_TODAY),
                                       self.config.get(CONF_PV_FORECAST_TOMORROW, DEFAULT_PV_FORECAST_TOMORROW))

    def pv_source(self) -> str | None:
        return self.pv_fc.source(self.config.get(CONF_PV_FORECAST_TODAY, DEFAULT_PV_FORECAST_TODAY))

    # Nazwy atrybutów z cenami: różne integracje (RCE PSE, Nord Pool, własne szablony) nazywają je różnie.
    _RCE_LISTS_TODAY = ("prices", "raw_today", "prices_today", "today", "forecast", "today_prices")
    _RCE_LISTS_TOMORROW = ("raw_tomorrow", "prices_tomorrow", "tomorrow_prices", "tomorrow", "forecast_tomorrow", "next_day")

    def _rce_entities(self) -> tuple[list[str], list[str]]:
        """(encje „dziś”, encje „jutro”) — skonfigurowana, znane nazwy, a na końcu każda inna encja z „rce” w nazwie."""
        sell_eid = self.config.get(CONF_PRICE_SELL_ENTITY, DEFAULT_PRICE_SELL_ENTITY)
        buy_eid = self.config.get(CONF_PRICE_BUY_ENTITY, DEFAULT_PRICE_BUY_ENTITY)
        # te same nazwy i wzorce co w karcie (tabela cen), żeby plan widział to, co widać na ekranie
        today_c = [sell_eid, "sensor.rce_pse_cena", "sensor.rce_pse_cena_dzisiaj", "sensor.rce_pse_prices_today",
                   "sensor.rce_prices_today", "sensor.cena_pradu_dzisiaj", "sensor.energy_price_today"]
        tomorrow_c = ["sensor.rce_pse_cena_jutro", "sensor.rce_pse_prices_tomorrow", "sensor.rce_prices_tomorrow",
                      "sensor.cena_pradu_jutro", "sensor.energy_price_tomorrow"]
        known = set(today_c) | set(tomorrow_c) | {buy_eid} | set(self._buy_entities())
        extra_today: list[str] = []
        extra_tomorrow: list[str] = []
        try:
            for st in self.hass.states.async_all("sensor"):
                eid = getattr(st, "entity_id", "") or ""
                low = eid.lower()
                if not eid or eid in known or _RE_BUY_ENTITY.search(low):
                    continue      # ceny zakupu nigdy nie są zgadywane jako ceny sprzedaży
                if _RE_TOMORROW_ENTITY.search(low):
                    extra_tomorrow.append(eid)
                elif "rce" in low or _RE_TODAY_ENTITY.search(low):
                    extra_today.append(eid)
        except Exception:  # noqa: BLE001
            pass
        dedup = lambda lst: list(dict.fromkeys(lst))  # noqa: E731
        buy_set = {buy_eid} | set(self._buy_entities())
        tomorrow_all = [e for e in dedup(tomorrow_c + sorted(extra_tomorrow)) if e not in buy_set]
        today_all = [e for e in dedup(today_c + tomorrow_all + sorted(extra_today)) if e not in buy_set or e == sell_eid]
        return today_all, tomorrow_all

    def _buy_entities(self) -> list[str]:
        """Encje z cenami ZAKUPU: skonfigurowana + (dla znanych integracji) jej encje z pełną listą cen."""
        buy = str(self.config.get(CONF_PRICE_BUY_ENTITY, DEFAULT_PRICE_BUY_ENTITY) or "")
        out = [buy] if buy else []
        low = buy.lower()
        for key, sib in _BUY_SIBLINGS.items():
            if key in low:
                out.extend(sib)
        return list(dict.fromkeys(out))

    def _read_rce_arrays(self) -> dict[str, list[float | None]]:
        """Ceny SPRZEDAŻY: {'YYYY-MM-DD': [hour0_price, hour1_price, ...]} dla dziś i jutro.

        Zbiera listy cen ze wszystkich atrybutów encji z cenami RCE (nie tylko o znanych nazwach), dla każdego dnia
        wybiera źródło z największym pokryciem godzin. Co zostało użyte i co widać w encjach — `rce_report()`."""
        entities, tomorrow_entities = self._rce_entities()
        fp = (tuple(tomorrow_entities), *self._price_fingerprint(entities))
        if self._rce_cache is not None and self._rce_cache[0] == fp:
            return {k: list(v) for k, v in self._rce_cache[1].items()}
        result, info = self._read_price_arrays(entities, tomorrow_entities)
        self._rce_info = info
        self._rce_cache = (fp, result)
        return {k: list(v) for k, v in result.items()}

    def _price_fingerprint(self, entities: list[str]) -> tuple:
        """Odcisk stanu encji z cenami: zmiana encji albo daty = nowy odczyt (bez zgadywania czasu ważności)."""
        # trzymamy same obiekty stanu: HA tworzy nowy obiekt przy każdej zmianie, więc porównanie wykrywa każdą zmianę
        return (dt_util.now().date().isoformat(), *((eid, self.hass.states.get(eid)) for eid in entities))

    def _read_buy_arrays(self) -> dict[str, list[float | None]]:
        """Ceny ZAKUPU godzinowe (taryfa dynamiczna, np. Pstryk) — ten sam czytnik co dla sprzedaży."""
        ents = self._buy_entities()
        fp = self._price_fingerprint(ents)
        if self._buy_cache is not None and self._buy_cache[0] == fp:
            return {k: list(v) for k, v in self._buy_cache[1].items()}
        result, info = self._read_price_arrays(ents, [])
        self._buy_info = info
        self._buy_cache = (fp, result)
        return {k: list(v) for k, v in result.items()}

    def buy_hourly_for(self, d: date) -> list[float | None] | None:
        """Lista 24 cen zakupu dla dnia d (None = brak listy w encji zakupu)."""
        try:
            return self._read_buy_arrays().get(d.isoformat())
        except Exception:  # noqa: BLE001
            _LOGGER.debug("EMS: odczyt godzinowych cen zakupu nieudany", exc_info=True)
            return None

    def buy_report(self) -> dict[str, Any]:
        """Co czytnik cen zakupu widział przy ostatnim odczycie (jak rce_report)."""
        self._read_buy_arrays()
        return self._buy_info or {}

    def _read_price_arrays(self, entities: list[str], tomorrow_entities: list[str]) -> tuple[dict[str, list[float | None]], dict[str, Any]]:
        """Wspólny czytnik list cen (sprzedaż i zakup): {'YYYY-MM-DD': [24 ceny]} + opis, co zostało użyte."""
        result: dict[str, list[float | None]] = {}

        def _price_of(item, net=False):
            if isinstance(item, bool):
                return None
            if isinstance(item, (int, float)):
                return normalize_price(float(item))
            if isinstance(item, dict):
                # pstryk-ha-next: ceny brutto/netto w osobnych polach — jak w stanie encji (atrybut „basis”)
                for k in ("rce_pln", "price", "value", "cena", *(("net", "gross") if net else ("gross", "net"))):
                    p = item.get(k)
                    if p is not None and not isinstance(p, bool):
                        try:
                            return normalize_price(float(p))
                        except (TypeError, ValueError):
                            return None
            return None

        def _ts_of(item):
            """Początek okresu ceny. RCE PSE: `dtime` to KONIEC kwadransu (00:15 dla 00:00–00:15), początek jest
            w `start_dtime` albo w `business_date` + `period` — inaczej ostatni kwadrans doby trafiał do jutra,
            a każda godzina była przesunięta o 15 minut."""
            if not isinstance(item, dict):
                return None
            for k in ("start_dtime", "start", "datetime", "period_start"):
                if item.get(k):
                    return item[k]
            bd, per = item.get("business_date"), item.get("period")
            if bd and isinstance(per, str):
                m = re.match(r"\s*(\d{1,2}):(\d{2})", per)
                if m:
                    return f"{str(bd)[:10]} {int(m.group(1)):02d}:{m.group(2)}:00"
            for k in ("dtime", "time"):
                if item.get(k):
                    return item[k]
            return None

        def _parse(arr, target: date, positional_ok: bool = True, net: bool = False) -> list[float | None]:
            """Ceny godzinowe dla dnia target; wpisy 15-/30-min są uśredniane.

            Lista bez znaczników czasu opisuje jeden, nieznany dzień — używamy jej tylko tam,
            gdzie wiemy który (np. atrybut „today”/„tomorrow”). Inaczej „jutro” = kopia „dziś”."""
            if not arr:
                return []
            sums = [0.0] * 24
            counts = [0] * 24
            has_ts = any(_ts_of(x) for x in arr)
            if not has_ts and not positional_ok:
                return []
            if has_ts:
                for item in arr:
                    if not isinstance(item, dict):
                        continue
                    p = _price_of(item, net)
                    ts = _ts_of(item)
                    if p is None or not ts:
                        continue
                    try:
                        dt = dt_util.parse_datetime(str(ts))
                        if dt is None:
                            continue
                        dt = dt_util.as_local(dt)
                        if dt.date() != target:
                            continue
                        sums[dt.hour] += p
                        counts[dt.hour] += 1
                    except Exception:
                        continue
            else:
                n = len(arr)
                s_utc, hrs = self._local_day_span(target)
                if hrs != 24 and n % hrs == 0:
                    # doba ze zmianą czasu (23 / 25 godzin; 92 / 100 kwadransów): kolejność wpisów = prawdziwy czas,
                    # więc godzinę lokalną wyliczamy z czasu, a nie z numeru pozycji (inaczej cała doba jest przesunięta)
                    step = timedelta(minutes=60 / (n // hrs))
                    for i, item in enumerate(arr):
                        p = _price_of(item)
                        if p is None:
                            continue
                        h = dt_util.as_local(s_utc + step * i).hour
                        sums[h] += p
                        counts[h] += 1
                else:
                    per_hour = max(1, n // 24)
                    for i, item in enumerate(arr[: per_hour * 24]):
                        p = _price_of(item)
                        if p is None:
                            continue
                        h = i // per_hour
                        sums[h] += p
                        counts[h] += 1
            return [(sums[h] / counts[h]) if counts[h] else None for h in range(24)]

        today = dt_util.now().date()
        tomorrow = today + timedelta(days=1)
        # lista atrybutów każdej encji: [(encja, atrybut, lista)]
        sources: list[tuple[str, str, list]] = []
        seen: list[str] = []
        net_basis: set[str] = set()
        for eid in entities:
            st = self.hass.states.get(eid)
            if not st:
                continue
            attrs = st.attributes or {}
            if str(attrs.get("basis") or "").strip().lower() == "net":
                net_basis.add(eid)
            lists = [(k, v) for k, v in attrs.items() if isinstance(v, list) and v]
            seen.append(f"{eid} ({st.state}): " + (", ".join(f"{k}[{len(v)}]" for k, v in lists) if lists else "brak list z cenami w atrybutach"))
            known = [n for n in (*self._RCE_LISTS_TODAY, *self._RCE_LISTS_TOMORROW) if any(k == n for k, _ in lists)]
            ordered = [(k, v) for n in known for k, v in lists if k == n] + [(k, v) for k, v in lists if k not in known]
            for k, v in ordered:
                sources.append((eid, k, v))

        def _best(target: date, is_tomorrow: bool):
            best: tuple[int, str, list[float | None]] | None = None
            for eid, name, lst in sources:
                if is_tomorrow:
                    positional = name in self._RCE_LISTS_TOMORROW or (eid in tomorrow_entities and name in self._RCE_LISTS_TODAY)
                else:   # lista z encji „jutro” bez znaczników czasu nigdy nie jest ceną „dziś”
                    positional = name in self._RCE_LISTS_TODAY and eid not in tomorrow_entities
                hours = _parse(lst, target, positional_ok=positional, net=eid in net_basis)
                cnt = sum(1 for v in hours if v is not None)
                if cnt and (best is None or cnt > best[0]):
                    best = (cnt, f"{eid}.{name}", hours)
            return best

        info: dict[str, Any] = {"checked": entities, "seen": seen, "today": {"source": None, "hours": 0},
                                "tomorrow": {"source": None, "hours": 0}}
        for target, is_tomorrow, key in ((today, False, "today"), (tomorrow, True, "tomorrow")):
            b = _best(target, is_tomorrow)
            if b:
                result[target.isoformat()] = b[2]
                info[key] = {"source": b[1], "hours": b[0]}
        t0, t1 = result.get(today.isoformat()), result.get(tomorrow.isoformat())
        if t0 and t1 and t0 == t1:      # dwa identyczne dni to kopia, nie prognoza — nie planuj na niej
            result.pop(tomorrow.isoformat(), None)
            info["tomorrow"] = {"source": None, "hours": 0, "note": "identyczne jak dziś (odrzucone jako kopia)"}
        return result, info

    @staticmethod
    def _local_day_span(target: date) -> tuple[datetime, int]:
        """(początek doby lokalnej w UTC, liczba godzin doby). Zmiana czasu daje 23 albo 25 godzin."""
        s = dt_util.as_local(datetime.combine(target, dtime.min)).astimezone(timezone.utc)
        e = dt_util.as_local(datetime.combine(target + timedelta(days=1), dtime.min)).astimezone(timezone.utc)
        return s, max(1, int(round((e - s).total_seconds() / 3600)))

    def rce_expected_hours(self, target: date) -> int:
        """Ile godzin lokalnych powinno mieć cenę: 24, a w dobie wiosennej zmiany czasu 23 (nie ma godziny 02:00)."""
        return min(24, self._local_day_span(target)[1])

    def rce_report(self) -> dict[str, Any]:
        """Co czytnik cen widział przy ostatnim odczycie: encje, listy w atrybutach, użyte źródła i liczba godzin."""
        if self._rce_info is None:
            self._read_rce_arrays()
        return self._rce_info

    # ------------------------------------------------ słońce
    def _sun_hours(self, d: date) -> tuple[float, float] | None:
        """(wschód, zachód) jako godziny lokalne (np. 6.42) albo None, gdy HA nie poda."""
        if get_astral_event_date is None:
            return None
        try:
            rise = get_astral_event_date(self.hass, "sunrise", d)
            sset = get_astral_event_date(self.hass, "sunset", d)
        except Exception:  # noqa: BLE001
            return None
        if not rise or not sset:
            return None
        r, st = dt_util.as_local(rise), dt_util.as_local(sset)
        return r.hour + r.minute / 60.0, st.hour + st.minute / 60.0

    def _pv_day(self, offset: int = 0) -> tuple[list[float | None] | None, tuple[float, float]]:
        """Prognoza godzinowa PV przycięta do dnia (poza wschód–zachód = 0) oraz (wschód, zachód).

        Solcast bywa niezerowy o zmierzchu/świcie; sterowanie nie może na tym planować.
        Bez danych słońca granice wynikają z godzin, w których prognoza jest dodatnia."""
        pv = self._read_pv_hourly(offset)
        sun = self._sun_hours(dt_util.now().date() + timedelta(days=offset))
        if sun is None:
            act = [h for h in range(24) if pv and isinstance(pv[h], (int, float)) and pv[h] > 0.02]
            sun = (float(min(act)), float(max(act) + 1)) if act else (7.0, 17.0)
        if not pv:
            return None, sun
        rise, sset = sun
        k = self.pv_factor()
        out: list[float | None] = []
        for h in range(24):
            v = pv[h]
            if isinstance(v, (int, float)) and k != 1.0:
                v = v * k
            out.append(0.0 if (h + 1 <= rise or h >= sset) else v)
        return out, sun

    def pv_factor(self) -> float:
        """Korekta prognozy PV z historii (prognoza vs wykonanie z 14 dni), gdy włączona; inaczej 1,0."""
        if not switch_on(self.hass, "pv_forecast_correction", True):
            return 1.0
        ins = getattr(getattr(self.coordinator, "runtime", None), "insights", None)
        if ins is None:
            return 1.0
        try:
            return float(ins.pv_correction()["factor"])
        except Exception:  # noqa: BLE001
            return 1.0

    def wear_cost(self) -> float:
        """Koszt zużycia baterii w zł na kWh przechodzącą przez baterię (0 = nie liczymy)."""
        return wear_cost_per_kwh(self.hass, self._cfg_num(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH, lo=0.1))

    def pv_raw_today(self) -> tuple[float | None, list[float | None] | None]:
        """Prognoza PV na dziś bez korekty (do zapisu „prognoza vs wykonanie”)."""
        return self._read_pv_forecast_kwh(CONF_PV_FORECAST_TODAY, DEFAULT_PV_FORECAST_TODAY), self._read_pv_hourly(0)

    @staticmethod
    def _pv_active(pv: list | None, sun: tuple[float, float]) -> list[int]:
        """Godziny realnej produkcji: w dzień (wschód–zachód) i powyżej progu względnego.

        Próg zależy od prognozy dnia (3% szczytu, min. 0,05 kWh), więc w listopadzie, gdy szczyt to 0,9 kWh,
        też wychodzi sensowny zestaw godzin — stały próg 1 kWh odrzucał całą zimę."""
        if not pv:
            return []
        vals = [v for v in pv if isinstance(v, (int, float))]
        peak = max(vals) if vals else 0.0
        thr = max(0.05, 0.03 * peak)
        return [h for h in range(24)
                if isinstance(pv[h], (int, float)) and pv[h] >= thr and sun[0] - 0.5 <= h + 0.5 <= sun[1] + 0.5]

    # ------------------------------------------------ API dla runtime / rezerwy / opłacalności
    def pv_hourly_today(self) -> list[float | None] | None:
        return self._pv_day(0)[0]

    def pv_scale_next_day(self) -> float:
        today = self._read_pv_forecast_kwh(CONF_PV_FORECAST_TODAY, DEFAULT_PV_FORECAST_TODAY)
        tomorrow = self._read_pv_forecast_kwh(CONF_PV_FORECAST_TOMORROW, DEFAULT_PV_FORECAST_TOMORROW)
        if today and tomorrow and today > 0.5:
            return min(3.0, max(0.0, tomorrow / today))
        return 1.0

    def rce_arrays(self) -> dict[str, list[float | None]]:
        return self._read_rce_arrays()

    def profit_reference(self) -> float | None:
        """Koszt alternatywny 1 kWh: średnia RCE w godzinach produkcji PV (dziś).

        Energia w baterii pochodzi z PV, które inaczej zostałoby sprzedane po tej cenie."""
        rce = self._read_rce_arrays().get(dt_util.now().date().isoformat())
        if not rce:
            return None
        pv, sun = self._pv_day(0)
        active = set(self._pv_active(pv, sun)) if pv is not None else None
        prices = []
        for h in range(24):
            p = rce[h] if h < len(rce) else None
            if not isinstance(p, (int, float)):
                continue
            if active is not None and h not in active:
                continue
            prices.append(float(p))
        if not prices:
            prices = [float(p) for p in rce if isinstance(p, (int, float))]
        return sum(prices) / len(prices) if prices else None

    @staticmethod
    def _fmt_stop(hour_abs: int) -> str:
        """Godzina STOP jako HH:MM. 24:00/00:00 -> 23:59, bo 00:00 oznacza 'nie ustawiono'
        i scheduler ignoruje takie reguły (STOP po północy nigdy by nie zadziałał)."""
        h = int(hour_abs) % 24
        if h == 0:
            return "23:59"
        return f"{h:02d}:00"

    @staticmethod
    def _avg(vals) -> float | None:
        clean = [v for v in vals if isinstance(v, (int, float))]
        return sum(clean) / len(clean) if clean else None

    @staticmethod
    def _soc_entity_value(hass, key: str, default: float) -> float:
        return number_value(hass, key, default)

    # ------------------------------------------------------------ suggest()
    # ------------------------------------------------------------ suggest()
    def _load_hourly(self, total: float | None) -> list[float]:
        lf = (getattr(self.coordinator, "data", None) or {}).get("load_forecast") or {}
        hourly = lf.get("hourly_forecast")
        if isinstance(hourly, list) and len(hourly) == 24:
            try:
                vals = [max(0.0, float(v)) for v in hourly]
                if all(math.isfinite(v) for v in vals):
                    return vals
            except (TypeError, ValueError):
                pass
        if total and total > 0:
            return [total / 24.0] * 24
        return [0.5] * 24

    def _load_today(self) -> list[float | None] | None:
        """Zużycie w godzinach do końca dziś (kWh/h) z prognozy bieżącej (zużycie dotychczas + tempo dnia)."""
        lf = (getattr(self.coordinator, "data", None) or {}).get("load_forecast") or {}
        arr = lf.get("hourly_remaining_today")
        if not isinstance(arr, list) or len(arr) != 24:
            return None
        out: list[float | None] = []
        for v in arr:
            try:
                f = float(v) if v is not None and not isinstance(v, bool) else None
            except (TypeError, ValueError):
                f = None
            out.append(max(0.0, f) if f is not None and math.isfinite(f) else None)
        if not any(v is not None for v in out):
            return None
        return self._apply_live_load(out)

    LIVE_WEIGHTS = (1.0, 0.6, 0.3)        # wpływ korekty na bieżącą godzinę i dwie następne
    LIVE_MIN_KW = 0.3                       # mniejsze odchylenia ignorujemy
    LIVE_MAX_UP_KW = 4.0

    def _apply_live_load(self, out: list[float | None]) -> list[float | None]:
        """Korekta najbliższych godzin o różnicę między tym, co dom bierze teraz (średnia z ~15 min), a tym, czego oczekiwano."""
        self._live_load = None
        if not switch_on(self.hass, "live_load_correction", True):
            return out
        lf = getattr(self.coordinator, "load_forecast", None)
        now = dt_util.now()
        live = lf.live_load_kw(now) if lf is not None and hasattr(lf, "live_load_kw") else None
        h0 = now.hour
        exp = out[h0] if out[h0] is not None else next((out[h] for h in range(h0 + 1, 24) if out[h] is not None), None)
        if live is None or exp is None:
            return out
        delta = live - exp
        if abs(delta) < max(self.LIVE_MIN_KW, 0.25 * exp):
            return out
        delta = max(-0.5 * exp, min(self.LIVE_MAX_UP_KW, delta))
        res = list(out)
        for i, w in enumerate(self.LIVE_WEIGHTS):
            h = h0 + i
            if h < 24 and res[h] is not None:
                res[h] = max(0.0, res[h] + w * delta)
        self._live_load = {"live_kw": round(live, 2), "expected_kw": round(exp, 2), "delta_kw": round(delta, 2)}
        return res

    @staticmethod
    def _load_abs(ctx: dict, h_abs: int) -> float:
        """Zużycie domu w godzinie bezwzględnej (0 = dziś 00:00): dziś — prognoza bieżąca, później — profil jutra."""
        lt = ctx.get("load_today")
        if 0 <= h_abs < 24 and lt and lt[h_abs] is not None:
            return float(lt[h_abs])
        return float(ctx["load_h"][h_abs % 24])

    @staticmethod
    def _ref_for_day(prices: list, pv: list | None, active: list[int] | None = None) -> float | None:
        """Koszt alternatywny 1 kWh: średnia (ważona produkcją PV) cena RCE w godzinach pracy PV."""
        if not prices:
            return None
        num = den = 0.0
        for h in (active if active is not None else range(24)):
            p = prices[h] if h < len(prices) else None
            if not isinstance(p, (int, float)):
                continue
            w = (pv[h] if pv and isinstance(pv[h], (int, float)) else 0.0)
            if w > 0:
                num += p * w
                den += w
        if den > 0:
            return num / den
        vals = [p for p in prices if isinstance(p, (int, float))]
        return sum(vals) / len(vals) if vals else None

    def _build_context(self, now: datetime, soc: float) -> dict[str, Any]:
        today = now.date()
        tomorrow = today + timedelta(days=1)
        pv_k = self.pv_factor()
        rce = self._read_rce_arrays()
        rce_days = [rce.get(today.isoformat(), []), rce.get(tomorrow.isoformat(), [])]
        (pv0, sun0), (pv1, sun1) = self._pv_day(0), self._pv_day(1)
        pv_days = [pv0, pv1]
        sun_days = [sun0, sun1]
        pv_act = [self._pv_active(pv0, sun0), self._pv_active(pv1, sun1)]
        data = getattr(self.coordinator, "data", None) or {}
        load_tomorrow = (data.get("load_forecast") or {}).get("tomorrow_forecast")
        if not isinstance(load_tomorrow, (int, float)) or isinstance(load_tomorrow, bool) or not math.isfinite(load_tomorrow):
            load_tomorrow = None
        rt = getattr(self.coordinator, "runtime", None)
        try:
            c2, p2 = rt.charge_2d() if rt is not None else (None, None)
        except Exception:  # noqa: BLE001
            c2, p2 = None, None
        mode = "storm" if switch_on(self.hass, "storm_mode", False) else (
            "vacation" if switch_on(self.hass, "vacation_mode", False) else "normal")
        if mode == "vacation":     # urlop: stałe, minimalne zużycie zamiast prognozy z historii domu
            load_tomorrow = number_value(self.hass, "vacation_load_w", 250.0) / 1000.0 * 24.0
        ctx: dict[str, Any] = {
            "now": now,
            "soc": soc,
            "cap": self._cfg_num(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH, lo=0.1),
            "max_dis_kw": max(0.1, self._cfg_num(CONF_MAX_DISCHARGE_POWER_W, DEFAULT_MAX_DISCHARGE_POWER_W) / 1000.0),
            "max_chg_kw": max(0.1, self._cfg_num(CONF_MAX_CHARGE_POWER_W, DEFAULT_MAX_CHARGE_POWER_W) / 1000.0),
            "target_cfg": min(100.0, max(0.0, self._cfg_num(CONF_TARGET_SOC_CHARGE, DEFAULT_TARGET_SOC_CHARGE))),
            "eff": min(1.0, max(0.5, number_value(self.hass, "cycle_efficiency", 90.0) / 100.0)),
            "margin": number_value(self.hass, "min_sell_margin", DEFAULT_MIN_SELL_MARGIN),
            "min_soc_sell": number_value(self.hass, "min_soc_for_sell", 50.0),
            "stop_soc": number_value(self.hass, "minimalny_soc_dla_wylaczenia_sprzedazy", 20.0),
            "reserve_floor": number_value(self.hass, "reserve_floor_soc", 15.0),
            "dyn_reserve": switch_on(self.hass, "dynamic_reserve", False),
            "tol": number_value(self.hass, "grid_arbitrage_block_kwh", 0.5),
            "rce": rce_days,
            "avg": [self._avg(rce_days[0]), self._avg(rce_days[1])],
            "pv": pv_days,
            "sun": sun_days,
            "pv_act": pv_act,
            "pv_kwh": [None if v is None else v * pv_k for v in (
                self._read_pv_forecast_kwh(CONF_PV_FORECAST_TODAY, DEFAULT_PV_FORECAST_TODAY),
                self._read_pv_forecast_kwh(CONF_PV_FORECAST_TOMORROW, DEFAULT_PV_FORECAST_TOMORROW))],
            "pv_factor": pv_k,
            "wear": self.wear_cost(),
            "load_tomorrow": load_tomorrow,
            "load_h": ([number_value(self.hass, "vacation_load_w", 250.0) / 1000.0] * 24
                       if mode == "vacation" else self._load_hourly(load_tomorrow)),
            # godziny do północy: ile dom zużyje jeszcze DZIŚ (tempo dnia z rzeczywistego zużycia), a nie profil jutra
            "load_today": None if mode == "vacation" else self._load_today(),
            "charge_2d": c2,
            "pv_2d": p2,
            "arb_now": rt.arbitrage_status() if rt is not None else (False, ""),
            "grid_hours": set(), "grid_end": 0, "grid_target": 0.0, "grid_kwh": 0.0,
            "grid_targets": {}, "sold": set(), "midday_hours": set(),
            "mode": mode,
        }
        ctx["ref"] = [self._ref_for_day(rce_days[0], pv_days[0], pv_act[0]), self._ref_for_day(rce_days[1], pv_days[1], pv_act[1])]
        # SOC, który ma zostać do świtu (nie schodzimy poniżej progu wyłączenia sprzedaży ani rezerwy)
        inv = floor_profile(self.hass)
        ctx["inv"] = inv
        ctx["inv_floor_h"] = inv["hourly"]
        ctx["inv_now"] = inv["hourly"][now.hour]
        ns, ne = get_profile().night_window() or (22, 6)
        ctx["inv_dawn"] = max(inv["hourly"][h % 24] for h in range(ns, ne + 25))
        ctx["dawn_margin"] = number_value(self.hass, "dawn_margin_soc", 10.0)
        if mode == "storm":
            ctx["target_cfg"] = 100.0
        # próg z falownika + margines (jak „margines świtu”): plan nie schodzi tak nisko, by alarmy odzywały się przy normalnej pracy
        ctx["night_floor"] = max(ctx["stop_soc"], ctx["reserve_floor"], HARD_FLOOR_SOC + 5.0,
                                 min(90.0, ctx["inv_dawn"] + ctx["dawn_margin"]) if ctx["inv_dawn"] > 0 else 0.0)
        return ctx

    def _pv_abs(self, ctx: dict, h_abs: int) -> float:
        day, hh = divmod(h_abs, 24)
        arr = ctx["pv"][day] if 0 <= day < len(ctx["pv"]) else None
        if not arr:
            return 0.0
        v = arr[hh]
        return float(v) if isinstance(v, (int, float)) else 0.0

    def _run(self, ctx: dict, soc: float, h0: int, h1: int, grid_hours=(), sale_hours=(),
             floor: float | None = HARD_FLOOR_SOC, trace: list | None = None) -> tuple[float, float]:
        """(SOC końcowy, najniższy SOC po drodze) — godzina po godzinie dla godzin bezwzględnych [h0, h1).

        floor=None: bez dolnego ograniczenia, więc niedobór energii jest widoczny jako niski „najniższy SOC”.
        Cel ładowania z sieci bywa inny w nocy i w południe — bierzemy go dla każdej godziny osobno
        (ctx['grid_targets']), a w razie braku wpisu ogólny ctx['grid_target'].
        trace: gdy podana lista, dopisuje do niej SOC na koniec każdej godziny (wykres planu)."""
        cap = ctx["cap"]
        targets = ctx.get("grid_targets") or {}
        lowest = soc
        for h in range(h0, h1):
            delta = self._pv_abs(ctx, h) - self._load_abs(ctx, h)
            if h in sale_hours:
                delta -= ctx["max_dis_kw"]
            new = soc + delta / cap * 100.0
            if h in grid_hours:
                new = min(soc + (delta + ctx["max_chg_kw"] * ctx["eff"]) / cap * 100.0,
                          max(targets.get(h, ctx["grid_target"]), soc))
            lowest = min(lowest, new)
            if floor is None:
                soc = min(100.0, new)
            else:
                # falownik nie rozładowuje poniżej swojego progu; gdy SOC już jest niżej, dom jedzie na sieci
                fl = min(max(floor, ctx["inv_floor_h"][h % 24]), soc)
                soc = min(100.0, max(fl, new))
            if trace is not None:
                trace.append(soc)
        return soc, lowest

    def _simulate(self, ctx: dict, soc: float, h0: int, h1: int,
                  grid_hours=(), sale_hours=()) -> float:
        """SOC (%) po symulacji godzina po godzinie dla godzin bezwzględnych [h0, h1)."""
        return self._run(ctx, soc, h0, h1, grid_hours, sale_hours)[0]

    def _dawn_abs(self, ctx: dict, h_abs: int) -> int:
        """Pierwsza godzina po h_abs, od której PV pokrywa zużycie domu (koniec nocy dla baterii).

        Poza horyzontem prognozy (>2 dni) zakładamy świt jak jutro: wschód + 1 h."""
        for h in range(h_abs, h_abs + 36):
            pv = self._pv_abs(ctx, h)
            if pv > 0.05 and pv >= self._load_abs(ctx, h):
                return h
        return 24 * (h_abs // 24 + 1) + int(math.ceil(ctx["sun"][1][0])) + 1

    def _need_start_soc(self, ctx: dict, h0: int, h1: int, floor: float) -> float:
        """Minimalny SOC (%) na starcie h0, by do h1 bateria nie spadła poniżej floor (liczone wstecz)."""
        need = max(floor, ctx["inv_floor_h"][h1 % 24])
        for h in range(h1 - 1, h0 - 1, -1):
            delta_pct = (self._pv_abs(ctx, h) - self._load_abs(ctx, h)) / ctx["cap"] * 100.0
            need = min(100.0, max(floor, ctx["inv_floor_h"][h % 24], need - delta_pct))
        return need

    @staticmethod
    def _fmt_hm(h: float) -> str:
        m = int(round(h * 60))
        return f"{(m // 60) % 24:02d}:{m % 60:02d}"

    @staticmethod
    def _fmt_start(hour_abs: int) -> str:
        """00:00 oznacza 'nie ustawiono' — start o północy zapisujemy jako 00:01."""
        h = int(hour_abs) % 24
        return "00:01" if h == 0 else f"{h:02d}:00"

    async def suggest(self) -> dict[str, Any]:
        self.tariff.sample()
        try:
            await self.pv_fc.async_refresh()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: odświeżenie prognozy PV nieudane: %s", err)
        now = dt_util.now()
        soc = self._read_soc()
        if soc is None:
            return {
                "generated_at": now.isoformat(),
                "error": "SOC niedostępny — nie można zaproponować harmonogramu.",
                "proposals": {},
            }
        ctx = self._build_context(now, soc)
        proposals: dict[str, dict] = {}
        proposals.update(self._suggest_grid_charge(ctx))
        proposals.update(self._suggest_midday_charge(ctx))
        if ctx["mode"] == "storm":
            why = "Pomiń — tryb burzowy: energia zostaje w baterii (rezerwa 100%); wyłącz tryb, aby planować sprzedaż."
            for keys in (("bateria_sprzedaz_start", "bateria_sprzedaz_stop"),
                         ("bateria_sprzedaz_start_2", "bateria_sprzedaz_stop_2"),
                         ("pv_export_start", "pv_export_stop")):
                self._skip_pair(proposals, keys, why)
        else:
            proposals.update(self._suggest_battery_sell(ctx))
            proposals.update(self._suggest_pv_block(ctx))
        try:
            curve = self._plan_curve(ctx)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS: nie udało się policzyć krzywej planu: %s", err, exc_info=True)
            curve = None
        return {
            "mode": ctx["mode"],
            "curve": curve,
            "generated_at": now.isoformat(),
            "soc": soc,
            "rce_today_avg": ctx["avg"][0],
            "rce_tomorrow_avg": ctx["avg"][1],
            "g12w_peak": self._pk_off(now.date())[0],
            "g12w_off_peak": self._pk_off(now.date())[1],
            "tariff_mode": get_profile().mode,
            "tariff_dynamic": get_profile().dynamic_for(now.date()),
            "pv_today_kwh": ctx["pv_kwh"][0],
            "pv_tomorrow_kwh": ctx["pv_kwh"][1],
            "load_tomorrow_kwh": ctx["load_tomorrow"],
            "inverter_floor": round(ctx["inv_now"], 1),
            "inverter_floor_source": ctx["inv"]["source"],
            "sunrise_today": self._fmt_hm(ctx["sun"][0][0]),
            "sunset_today": self._fmt_hm(ctx["sun"][0][1]),
            "sunrise_tomorrow": self._fmt_hm(ctx["sun"][1][0]),
            "sunset_tomorrow": self._fmt_hm(ctx["sun"][1][1]),
            "proposals": proposals,
            "assumptions": self._assumptions(ctx),
        }

    def _assumptions(self, ctx: dict) -> dict[str, Any]:
        """Na czym opiera się plan (do wyświetlenia pod wykresem): zużycie dziś / jutro i prognoza PV."""
        lt = ctx.get("load_today")
        h0 = ctx["now"].hour + 1
        rest = sum(self._load_abs(ctx, h) for h in range(h0, 24)) if h0 < 24 else 0.0
        pv0 = ctx["pv"][0]
        pv_rest = sum(float(pv0[h]) for h in range(h0, 24) if pv0 and isinstance(pv0[h], (int, float))) if pv0 else None
        return {
            "load_rest_today_kwh": round(rest, 1),
            "load_today_source": ("tempo dnia + bieżące zużycie" if getattr(self, "_live_load", None) else "tempo dnia") if lt else "profil",
            "load_live": getattr(self, "_live_load", None),
            "load_tomorrow_kwh": None if ctx.get("load_tomorrow") is None else round(float(ctx["load_tomorrow"]), 1),
            "pv_rest_today_kwh": None if pv_rest is None else round(pv_rest, 1),
            "pv_tomorrow_kwh": None if ctx["pv_kwh"][1] is None else round(float(ctx["pv_kwh"][1]), 1),
            "pv_hourly_today": pv0 is not None,
            "pv_hourly_tomorrow": ctx["pv"][1] is not None,
            "pv_source": self.pv_source(),
            "pv_factor": round(float(ctx.get("pv_factor", 1.0)), 3),
            "wear_cost": round(float(ctx.get("wear", 0.0)), 3),
            "mode": ctx["mode"],
        }

    def _p(self, key: str, current: str, proposed: str | None, reason: str,
           confidence: str = "medium", skip: bool = False) -> dict:
        label = TIME_LABELS.get(key, (key, "", ""))[0]
        return {
            "label": label,
            "current": current or "—",
            "proposed": proposed,
            "reason": reason,
            "confidence": confidence,
            "skip": skip,
        }

    def _plan_curve(self, ctx: dict) -> dict[str, Any]:
        """Przewidywany SOC godzina po godzinie (do ~30 h) z zaplanowanym ładowaniem i sprzedażą.

        Dane do wykresu planu na karcie: SOC, próg odcięcia falownika, PV, zużycie, ceny kupna/sprzedaży,
        godziny ładowania z sieci i sprzedaży oraz szczyt taryfy."""
        now = ctx["now"]
        h0 = now.hour + 1
        n = max(1, min(30, 48 - h0))
        h1 = h0 + n
        grid = set(ctx["grid_hours"])
        sale = set(ctx["sold"])
        trace: list[float] = []
        self._run(ctx, ctx["soc"], h0, h1, grid, sale, trace=trace)
        base = now.replace(minute=0, second=0, microsecond=0)
        peak, buy, sell, pv, load, fl = [], [], [], [], [], []
        for i, h in enumerate(range(h0, h1)):
            t = base + timedelta(hours=h - now.hour)
            peak.append(1 if self._is_peak(t) else 0)
            try:
                buy.append(round(float(self.tariff.get_price(t)), 3))
            except Exception:  # noqa: BLE001
                buy.append(None)
            day, hh = divmod(h, 24)
            arr = ctx["rce"][day] if day < len(ctx["rce"]) else None
            v = arr[hh] if arr and hh < len(arr) else None
            sell.append(round(float(v), 3) if isinstance(v, (int, float)) else None)
            pv.append(round(self._pv_abs(ctx, h), 2))
            load.append(round(self._load_abs(ctx, h), 2))
            fl.append(round(float(ctx["inv_floor_h"][hh]), 1))
        return {
            "start": (base + timedelta(hours=h0 - now.hour)).isoformat(),
            "hours": n,
            "soc_now": round(float(ctx["soc"]), 1),
            "soc": [round(x, 1) for x in trace],
            "floor": fl, "pv": pv, "load": load, "buy": buy, "sell": sell, "peak": peak,
            "grid": [1 if h in grid else 0 for h in range(h0, h1)],
            "sale": [1 if h in sale else 0 for h in range(h0, h1)],
            "target": [round(float((ctx.get("grid_targets") or {}).get(h, 0.0)), 0) if h in grid else None for h in range(h0, h1)],
        }

    @staticmethod
    def _is_peak(t: datetime) -> bool:
        return is_g12w_peak(t)

    def _pk_off(self, d: date) -> tuple[float | None, float | None]:
        """(cena w szczycie, cena poza szczytem) dla dnia d: z cen godzinowych (taryfa dynamiczna)
        albo nauczone kubełki taryfy strefowej (jak dotąd)."""
        prof = get_profile()
        if prof.dynamic_for(d):
            arr = self.buy_hourly_for(d) or []
            spans = prof.peaks_for(d)
            pk = [float(arr[h]) for h in range(min(24, len(arr))) if _num(arr[h]) and any(a <= h < b for a, b in spans)]
            off = [float(arr[h]) for h in range(min(24, len(arr))) if _num(arr[h]) and not any(a <= h < b for a, b in spans)]
            return (sum(pk) / len(pk) if pk else None), (sum(off) / len(off) if off else None)
        return self.tariff.prices.get("peak"), self.tariff.prices.get("off_peak")

    def _buy_at(self, ctx: dict, h_abs: int) -> float | None:
        """Cena zakupu w godzinie bezwzględnej (0 = dziś 00:00)."""
        base = ctx["now"].replace(minute=0, second=0, microsecond=0)
        try:
            v = self.tariff.get_price(base + timedelta(hours=h_abs - ctx["now"].hour))
        except Exception:  # noqa: BLE001
            return None
        return float(v) if _num(v) else None

    def _cheapest_block(self, ctx: dict, n: int, lo: int, hi: int) -> tuple[int, float] | None:
        """(start, średnia cena) najtańszego ciągłego bloku n godzin w [lo, hi); przy remisie — najpóźniejszy
        (taki sam wynik jak dotąd przy taryfie strefowej: ładowanie tuż przed szczytem)."""
        best: tuple[int, float] | None = None
        for st in range(lo, hi - n + 1):
            ps = [self._buy_at(ctx, h) for h in range(st, st + n)]
            if any(p is None for p in ps):
                continue
            avg = sum(ps) / n
            if best is None or avg <= best[1] + 1e-9:
                best = (st, avg)
        return best

    def _skip_pair(self, out: dict, keys: tuple[str, ...], reason: str, conf: str = "high") -> None:
        for k in keys:
            out[k] = self._p(k, self._read_current_time(k), None, reason, conf, skip=True)

    # -------------------------------------------- ŁADOWANIE Z SIECI
    def _suggest_grid_charge(self, ctx: dict) -> dict:
        """Doładowanie w nocnym oknie taryfy (domyślnie G12w 22–06), kończone tuż przed szczytem.

        Cel = tyle, ile dom potrzebuje do chwili, gdy PV pokryje zużycie (rezerwa), nie zawsze
        'target' z konfiguracji. SOC liczony w chwili startu ładowania, nie 'teraz'."""
        out: dict = {}
        set1 = ("start_grid_charge", "stop_grid_charge")
        set2 = ("start_grid_charge_2", "stop_grid_charge_2")
        now_h = ctx["now"].hour
        prof = get_profile()
        nb = prof.night_bounds(ctx["now"])
        if nb is None:
            self._skip_pair(out, set1 + set2,
                            f"Pomiń — taryfa ({prof.label()}) nie ma taniego okna nocnego, więc ładowanie z sieci nie ma uzasadnienia cenowego.")
            return out
        ns, ne_today, ne_next = nb
        # Pilnie: SOC tuż nad progiem falownika (≤ próg + 5 pkt) w taniej porze → ładujemy od bieżącej godziny, bez czekania na „najlepszą”.
        floor_now = max(float(ctx.get("inv_now") or 0.0), float(HARD_FLOOR_SOC))
        urgent = bool(ctx["soc"] is not None and ctx["soc"] <= floor_now + URGENT_MARGIN_PCT and not prof.is_peak(ctx["now"]))
        if now_h >= ns or ne_today is None:
            earliest, end_h = now_h + 1, ne_next
            nxt = True
        elif now_h >= ne_today - 1:
            if urgent and now_h < ne_today:     # ostatnia godzina taniego okna, a bateria przy progu: ładujemy teraz, nie planujemy dopiero następnej nocy
                earliest, end_h = now_h + 1, ne_today
                nxt = False
            else:                               # tuż przed końcem okna nocnego — planujemy nadchodzącą noc
                earliest, end_h = ns, ne_next
                nxt = True
        else:
            earliest, end_h = now_h + 1, ne_today
            nxt = False
        if end_h is None:
            self._skip_pair(out, set1 + set2,
                            "Pomiń — jutro taryfa nie ma drogich godzin, więc ładowanie z sieci nie ma uzasadnienia cenowego.")
            return out
        urgent = urgent and earliest == now_h + 1
        ctx["urgent_charge"] = urgent
        if urgent:
            earliest = now_h
        end = end_h + 24 if nxt else end_h
        ne = end % 24
        if earliest >= end:
            self._skip_pair(out, set1 + set2, f"Pomiń — okno nocne (do {ne:02d}:00) już się kończy; propozycja pojawi się po południu.")
            return out

        soc_start = ctx["soc"]
        if earliest > now_h + 1:
            soc_start = self._simulate(ctx, ctx["soc"], now_h + 1, earliest)

        pv_profile = ctx["pv"][1] if end >= 24 else ctx["pv"][0]
        scale = 1.0
        floor_dawn = max(ctx["reserve_floor"], ctx["inv_dawn"])
        res = compute_reserve(
            now_hour=max(0, ne - 1), capacity_kwh=ctx["cap"], floor_pct=floor_dawn,
            load_hourly=ctx["load_h"], pv_hourly=pv_profile, pv_scale_next_day=scale,
        )
        target = min(ctx["target_cfg"], res["pct"] + ctx["dawn_margin"])
        if ctx["mode"] == "storm":
            target = 100.0
        floor_note = (f" Próg odcięcia falownika: {ctx['inv_dawn']:.0f}% ({ctx['inv']['source']})."
                      if ctx["inv_dawn"] > ctx["reserve_floor"] else "")
        if urgent:
            floor_note += (f" SOC {ctx['soc']:.0f}% jest tuż nad progiem falownika ({floor_now:.0f}%), więc ładowanie startuje od razu, "
                           f"a nie dopiero w najlepszej godzinie.")

        # Słaby dzień po nocy: sam „most do świtu” nie wystarczy — bateria ma pokryć też drogi szczyt (domyślnie 6–22),
        # bo import w szczycie jest wielokrotnie droższy niż ładowanie nocne.
        day_pv = ctx["pv"][1] if end >= 24 else ctx["pv"][0]
        base = 24 if end >= 24 else 0
        d_end = (ctx["now"] + timedelta(days=1)).date() if end >= 24 else ctx["now"].date()
        pk, off = self._pk_off(d_end)
        peak_note = ""
        if (ctx["mode"] != "storm" and day_pv and isinstance(pk, (int, float)) and isinstance(off, (int, float))
                and pk > off / ctx["eff"] + 0.05 and prof.peak_day(d_end)):
            # Jeśli w ciągu dnia jest tanie okno (G12w: 13–15) i zestaw 2 ładowania jest włączony, wieczorny szczyt
            # pokryje doładowanie południowe — noc ma wtedy zapewnić tylko szczyt poranny (nie kupujemy na zapas).
            mw = prof.midday_window_for(d_end)
            midday_covers = mw is not None and switch_on(self.hass, "ladowanie_z_sieci_2", False)
            ns_end = prof.night_start_for(d_end)
            cover_end = mw[0] if midday_covers else min(ns_end if ns_end is not None else 24, 24)
            need_day = self._need_start_soc(ctx, base + ne, base + cover_end, floor_dawn)
            if need_day + 3.0 > target:
                target = min(ctx["target_cfg"], need_day + 3.0)
                peak_note = (f" Prognoza PV na ten dzień jest słaba, więc cel obejmuje też szczyt taryfy {ne}–{cover_end} "
                             f"(SOC o {ne:02d}:00 ≥ ~{need_day:.0f}%).")
                if midday_covers:
                    peak_note += (f" Szczyt wieczorny pokryje doładowanie w oknie {mw[0]}–{mw[1]} "
                                  f"(zestaw 2 ładowania jest włączony), więc nie kupuję go na zapas w nocy.")

        # „Cel” to SOC potrzebny na KONIEC okna nocnego (tuż przed szczytem), więc porównujemy go z SOC, jaki zostanie
        # po nocy bez ładowania — a nie z SOC z początku nocy (przez noc dom zużywa energię z baterii).
        soc_dawn = self._simulate(ctx, soc_start, earliest, end)
        if soc_dawn >= target - 2.0:
            reason = (f"Pomiń — bateria wystarczy do rana (przewidywany SOC {soc_dawn:.0f}% {'jutro ' if end >= 24 else ''}o {end % 24:02d}:00 bez ładowania, "
                      f"potrzeba ok. {target:.0f}% do czasu aż PV pokryje zużycie).{floor_note}")
            self._skip_pair(out, set1 + set2, reason)
            return out

        avail = end - earliest
        wear = ctx.get("wear", 0.0)
        if (wear > 0 and isinstance(pk, (int, float)) and isinstance(off, (int, float))
                and not (prof.dynamic_for(ctx["now"].date()) or prof.dynamic_for(d_end))
                and pk <= off / ctx["eff"] + wear and ctx["mode"] != "storm"):
            self._skip_pair(out, set1 + set2,
                            f"Pomiń — ładowanie z sieci się nie opłaca: szczyt {pk:.2f} zł/kWh wobec {off:.2f} / {ctx['eff']:.0%} "
                            f"sprawności + {wear:.2f} zł/kWh kosztu zużycia baterii.")
            return out
        if prof.dynamic_for(ctx["now"].date()) or prof.dynamic_for(d_end):
            return self._grid_charge_dynamic(ctx, out, set1, set2, earliest, end, soc_start, target, res,
                                             floor_note, peak_note, pk)
        s_abs, n, grid_kwh = earliest, avail, 0.0
        for _ in range(3):             # start ładowania zależy od ilości, a ilość od SOC w chwili startu
            soc_at = soc_start if s_abs == earliest else self._simulate(ctx, ctx["soc"], now_h + 1, s_abs)
            stored_kwh = max(0.0, (target - soc_at) / 100.0 * ctx["cap"])
            grid_kwh = stored_kwh / ctx["eff"]
            n = max(1, math.ceil(grid_kwh / ctx["max_chg_kw"]))
            if n >= avail:
                s_abs, n = earliest, avail
                grid_kwh = min(grid_kwh, avail * ctx["max_chg_kw"])
                break
            new_s = earliest if urgent else end - n            # zwykle: ładowanie kończy się tuż przed szczytem; pilnie: od razu
            if new_s == s_abs:
                break
            s_abs = new_s
        soc_start = soc_at
        ctx["grid_hours"] = set(range(s_abs, end))
        ctx["grid_end"] = end
        ctx["grid_target"] = target
        ctx["grid_targets"] = {h: target for h in range(s_abs, end)}
        ctx["grid_kwh"] = grid_kwh

        reason = (f"Doładuj ~{grid_kwh:.1f} kWh z sieci ({s_abs % 24:02d}:00–{end % 24:02d}:00, najtańsza taryfa nocna): "
                  f"SOC o starcie ~{soc_start:.0f}% → cel {target:.0f}% (tyle potrzeba do rana, "
                  f"do godz. {res['until_hour']}:00, aż PV pokryje zużycie).{floor_note}{peak_note}")
        out[set1[0]] = self._p(set1[0], self._read_current_time(set1[0]), self._fmt_start(s_abs), reason, "high")
        out[set1[1]] = self._p(set1[1], self._read_current_time(set1[1]), self._fmt_stop(end), reason, "high")
        self._skip_pair(out, set2,
                        "Pomiń — okno nocne wystarcza; ładowanie z sieci w dzień koliduje z darmową energią z PV.")
        return out

    def _grid_charge_dynamic(self, ctx: dict, out: dict, set1, set2, earliest: int, end: int, soc_start: float,
                             target: float, res: dict, floor_note: str, peak_note: str, pk: float | None) -> dict:
        """Taryfa dynamiczna: ładowanie w NAJTAŃSZYCH godzinach przed szczytem (ciągły blok — jedna para START/STOP).

        Cel bloku uwzględnia zużycie domu między końcem ładowania a początkiem szczytu, tak by o `end` było `target`."""
        now_h = ctx["now"].hour
        cap, eff, chg = ctx["cap"], ctx["eff"], ctx["max_chg_kw"]
        avail = end - earliest
        s_abs, n = end - 1, 1
        blk_target, soc_at, grid_kwh, avg = target, soc_start, 0.0, None
        for _ in range(6):
            soc_at = soc_start if s_abs <= earliest else self._simulate(ctx, ctx["soc"], now_h + 1, s_abs)
            b_end = s_abs + n
            drop = 0.0 if b_end >= end else max(0.0, target - self._simulate(ctx, target, b_end, end))
            blk_target = min(100.0 if ctx["mode"] == "storm" else max(target, ctx["target_cfg"]), target + drop)
            stored = max(0.0, (blk_target - soc_at) / 100.0 * cap)
            grid_kwh = stored / eff
            n_new = max(1, min(avail, math.ceil(grid_kwh / chg)))
            if ctx.get("urgent_charge"):            # pilnie: start od razu, cena tylko do informacji
                ps = [self._buy_at(ctx, h) for h in range(earliest, earliest + n_new)]
                best = (earliest, sum(ps) / n_new) if ps and all(x is not None for x in ps) else (earliest, None)
            else:
                best = self._cheapest_block(ctx, n_new, earliest, end)
            s_new, avg = (best if best else (end - n_new, None))
            if (s_new, n_new) == (s_abs, n):
                break
            s_abs, n = s_new, n_new
        grid_kwh = min(grid_kwh, n * chg)
        wear = ctx.get("wear", 0.0)
        if pk is not None and avg is not None and not pk > avg / eff + 0.05 + wear and ctx["mode"] != "storm":
            wear_txt = f" i kosztu zużycia baterii ({wear:.2f} zł/kWh)" if wear > 0 else ""
            self._skip_pair(out, set1 + set2,
                            f"Pomiń — najtańsze godziny przed szczytem kosztują śr. {avg:.2f} zł/kWh, a szczyt śr. {pk:.2f}: "
                            f"różnica nie pokrywa strat cyklu baterii ({eff:.0%}){wear_txt}.")
            return out
        e_abs = s_abs + n
        ctx["grid_hours"] = set(range(s_abs, e_abs))
        ctx["grid_end"] = e_abs
        ctx["grid_target"] = blk_target
        ctx["grid_targets"] = {h: blk_target for h in range(s_abs, e_abs)}
        ctx["grid_kwh"] = grid_kwh
        price_txt = f", śr. {avg:.2f} zł/kWh" if avg is not None else ""
        reason = (f"Doładuj ~{grid_kwh:.1f} kWh z sieci ({s_abs % 24:02d}:00–{e_abs % 24:02d}:00 — najtańsze godziny przed szczytem "
                  f"o {end % 24:02d}:00{price_txt}): SOC o starcie ~{soc_at:.0f}% → {blk_target:.0f}%, tak by o {end % 24:02d}:00 "
                  f"zostało ~{target:.0f}% (tyle potrzeba do godz. {res['until_hour']}:00, aż PV pokryje zużycie).{floor_note}{peak_note}")
        out[set1[0]] = self._p(set1[0], self._read_current_time(set1[0]), self._fmt_start(s_abs), reason, "high")
        out[set1[1]] = self._p(set1[1], self._read_current_time(set1[1]), self._fmt_stop(e_abs), reason, "high")
        self._skip_pair(out, set2,
                        "Pomiń — okno nocne wystarcza; ładowanie z sieci w dzień koliduje z darmową energią z PV.")
        return out

    # -------------------------------------------- ŁADOWANIE DZIENNE (między szczytami; G12w: 13–15)
    def _suggest_midday_charge(self, ctx: dict) -> dict:
        """Tanie okno między szczytami (G12w: 13–15, dni robocze): doładowanie przed drogim szczytem wieczornym.

        Zestaw 2 ładowania z sieci. Opłaca się, gdy bateria bez doładowania zeszłaby do progu odcięcia
        falownika przed końcem szczytu (wtedy dom kupowałby prąd w szczycie)."""
        out: dict = {}
        keys = ("start_grid_charge_2", "stop_grid_charge_2")
        now = ctx["now"]
        now_h = now.hour
        today = now.date()

        def skip(reason: str, conf: str = "high") -> dict:
            self._skip_pair(out, keys, reason, conf)
            return out

        prof = get_profile()
        mw = prof.midday_window_for(today)
        if mw is None:
            return skip(f"Pomiń — taryfa ({prof.label()}) nie ma taniego okna między szczytami.")
        ms, me = mw
        ev_a, ev_b = prof.peaks_for(today)[1]
        if not prof.peak_day(today):
            return skip("Pomiń — dziś taryfa pozaszczytowa przez całą dobę; osobne okno dzienne nie jest potrzebne.")
        lo, end = max(ms, now_h + 1), me
        if lo >= end:
            return skip(f"Pomiń — tanie okno {ms}–{me} już minęło lub się kończy; kolejna propozycja po północy.")
        dyn = prof.dynamic_for(today)
        pk, off = self._pk_off(today)
        if not (isinstance(pk, (int, float)) and isinstance(off, (int, float))):
            return skip("Pomiń — brak nauczonych cen taryfy (szczyt/pozaszczyt).", "low")
        eff = ctx["eff"]
        wear = ctx.get("wear", 0.0)
        if not pk > off / eff + 0.05 + wear:
            return skip("Pomiń — różnica cen szczyt/pozaszczyt nie pokrywa strat cyklu baterii"
                        + (f" i kosztu jej zużycia ({wear:.2f} zł/kWh)." if wear > 0 else "."))

        floor_eve = max(ctx["reserve_floor"], float(HARD_FLOOR_SOC))
        need = self._need_start_soc(ctx, ev_a, ev_b, floor_eve)
        target = min(ctx["target_cfg"], need + ctx["dawn_margin"] / 2.0)
        if ctx["mode"] == "storm":
            target = 100.0
        soc_lo = ctx["soc"] if lo <= now_h + 1 else self._simulate(ctx, ctx["soc"], now_h + 1, lo)
        soc15 = soc_lo if lo >= ev_a else self._simulate(ctx, soc_lo, lo, ev_a)
        fl15 = ctx["inv_floor_h"][ev_a % 24]
        if soc15 >= target - 2.0:
            return skip(f"Pomiń — bateria wystarczy na szczyt wieczorny (przewidywany SOC {soc15:.0f}% o {ev_a:02d}:00, "
                        f"potrzeba ok. {target:.0f}% do {ev_b:02d}:00; próg odcięcia falownika {fl15:.0f}%).")

        stored = max(0.0, (target - soc15) / 100.0 * ctx["cap"])
        grid_kwh = stored / eff
        n = max(1, math.ceil(grid_kwh / ctx["max_chg_kw"]))
        n = min(n, end - lo)
        grid_kwh = min(grid_kwh, n * ctx["max_chg_kw"])
        s = end - n
        if dyn:
            # taryfa dynamiczna: najtańszy blok w oknie i realne ceny (blok vs średnia szczytu wieczornego)
            best = self._cheapest_block(ctx, n, lo, end)
            if best:
                s, off = best
            ev_prices = [p for p in (self._buy_at(ctx, h) for h in range(ev_a, ev_b)) if p is not None]
            if ev_prices:
                pk = sum(ev_prices) / len(ev_prices)
            if not pk > off / eff + 0.05 + wear:
                return skip(f"Pomiń — najtańsze godziny {ms}–{me} (śr. {off:.2f} zł/kWh) nie są na tyle tańsze od szczytu "
                            f"wieczornego (śr. {pk:.2f}), by pokryć straty cyklu baterii"
                            + (f" i koszt jej zużycia ({wear:.2f} zł/kWh)." if wear > 0 else "."))
        saving = stored * (pk - off / eff - wear)
        if saving < 0.1:
            return skip(f"Pomiń — zysk z doładowania w oknie {ms}–{me} byłby znikomy (~{saving:.2f} zł).")
        stop_h = s + n
        reason = (f"Doładuj ~{grid_kwh:.1f} kWh z sieci {s:02d}:00–{stop_h:02d}:00 (tania taryfa, {'tuż ' if not dyn else ''}przed szczytem {ev_a}–{ev_b}): "
                  f"SOC o {ev_a:02d}:00 bez doładowania ~{soc15:.0f}% → cel {target:.0f}% (ok. {need:.0f}% potrzeba na szczyt do {ev_b:02d}:00; "
                  f"próg odcięcia falownika {fl15:.0f}%). Szacowany zysk ~{saving:.2f} zł.")
        if not switch_on(self.hass, "ladowanie_z_sieci_2", False):
            reason += " Zestaw 2 jest wyłączony — włącz przełącznik „Ładowanie z sieci (zestaw 2)”, aby propozycja zadziałała."
        conf = "medium"
        hrs = set(range(s, stop_h))                    # dalsze symulacje (sprzedaż wieczorna, wykres) widzą to ładowanie
        ctx["grid_hours"] = set(ctx["grid_hours"]) | hrs
        ctx["midday_hours"] = hrs
        ctx["grid_targets"].update({h: target for h in hrs})
        out[keys[0]] = self._p(keys[0], self._read_current_time(keys[0]), f"{s:02d}:00", reason, conf)
        out[keys[1]] = self._p(keys[1], self._read_current_time(keys[1]), f"{stop_h:02d}:00", reason, conf)
        return out

    # -------------------------------------------- SPRZEDAŻ Z BATERII
    def _best_window(self, prices: list[float | None], h_start: int, h_end: int,
                     max_hours: int) -> tuple[int, int, float] | None:
        """Znajdź pod-okno [h_start, h_end) o najwyższej średniej cenie."""
        best = None
        n = max_hours
        for s in range(h_start, h_end - n + 1):
            window = prices[s:s + n]
            vals = [v for v in window if isinstance(v, (int, float))]
            if len(vals) < n:
                continue
            avg = sum(vals) / len(vals)
            if best is None or avg > best[2]:
                best = (s, s + n, avg)
        return best

    def _reserve_pct_at(self, ctx: dict, h_abs: int) -> float:
        day = min(1, h_abs // 24)
        pv = ctx["pv"][day] or ctx["pv"][0]
        kwh = ctx["pv_kwh"]
        scale = (kwh[1] / kwh[0]) if (day == 0 and kwh[0] and kwh[1] and kwh[0] > 0.5) else 1.0
        res = compute_reserve(
            now_hour=h_abs % 24, capacity_kwh=ctx["cap"],
            floor_pct=max(ctx["reserve_floor"], ctx["inv_floor_h"][h_abs % 24]),
            load_hourly=ctx["load_h"], pv_hourly=pv, pv_scale_next_day=min(3.0, scale),
        )
        return float(res["pct"])

    def _grid_blocks_sales(self, ctx: dict, day: int, lo_abs: int) -> str | None:
        """Czy planowane nocne ładowanie z sieci zablokuje sprzedaż (bilans 2-dniowy)?"""
        g = ctx["grid_kwh"]
        if g <= ctx["tol"] or lo_abs < ctx["grid_end"] or ctx["tol"] <= 0:
            return None
        c2, p2 = ctx["charge_2d"], ctx["pv_2d"]
        if c2 is None or p2 is None:
            return None
        if c2 + g > p2 + ctx["tol"]:
            return (f"ładowanie z sieci tej nocy (~{g:.1f} kWh) + dotychczasowe {c2:.1f} kWh przekroczy produkcję PV "
                    f"z 2 dni ({p2:.1f} kWh) — blokada arbitrażu zatrzymałaby sprzedaż")
        return None

    def _suggest_battery_sell(self, ctx: dict) -> dict:
        out: dict = {}
        now_h = ctx["now"].hour
        prof = get_profile()
        d0 = ctx["now"].date()
        p_today, p_tom = prof.peaks_for(d0), prof.peaks_for(d0 + timedelta(days=1))
        set_keys = {1: ("bateria_sprzedaz_start", "bateria_sprzedaz_stop"),
                    2: ("bateria_sprzedaz_start_2", "bateria_sprzedaz_stop_2")}
        sets = {}
        wins = []
        for i in (1, 2):
            # zestaw i = i-ty szczyt dziś, a gdy już minął — i-ty szczyt jutro (w taryfie dynamicznej jutro może być inaczej)
            if i <= len(p_today) and now_h + 1 < p_today[i - 1][1]:
                day, peaks = 0, p_today
            elif i <= len(p_tom):
                day, peaks = 1, p_tom
            else:
                self._skip_pair(out, set_keys[i], "Pomiń — taryfa nie ma tego szczytu (okna szczytu ustawiasz w konfiguracji integracji).")
                continue
            a, b = peaks[i - 1]
            lbl = "porannym" if (i == 1 and (len(peaks) > 1 or a < 12)) else "wieczornym"
            sets[i] = (set_keys[i], (a, b), lbl)
            lo = max(a, now_h + 1) if day == 0 else a
            wins.append((day * 24 + lo, day * 24 + b, i, day, lo, b))
        blocked, why = ctx["arb_now"]
        wins.sort()

        soc_ref, h_ref = ctx["soc"], now_h + 1
        sold: set[int] = set()
        ctx["sold"] = sold
        for lo_abs, b_abs, idx, day, lo, b in wins:
            keys, _peak, lbl = sets[idx]
            dname = "jutro" if day else "dziś"
            skip = lambda reason, conf="high", keys=keys: self._skip_pair(out, keys, reason, conf)  # noqa: E731

            if blocked:
                skip(f"Pomiń — bilans 2-dniowy blokuje sprzedaż już teraz ({why}).")
                continue
            prices = ctx["rce"][day]
            if not any(isinstance(p, (int, float)) for p in prices):
                skip(f"Pomiń — brak cen RCE na {dname}.", "low")
                continue
            blk = self._grid_blocks_sales(ctx, day, lo_abs)
            if blk:
                skip(f"Pomiń — {blk}.")
                continue

            if lo_abs > h_ref:
                soc_ref = self._simulate(ctx, soc_ref, h_ref, lo_abs, ctx["grid_hours"], sold)
                h_ref = lo_abs
            soc_lo = soc_ref
            need_soc = ctx["min_soc_sell"]
            floor = max(ctx["stop_soc"], float(HARD_FLOOR_SOC), ctx["inv_floor_h"][lo % 24])
            if ctx["dyn_reserve"]:
                res_pct = self._reserve_pct_at(ctx, lo_abs)
                need_soc = max(need_soc, res_pct)
                floor = max(floor, res_pct)
            if soc_lo < need_soc:
                skip(f"Pomiń — przewidywany SOC {soc_lo:.0f}% o {lo:02d}:00 ({dname}) poniżej progu sprzedaży {need_soc:.0f}%.")
                continue
            avail_lo = (soc_lo - floor) / 100.0 * ctx["cap"]
            if avail_lo < 1.0:
                skip(f"Pomiń — za mało energii do sprzedaży (~{avail_lo:.1f} kWh ponad {floor:.0f}% SOC).", "medium")
                continue
            n0 = max(1, min(3, math.ceil(avail_lo / ctx["max_dis_kw"]), b - lo))   # okno nie dłuższe niż czas do końca szczytu
            day_avg, ref = ctx["avg"][day], ctx["ref"][day]
            eff, margin = ctx["eff"], ctx["margin"]

            chosen, why_not = None, None
            for nn in range(n0, 0, -1):      # najdłuższe okno, które nie zostawi domu bez energii przed świtem
                w = self._best_window(prices, lo, b, nn)
                if not w:
                    miss = [f"{h:02d}" for h in range(lo, min(b, lo + nn)) if not isinstance(prices[h] if h < len(prices) else None, (int, float))]
                    why_not = why_not or (f"brak cen RCE {dname} dla godz. {', '.join(miss) or f'{lo:02d}–{b:02d}'}", "low")
                    continue
                s, e, avg = w
                if day_avg is not None and avg < day_avg:
                    why_not = why_not or (f"najlepsze okno {dname} ({avg:.3f} zł/kWh) jest poniżej średniej dnia ({day_avg:.3f})", "high")
                    continue
                wear = ctx.get("wear", 0.0)
                net = avg * eff - (ref if ref is not None else 0.0) - wear
                if net < margin:
                    wear_txt = f" − {wear:.3f} (zużycie baterii)" if wear > 0 else ""
                    why_not = why_not or (f"sprzedaż nieopłacalna {dname}: {avg:.3f} × {eff:.0%} − {(ref or 0):.3f} (koszt alternatywny)"
                                          f"{wear_txt} = {net:.3f} < min. marża {margin:.2f} zł/kWh", "high")
                    continue
                s_abs = day * 24 + s
                soc_s = soc_lo if s_abs <= lo_abs else self._simulate(ctx, soc_lo, lo_abs, s_abs, ctx["grid_hours"], sold)
                avail = (soc_s - floor) / 100.0 * ctx["cap"]
                if soc_s < need_soc or avail < 1.0:
                    why_not = why_not or (f"przewidywany SOC {soc_s:.0f}% o {s:02d}:00 ({dname}) jest za niski na sprzedaż", "medium")
                    continue
                sh = sold | set(range(s_abs, day * 24 + e))
                dawn = self._dawn_abs(ctx, day * 24 + e)
                _, low_pt = self._run(ctx, soc_s, s_abs, dawn, ctx["grid_hours"], sh, floor=None)
                if low_pt < ctx["night_floor"]:
                    why_not = why_not or (f"po sprzedaży {s:02d}–{e:02d} bateria spadłaby do ~{max(0.0, low_pt):.0f}% przed świtem "
                                          f"(PV pokryje dom dopiero ok. {dawn % 24:02d}:00; min. {ctx['night_floor']:.0f}%)", "high")
                    continue
                chosen = (s, e, avg, net, soc_s, avail, low_pt, dawn)
                break
            if not chosen:
                reason, conf = why_not or ("brak opłacalnego okna", "high")
                skip(f"Pomiń — {reason}.", conf)
                continue
            s, e, avg, net, soc_s, avail, low_pt, dawn = chosen

            sell_kwh = min(avail, ctx["max_dis_kw"] * (e - s))
            reason = (f"Najlepsze okno {dname} w szczycie {lbl}: {s:02d}–{e:02d}, śr. {avg:.3f} zł/kWh "
                      f"(dzień śr. {(day_avg or 0):.3f}). Przewidywany SOC o {s:02d}:00 ~{soc_s:.0f}%, "
                      f"sprzedaż ~{sell_kwh:.1f} kWh, zysk netto ~{net * sell_kwh:+.2f} zł. "
                      f"Do świtu (PV pokryje dom ok. {dawn % 24:02d}:00) SOC nie spadnie poniżej ~{max(0.0, low_pt):.0f}%.")
            conf = "high" if (avg - (day_avg or avg)) > 0.05 and net >= 2 * margin else "medium"
            k_s, k_e = keys
            out[k_s] = self._p(k_s, self._read_current_time(k_s), f"{s:02d}:00", reason, conf)
            out[k_e] = self._p(k_e, self._read_current_time(k_e), self._fmt_stop(e), reason, conf)
            sold.update(range(day * 24 + s, day * 24 + e))
        return out

    # -------------------------------------------- BLOKADA PV
    def _suggest_pv_block(self, ctx: dict) -> dict:
        """Blokada ładowania z PV (cała produkcja idzie na sprzedaż) w najdroższych godzinach.

        Opłaca się tylko, gdy (1) cena w tych godzinach przewyższa średnią cenę godzin PV o margines,
        (2) po zakończeniu blokady zostanie dość PV, by bateria się dopełniła."""
        out: dict = {}
        keys = ("pv_export_start", "pv_export_stop")
        now_h = ctx["now"].hour
        cap, margin = ctx["cap"], ctx["margin"]

        def skip(reason: str, conf: str = "high") -> dict:
            self._skip_pair(out, keys, reason, conf)
            return out

        day = 0 if any(h > now_h for h in ctx["pv_act"][0]) else 1   # dziś, jeśli PV jeszcze produkuje
        pv, prices = ctx["pv"][day], ctx["rce"][day]
        dname = "jutro" if day else "dziś"
        if not pv:
            return skip(f"Pomiń — brak prognozy godzinowej PV na {dname} (Solcast albo Forecast.Solar).", "low")
        if not any(isinstance(p, (int, float)) for p in prices):
            return skip(f"Pomiń — brak cen RCE na {dname}.", "low")

        lo = now_h + 1 if day == 0 else 0
        pv_hours = [h for h in ctx["pv_act"][day] if h >= lo and isinstance(prices[h], (int, float))]
        if len(pv_hours) < 2:
            rise, sset = ctx["sun"][day]
            return skip(f"Pomiń — za mało godzin z produkcją PV {dname} (słońce {int(rise):02d}:{int(rise % 1 * 60):02d}–"
                        f"{int(sset):02d}:{int(sset % 1 * 60):02d}, prognoza PV).")

        num = sum(pv[h] * prices[h] for h in pv_hours)
        den = sum(pv[h] for h in pv_hours)
        p_ref = num / den
        good = [h for h in pv_hours if prices[h] >= p_ref + margin]
        if not good:
            return skip(f"Pomiń — {dname} brak godzin, w których cena przewyższa średnią cenę godzin PV "
                        f"({p_ref:.3f}) o min. marżę {margin:.2f} zł/kWh.")

        runs: list[list[int]] = []
        for h in good:
            if runs and h == runs[-1][-1] + 1:
                runs[-1].append(h)
            else:
                runs.append([h])

        soc_first = self._simulate(ctx, ctx["soc"], now_h + 1, day * 24 + good[0]) if (day * 24 + good[0]) > now_h + 1 else ctx["soc"]
        min_soc = max(PV_BLOCK_MAX_SOC, number_value(self.hass, "min_soc_for_pv_export", 20.0))
        if soc_first < min_soc:
            return skip(f"Pomiń — przewidywany SOC {soc_first:.0f}% < {min_soc:.0f}%: bateria potrzebuje ładowania z PV.")

        def gain(run: list[int]) -> float:
            return sum(pv[h] * (prices[h] - p_ref) for h in run)

        best_reason = None
        for run in sorted(runs, key=gain, reverse=True):
            end = run[-1] + 1
            later = [h for h in range(end, 24) if (pv[h] or 0) > 0]
            # w czasie blokady PV idzie na sprzedaż, więc dom jedzie z baterii
            soc_end = max(float(HARD_FLOOR_SOC), max(ctx["inv_floor_h"][h] for h in run),
                          soc_first - sum(self._load_abs(ctx, day * 24 + h) for h in run) / cap * 100.0)
            need_kwh = max(0.0, (ctx["target_cfg"] - soc_end) / 100.0 * cap)
            surplus = sum(max(0.0, pv[h] - self._load_abs(ctx, day * 24 + h)) for h in later)
            if surplus < need_kwh * 1.15 + 0.5:
                best_reason = (f"blokada {run[0]:02d}–{end:02d} zostawiłaby tylko ~{surplus:.1f} kWh nadwyżki PV "
                               f"na dopełnienie baterii (potrzeba ~{need_kwh:.1f} kWh)")
                continue
            export_kwh = sum(pv[h] for h in run)
            avg_price = sum(pv[h] * prices[h] for h in run) / export_kwh
            profit = gain(run)
            reason = (f"Blokuj ładowanie {run[0]:02d}–{end:02d} ({dname}): cena {avg_price:.3f} zł/kWh wobec średniej "
                      f"{p_ref:.3f} w godzinach PV; ~{export_kwh:.1f} kWh PV pójdzie na sprzedaż "
                      f"(+{profit:.2f} zł), a bateria dopełni się z późniejszej nadwyżki PV (~{surplus:.1f} kWh).")
            conf = "high" if len(run) >= 2 and profit >= 0.5 else "medium"
            out["pv_export_start"] = self._p("pv_export_start", self._read_current_time("pv_export_start"),
                                             f"{run[0]:02d}:00", reason, conf)
            out["pv_export_stop"] = self._p("pv_export_stop", self._read_current_time("pv_export_stop"),
                                            self._fmt_stop(end), reason, conf)
            return out
        return skip(f"Pomiń — {best_reason or 'brak opłacalnej blokady'}.")
