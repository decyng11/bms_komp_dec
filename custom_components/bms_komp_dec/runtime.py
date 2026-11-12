"""Rdzeń logiki EMS komp-dec.

Zawiera: wykonywanie komend na falowniku (z odczytem zwrotnym), harmonogram (dni tygodnia,
święta), zabezpieczenia sprzedaży, reakcję na niskie/ujemne ceny RCE, sprawdzanie
opłacalności, dynamiczną rezerwę SOC, dziennik decyzji i księgę zysków.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATTERY_CAPACITY_KWH, CONF_GRID_POWER, CONF_PRICE_BUY_ENTITY, CONF_PRICE_SELL_ENTITY, CONF_SOC,
    DEFAULT_BATTERY_CAPACITY_KWH, DEFAULT_PRICE_BUY_ENTITY, DEFAULT_PRICE_SELL_ENTITY, WEEKDAY_SWITCH_KEYS,
)
from . import inbox
from .gridlimit import GridLimiter
from . import brands
from . import inverter_ctl as ictl
from .battery_sign import SignLearner
from .battery_stats import BatteryStats
from .decision_log import DecisionLog
from .diag_store import DiagStore
from . import devices as devmod
from .helpers import (
    ThrottledStore, find_eid, normalize_price, number_value, state_float, state_str, switch_on,
)
from .holidays_pl import holiday_name, is_holiday
from .device_ctl import DeviceController
from .insights import Insights
from .repairs_bms import Repairs
from .ledger import Ledger
from . import money as money_mod
from .tariff import get_profile
from .monitor import Monitor
from . import report as report_mod
from .reserve import compute_reserve
from .inverter_floor import floor_profile
from .watch import WriteWatch

_LOGGER = logging.getLogger(__name__)

# (time_key, switch_key, button_key, soc_key, is_stop)
SCHEDULE_RULES = [
    ("bateria_sprzedaz_start",   "bateria_sprzedaz_1", "sprzedaz_6000w",       "min_soc_for_sell",        False),
    ("bateria_sprzedaz_stop",    "bateria_sprzedaz_1", "nadwyzka_9700w",       None,                      True),
    ("bateria_sprzedaz_start_2", "bateria_sprzedaz_2", "sprzedaz_6000w",       "min_soc_for_sell",        False),
    ("bateria_sprzedaz_stop_2",  "bateria_sprzedaz_2", "nadwyzka_9700w",       None,                      True),
    ("pv_export_start", None, "eksport_pv_blokada",    "min_soc_for_pv_export", False),
    ("pv_export_stop",  None, "przywroc_ladowanie",    None,                    False),
    ("start_grid_charge",   "ladowanie_z_sieci_1", "wlacz_ladowanie_siec",  None, False),
    ("stop_grid_charge",    "ladowanie_z_sieci_1", "wylacz_ladowanie_siec", None, True),
    ("start_grid_charge_2", "ladowanie_z_sieci_2", "wlacz_ladowanie_siec",  None, False),
    ("stop_grid_charge_2",  "ladowanie_z_sieci_2", "wylacz_ladowanie_siec", None, True),
]

STOP_PARTNER = {
    "bateria_sprzedaz_stop": "bateria_sprzedaz_start",
    "bateria_sprzedaz_stop_2": "bateria_sprzedaz_start_2",
    "stop_grid_charge": "start_grid_charge",
    "stop_grid_charge_2": "start_grid_charge_2",
}

# Reguły "start" podlegają filtrowi dni tygodnia/świąt; reguły "stop" zawsze działają
# (przywracają bezpieczny stan i nic nie kosztują).
START_KEYS = {
    "bateria_sprzedaz_start", "bateria_sprzedaz_start_2", "pv_export_start",
    "start_grid_charge", "start_grid_charge_2",
}

SOC_DEFAULTS = {
    "min_soc_for_sell": 50.0,
    "min_soc_for_pv_export": 20.0,
    "min_soc_for_pv_export_stop": 5.0,
}

DEFAULT_SELL_BLOCK_W = 2000.0
SELLING_TOKEN = "__sprzedaz__"     # zapamiętany „tryb” przy falownikach bez trybu Export First (Sofar)
PRICE_HYSTERESIS = 0.02          # PLN/kWh powyżej progu, by uznać cenę za "wróconą do normy"
GUARD_COOLDOWN_S = 120
VERIFY_FIRST_WAIT_S = 20
VERIFY_SECOND_WAIT_S = 30
PROFIT_REF_TTL_S = 300
RESERVE_TTL_S = 60
PLAN_TTL_S = 900
PLAN_ERROR_TTL_S = 20      # plan z błędem (np. SOC jeszcze niedostępny po restarcie) ponawiamy szybko, nie po 15 min

COMMAND_LABELS = {
    "sprzedaz_6000w": "Sprzedaż 6000W",
    "nadwyzka_9700w": "Nadwyżka 9700W (tryb Zero Export)",
    "eksport_pv_blokada": "Eksport PV + blokada ładowania",
    "przywroc_ladowanie": "Przywrócenie ładowania",
    "zablokuj_ladowanie": "Blokada ładowania PV",
    "odblokuj_ladowanie": "Odblokowanie ładowania PV",
    "wlacz_ladowanie_siec": "Włączenie ładowania z sieci",
    "wylacz_ladowanie_siec": "Wyłączenie ładowania z sieci",
}


def _pl(v: float, n: int) -> str:
    """Liczba z przecinkiem dziesiętnym (polski zapis)."""
    return f"{float(v):.{n}f}".replace(".", ",")


class BmsRuntime:
    def __init__(self, hass: HomeAssistant, coordinator, optimizer) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.optimizer = optimizer
        self.log = DecisionLog(hass)
        self.ledger = Ledger(hass)
        self.stats = BatteryStats(hass)
        self.diag_store = DiagStore(hass)
        self.devices = devmod.DeviceManager(hass)
        self.insights = Insights(hass)
        self.dev_ctl = DeviceController(self)
        self.repairs = Repairs(self)
        self.monitor = Monitor(self)
        self.watch = WriteWatch(self)
        self.grid_limiter = GridLimiter(self)
        self.fired: dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        self._cmd_gen = 0
        self._tasks: set[asyncio.Task] = set()
        self._guard_last: dict[str, datetime] = {}
        self._skip_logged: dict[str, str] = {}
        self._profit_ref: tuple[float, float | None] | None = None
        self._reserve_cache: tuple[float, dict[str, Any]] | None = None
        self._plan: dict[str, Any] | None = None           # ostatni plan (krzywa SOC) z optymalizatora
        self._plan_ts = 0.0
        self._plan_lock = asyncio.Lock()
        self._report_cache: tuple[str, dict[str, Any]] | None = None
        self._state_store = ThrottledStore(hass, 1, "bms_komp_dec_runtime", delay=30)
        self.state: dict[str, Any] = {
            "today_date": None, "today_charge": 0.0, "today_pv": 0.0,
            "yesterday_date": None, "yesterday_charge": 0.0, "yesterday_pv": 0.0,
            "price_reaction": {"active": False, "prev_mode": None},
            "last_applied": {},
            "normal_charge_current": None,     # ostatni prąd ładowania > 0 (do „odblokuj ładowanie”)
            "battery_sign_votes": {"pos": 0, "neg": 0},
            "notified": {},                    # klucz powiadomienia → czas ostatniej wysyłki (cooldown po restarcie)
            "alarms_active": {},               # encja alarmu → ostatnio zgłoszony stan
            "watches": [],                     # kontrola wartości po zapisie (watch.py)
            "low_soc_active": False,
            "storm_until": None,               # znacznik czasu końca trybu burzowego
            "vacation_since": None,
            "report_sent": None,               # „RRRR-MM” ostatnio wysłanego raportu miesięcznego
        }
        self._sign = SignLearner()

    # ------------------------------------------------------------ lifecycle
    async def async_load(self) -> None:
        await self.log.async_load()
        await self.ledger.async_load()
        await self.stats.async_load()
        await self.diag_store.async_load()
        try:
            await self.devices.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS: nie udało się wczytać urządzeń: %s", err)
        try:
            await self.insights.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS: nie udało się wczytać historii godzinowej: %s", err)
        lf = getattr(self.coordinator, "load_forecast", None)
        if lf is not None:
            lf.split_hook = lambda f, target, today: devmod.forecast_split(self.devices, f, target, today)
        try:
            data = await self._state_store.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS runtime: błąd wczytywania stanu: %s", err)
            data = None
        if isinstance(data, dict):
            # wszystkie zapisane klucze, nie tylko te z wartościami domyślnymi powyżej — inaczej po restarcie
            # znikały m.in. ustawienia powiadomień (notify_cfg) i znaczniki wysłanych podsumowań
            for k, v in data.items():
                if isinstance(k, str):
                    self.state[k] = v
            pr = self.state.get("price_reaction")
            if not isinstance(pr, dict):
                self.state["price_reaction"] = {"active": False, "prev_mode": None}
            if not isinstance(self.state.get("last_applied"), dict):
                self.state["last_applied"] = {}
            for k in ("notified", "alarms_active"):
                if not isinstance(self.state.get(k), dict):
                    self.state[k] = {}
            if not isinstance(self.state.get("watches"), list):
                self.state["watches"] = []
            self._sign = SignLearner(self.state.get("battery_sign_votes"))

    def _save_state(self) -> None:
        self._state_store.request_save(lambda: dict(self.state))

    def async_shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()

    def _spawn(self, coro) -> None:
        task = self.hass.async_create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # -------------------------------------------------------------- readers
    @property
    def cfg(self) -> dict[str, Any]:
        return self.coordinator.config

    def soc(self) -> float | None:
        val = self.coordinator.get_float_opt(CONF_SOC)
        if val is not None:
            return val
        for eid in ("sensor.bms_soc", "sensor.inverter_battery"):
            val = state_float(self.hass, eid)
            if val is not None:
                return val
        return None

    def grid_power(self) -> float | None:
        raw = self.coordinator.get_float_opt(CONF_GRID_POWER)
        if raw is not None:
            return raw
        gp = (self.coordinator.data or {}).get("grid_power")
        if gp is not None:
            try:
                return float(gp)
            except (TypeError, ValueError):
                pass
        for eid in ("sensor.bms_grid_power", "sensor.inverter_grid_power"):
            val = state_float(self.hass, eid)
            if val is not None:
                return val
        return None

    def eid(self, role: str) -> str:
        """entity_id sterującej encji falownika (config → wykrycie po prefiksie → nazwa domyślna)."""
        return ictl.resolve(self.hass, self.cfg, role)

    def brand(self) -> str:
        """Marka falownika (Deye / Sofar G3 / Sofar hybrydowy) — wykrywana po opcjach trybu pracy."""
        return brands.detect(self.hass, self.cfg)

    def _brand_state(self) -> dict[str, Any]:
        return brands.state(self.hass, self.cfg, self.brand())

    def work_mode(self) -> str | None:
        return state_str(self.hass, self.eid("work_mode"))

    def charge_current(self) -> float | None:
        if self.brand() != brands.DEYE:
            return self._brand_state()["charge_current"]
        return state_float(self.hass, self.eid("charge_current"))

    def tou_state(self) -> str | None:
        return state_str(self.hass, self.eid("tou_select"))

    def is_selling(self) -> bool:
        if self.brand() != brands.DEYE:
            return bool(self._brand_state()["selling"])
        return ictl.matches_option(self.hass, self.eid("work_mode"), self.work_mode(), "export")

    def is_mode_export(self, mode: str | None) -> bool:
        if mode == SELLING_TOKEN:
            return True
        if self.brand() != brands.DEYE:
            return False
        return ictl.matches_option(self.hass, self.eid("work_mode"), mode, "export")

    def grid_charging_on(self) -> bool:
        """Deye: TOU „Disabled” = falownik ładuje z sieci wg ustawień (tak działa „Włącz ładowanie z sieci”)."""
        if self.brand() != brands.DEYE:
            return bool(self._brand_state()["grid_charging"])
        return ictl.matches_option(self.hass, self.eid("tou_select"), self.tou_state(), "tou_off")

    def pv_charge_blocked(self) -> bool:
        """Czy ładowanie baterii z PV jest zablokowane (Deye: prąd ładowania 0 A)."""
        if self.brand() != brands.DEYE:
            return bool(self._brand_state()["pv_blocked"])
        cur = self.charge_current()
        return cur is not None and cur <= 0.1

    def brand_test_mode(self) -> bool:
        """Sofar (sterowanie niesprawdzone na prawdziwym falowniku): komendy tylko do dziennika, dopóki włączone."""
        return self.brand() != brands.DEYE and switch_on(self.hass, "brand_test_mode", True)

    def battery_sign(self) -> dict[str, Any]:
        """Znak mocy baterii przy ładowaniu (ręczny → wykryty z danych → domyślny Deye)."""
        manual = number_value(self.hass, "battery_charge_sign", 0.0)
        return self._sign.result(manual)

    def _learn_battery_sign(self, now: datetime) -> None:
        data = self.coordinator.data or {}
        if self._sign.add(now.timestamp(), self.soc(), data.get("battery_power")):
            self.state["battery_sign_votes"] = dict(self._sign.votes)
            self._save_state()

    def _remember_charge_current(self) -> None:
        cc = self.charge_current()
        if cc is not None and cc > 1 and self.state.get("normal_charge_current") != cc:
            self.state["normal_charge_current"] = cc
            self._save_state()

    def sell_price(self) -> float | None:
        eid = self.optimizer.config.get(CONF_PRICE_SELL_ENTITY, DEFAULT_PRICE_SELL_ENTITY)
        return normalize_price(state_float(self.hass, eid))

    def buy_price(self) -> float | None:
        eid = self.optimizer.config.get(CONF_PRICE_BUY_ENTITY, DEFAULT_PRICE_BUY_ENTITY)
        val = state_float(self.hass, eid)
        if val is not None and 0 < val <= 20:
            return val
        try:
            return float(self.optimizer.tariff.get_price(dt_util.now()))
        except Exception:  # noqa: BLE001
            return None

    # ----------------------------------------------- bilans 2-dniowy (arbitraż)
    def update_daily_snapshot(self, now: datetime) -> None:
        """Na bieżąco zapamiętuje dzisiejsze liczniki; o północy staje się to 'wczoraj'.

        Zastępuje pojedynczy snapshot o 23:59:30, który ginął przy restarcie HA."""
        data = self.coordinator.data or {}
        charge = data.get("energy_battery_charge_today")
        pv = data.get("energy_pv_today")
        if charge is None or pv is None:
            return
        today = dt_util.as_local(now).date().isoformat()
        st = self.state
        if st.get("today_date") != today:
            prev = st.get("today_date")
            if prev:
                st["yesterday_date"] = prev
                st["yesterday_charge"] = float(st.get("today_charge") or 0.0)
                st["yesterday_pv"] = float(st.get("today_pv") or 0.0)
                self.log.add(
                    "system",
                    f"Nowy dzień: wczoraj ładowanie baterii {st['yesterday_charge']:.1f} kWh, "
                    f"PV {st['yesterday_pv']:.1f} kWh",
                )
            st["today_date"] = today
            st["today_charge"] = float(charge)
            st["today_pv"] = float(pv)
            self._save_state()
            return
        changed = False
        if float(charge) > float(st.get("today_charge") or 0.0):
            st["today_charge"] = float(charge)
            changed = True
        if float(pv) > float(st.get("today_pv") or 0.0):
            st["today_pv"] = float(pv)
            changed = True
        if changed:
            self._save_state()

    def charge_2d(self) -> tuple[float | None, float | None]:
        data = self.coordinator.data or {}
        charge = data.get("energy_battery_charge_today")
        pv = data.get("energy_pv_today")
        if charge is None or pv is None:
            return None, None
        today = dt_util.now().date()
        y_ok = self.state.get("yesterday_date") == (today - timedelta(days=1)).isoformat()
        yc = float(self.state.get("yesterday_charge") or 0.0) if y_ok else 0.0
        ypv = float(self.state.get("yesterday_pv") or 0.0) if y_ok else 0.0
        return float(charge) + yc, float(pv) + ypv

    def arbitrage_status(self) -> tuple[bool, str]:
        c2, p2 = self.charge_2d()
        if c2 is None or p2 is None:
            return False, ""
        tol = number_value(self.hass, "grid_arbitrage_block_kwh", 0.5)
        if tol <= 0:
            return False, ""
        if c2 > p2 + tol:
            return True, (f"ładowanie baterii {c2:.1f} kWh > produkcja PV {p2:.1f} kWh (bilans 2-dniowy)")
        return False, ""

    def storm_active(self) -> bool:
        return switch_on(self.hass, "storm_mode", False)

    def vacation_active(self) -> bool:
        return switch_on(self.hass, "vacation_mode", False)

    def sell_block_reason(self, strict_grid: bool = False) -> str | None:
        """Powód zakazu sprzedaży (tryb burzowy / import z sieci / arbitraż) albo None.

        strict_grid=True: brak odczytu mocy sieci również blokuje (start z harmonogramu)."""
        if self.storm_active():
            return "tryb burzowy — energia zostaje w baterii (rezerwa 100%)"
        grid = self.grid_power()
        limit = number_value(self.hass, "grid_import_sell_block_w", DEFAULT_SELL_BLOCK_W)
        if limit > 0:
            if grid is None:
                if strict_grid:
                    return "brak odczytu mocy z sieci — nie można potwierdzić braku importu"
            elif grid > limit:
                return f"import z sieci {grid:.0f} W > limit {limit:.0f} W"
        day_block = self.daily_import_block()
        if day_block:
            return day_block
        blocked, reason = self.arbitrage_status()
        if blocked:
            return f"arbitraż: {reason}"
        return None

    def import_today_kwh(self) -> float | None:
        """Ile kWh pobrano dziś z sieci: licznik falownika, a gdy go brak — z księgi rozliczeń."""
        raw = (self.coordinator.data or {}).get("energy_grid_import_today")
        try:
            if raw is not None:
                return float(raw)
        except (TypeError, ValueError):
            pass
        day = self.ledger.days.get(dt_util.now().date().isoformat())
        return float(day["import_kwh"]) if day else None

    def daily_import_block(self) -> str | None:
        """Blokada sprzedaży według energii z całego dnia: pobrano z sieci więcej niż limit (0 = wyłączona)."""
        limit = number_value(self.hass, "grid_import_sell_block_kwh", 3.0)
        if limit <= 0:
            return None
        imported = self.import_today_kwh()
        if imported is not None and imported > limit:
            return f"dziś pobrano z sieci {imported:.1f} kWh > limit {limit:.1f} kWh"
        return None

    # --------------------------------------------- opłacalność (funkcja 2)
    def profit_status(self) -> dict[str, Any]:
        """{'ok': bool|None, 'net': zł/kWh, 'price', 'ref', 'margin', 'eff'} — ok=None gdy brak danych."""
        price = self.sell_price()
        now_ts = dt_util.now().timestamp()
        if self._profit_ref is None or now_ts - self._profit_ref[0] > PROFIT_REF_TTL_S:
            try:
                ref = self.optimizer.profit_reference()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("EMS profit_reference: %s", err)
                ref = None
            self._profit_ref = (now_ts, ref)
        ref = self._profit_ref[1]
        eff = min(1.0, max(0.5, number_value(self.hass, "cycle_efficiency", 90.0) / 100.0))
        margin = number_value(self.hass, "min_sell_margin", 0.15)
        try:
            wear = float(self.optimizer.wear_cost()) if hasattr(self.optimizer, "wear_cost") else 0.0
        except Exception:  # noqa: BLE001
            wear = 0.0
        out: dict[str, Any] = {"ok": None, "price": price, "ref": ref, "margin": margin, "eff": eff, "net": None, "wear": wear}
        if price is None:
            return out
        if price <= 0:
            out.update(ok=False, net=price * eff - (ref or 0.0) - wear)
            return out
        if ref is None:
            out["net"] = price * eff - wear
            out["ok"] = out["net"] >= margin
            return out
        net = price * eff - ref - wear
        out.update(net=net, ok=net >= margin)
        return out

    # --------------------------------------------- dynamiczna rezerwa (funkcja 3)
    def reserve(self) -> dict[str, Any]:
        if self.storm_active():       # tryb burzowy: cała energia zostaje w baterii (zasilanie awaryjne)
            cap = float(self.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
            return {"pct": 100.0, "need_kwh": round(cap, 2), "until_hour": None, "hours": 0,
                    "enabled": True, "storm": True}
        now_ts = dt_util.now().timestamp()
        if self._reserve_cache and now_ts - self._reserve_cache[0] < RESERVE_TTL_S:
            return self._reserve_cache[1]
        lf = (self.coordinator.data or {}).get("load_forecast") or {}
        hourly = lf.get("hourly_forecast")
        if not (isinstance(hourly, list) and len(hourly) == 24):
            tf = lf.get("tomorrow_forecast")
            hourly = [tf / 24.0] * 24 if isinstance(tf, (int, float)) and tf > 0 else None
        try:
            pv_hourly = self.optimizer.pv_hourly_today()
            scale = self.optimizer.pv_scale_next_day()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS reserve: brak prognozy PV: %s", err)
            pv_hourly, scale = None, 1.0
        now_h = dt_util.now().hour
        rem = lf.get("hourly_remaining_today")
        if hourly and isinstance(rem, list) and len(rem) == 24:
            # do północy: ile dom zużyje jeszcze dziś (tempo dnia); godziny po północy — profil jutra
            hourly = [rem[h] if (h >= now_h and isinstance(rem[h], (int, float)) and not isinstance(rem[h], bool))
                      else hourly[h] for h in range(24)]
        inv = self.inverter_floor()
        floor_ahead = max(inv["hourly"][(now_h + i) % 24] for i in range(13))   # próg odcięcia falownika w najbliższych godzinach
        res = compute_reserve(
            now_hour=now_h,
            capacity_kwh=float(self.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH)),
            floor_pct=max(number_value(self.hass, "reserve_floor_soc", 15.0), floor_ahead),
            load_hourly=hourly,
            pv_hourly=pv_hourly,
            pv_scale_next_day=scale,
        )
        res["enabled"] = switch_on(self.hass, "dynamic_reserve", False)
        self._reserve_cache = (now_ts, res)
        return res

    def inverter_floor(self) -> dict:
        """Rzeczywisty próg odcięcia baterii w falowniku (profil godzinowy)."""
        try:
            return floor_profile(self.hass)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: próg odcięcia falownika niedostępny: %s", err)
            return {"hourly": [0.0] * 24, "shutdown": None, "source": "brak danych", "manual": 0.0, "programs": []}

    def sell_soc_threshold(self) -> float:
        if self.storm_active():
            return 100.0
        base = number_value(self.hass, "min_soc_for_sell", SOC_DEFAULTS["min_soc_for_sell"])
        if switch_on(self.hass, "dynamic_reserve", False):
            return max(base, float(self.reserve()["pct"]))
        return base

    # ----------------------------------------------- dni tygodnia + święta (funkcja 7)
    def day_info(self, now: datetime) -> tuple[bool, str, bool]:
        d = dt_util.as_local(now).date()
        hol = is_holiday(d)
        idx = 6 if (hol and switch_on(self.hass, "holidays_as_sunday", True)) else d.weekday()
        key = WEEKDAY_SWITCH_KEYS[idx]
        return switch_on(self.hass, key, True), key, hol

    # --------------------------------------------------- komendy na falowniku
    def _steps(self, key: str) -> list[tuple[str, str, Any]]:
        """Kroki komendy z już rozwiązanymi encjami, nazwami opcji i wartościami (przyciętymi do zakresu encji)."""
        h = self.hass
        brand = self.brand()
        if brand != brands.DEYE:
            sell_w, chg_w, dis_w = brands.powers(h, self.optimizer.config if isinstance(getattr(self.optimizer, "config", None), dict) else {})
            cc_eid = brands.role_eid(h, self.cfg, brand, "charge_current") if brand == brands.SOFAR_HYBRID else None
            normal_cur = ictl.normal_charge_current(h, cc_eid, self.state.get("normal_charge_current")) if cc_eid else None
            try:
                return brands.steps(h, self.cfg, brand, key, sell_w=sell_w, charge_w=chg_w, discharge_w=dis_w,
                                    normal_current=normal_cur)
            except brands.StepError as err:
                raise HomeAssistantError(str(err)) from err
        wm, cc = self.eid("work_mode"), self.eid("charge_current")
        ex, tou = self.eid("export_surplus"), self.eid("tou_select")

        def opt(eid: str, kind: str) -> str:
            val = ictl.pick_option(h, eid, kind)
            if val is None:
                raise HomeAssistantError(
                    f"encja {eid} nie ma oczekiwanej opcji ({' / '.join(ictl.OPTION_CANDIDATES[kind])}); "
                    f"dostępne: {', '.join(ictl.options_of(h, eid) or [])}")
            return val

        def normal() -> float:
            return ictl.normal_charge_current(h, cc, self.state.get("normal_charge_current"))

        def sell_w() -> float:
            w = ictl.power_setting(h, ex, "sell_export_power_w", 6000.0)
            cap_w = self.planned_sale_power_w()          # plan obniżył moc, by sprzedać tylko zapas energii
            return min(w, cap_w) if cap_w else w

        def surplus_w() -> float:
            return ictl.power_setting(h, ex, "surplus_power_w", 9700.0)

        def num(v: float) -> float:
            return int(v) if float(v).is_integer() else round(float(v), 1)

        builders = {
            "sprzedaz_6000w": lambda: [("select", wm, opt(wm, "export")), ("number", ex, num(sell_w()))],
            "nadwyzka_9700w": lambda: [("select", wm, opt(wm, "zero")), ("number", ex, num(surplus_w()))],
            "eksport_pv_blokada": lambda: [("number", cc, 0)],
            "przywroc_ladowanie": lambda: [
                ("number", cc, num(normal())),
                ("select", wm, opt(wm, "zero")),
                ("number", ex, num(surplus_w())),
            ],
            "zablokuj_ladowanie": lambda: [("number", cc, 0)],
            "odblokuj_ladowanie": lambda: [("number", cc, num(normal()))],
            # prąd ładowania 0 A (blokada ładowania z PV) blokuje też ładowanie z sieci — przy starcie okna go przywracamy
            "wlacz_ladowanie_siec": lambda: ([("number", cc, num(normal()))] if self.pv_charge_blocked() else [])
                                            + [("select", tou, opt(tou, "tou_off"))],
            "wylacz_ladowanie_siec": lambda: [("select", tou, opt(tou, "tou_on"))],
        }
        build = builders.get(key)
        return build() if build else []

    async def _call(self, domain: str, eid: str, value: Any) -> None:
        if domain == "time":
            await self.hass.services.async_call("time", "set_value", {"entity_id": eid, "time": value}, blocking=True)
            return
        if domain == "select":
            await self.hass.services.async_call(
                "select", "select_option", {"entity_id": eid, "option": value}, blocking=True)
        else:
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": eid, "value": value}, blocking=True)

    async def run_command(self, key: str, source: str = "ręcznie", enforce_guard: bool = True) -> None:
        """Wykonuje komendę przycisku. Zgłasza HomeAssistantError przy zakazie/błędzie."""
        label = COMMAND_LABELS.get(key, key)
        try:
            steps = self._steps(key)
        except HomeAssistantError as err:
            self.log.add("command", f"{label} ({source}): {err}", "error")
            raise HomeAssistantError(f"{label}: {err}") from err
        if not steps:
            _LOGGER.warning("EMS: nieznana komenda %s", key)
            return
        # Żaden krok nie jest wykonywany, dopóki wszystkie encje nie istnieją — komenda nie zostaje „w połowie”.
        missing = [eid for _d, eid, _v in steps if self.hass.states.get(eid) is None]
        if missing:
            msg = (f"nie znaleziono encji falownika: {', '.join(dict.fromkeys(missing))} — "
                   f"wskaż właściwe encje w konfiguracji integracji (Zmień konfigurację → „Wykryj encje ponownie”)")
            self.log.add("command", f"{label} ({source}): {msg}", "error")
            raise HomeAssistantError(f"{label}: {msg}")
        if key == "sprzedaz_6000w" and enforce_guard:
            reason = self.sell_block_reason(strict_grid=not source.startswith("ręcznie"))
            if reason:
                self.log.add("guard", f"{label} ({source}) ZABLOKOWANA: {reason}", "warn")
                raise HomeAssistantError(f"Sprzedaż zablokowana: {reason}.")
        if self.brand_test_mode():
            plan = "; ".join(f"{eid} = {value}" for _d, eid, value in steps)
            self.log.add("command", f"TRYB PRÓBNY ({brands.LABELS.get(self.brand(), self.brand())}) — {label} ({source}): "
                                    f"ustawiłbym {plan}. Nic nie zapisano; wyłącz switch.bms_brand_test_mode, gdy kroki są właściwe.", "info")
            return
        async with self._lock:
            self._cmd_gen += 1
            gen = self._cmd_gen
            for domain, eid, value in steps:
                try:
                    await self._call(domain, eid, value)
                except Exception as err:  # noqa: BLE001
                    self.log.add("command", f"{label} ({source}): błąd {eid}={value}: {err}", "error")
                    raise HomeAssistantError(f"{label}: nie udało się ustawić {eid}: {err}") from err
        self.log.add("command", f"{label} ({source})", "ok")
        if switch_on(self.hass, "readback_verify", True):
            self._spawn(self._verify(key, label, steps, gen))

    def _mismatches(self, steps: list[tuple[str, str, Any]]) -> list[tuple[str, str, Any]]:
        bad = []
        for domain, eid, value in steps:
            st = self.hass.states.get(eid)
            if st is None or str(st.state).lower() in ("unknown", "unavailable", "none", ""):
                bad.append((domain, eid, value))
                continue
            if domain == "select":
                if str(st.state).strip().lower() != str(value).strip().lower():
                    bad.append((domain, eid, value))
            elif domain == "time":
                if str(st.state)[:5] != str(value)[:5]:
                    bad.append((domain, eid, value))
            else:
                try:
                    actual = float(st.state)
                except (TypeError, ValueError):
                    bad.append((domain, eid, value))
                    continue
                expected = float(value)
                mx = (st.attributes or {}).get("max")
                try:
                    if mx is not None:
                        expected = min(expected, float(mx))
                except (TypeError, ValueError):
                    pass
                if abs(actual - expected) > 0.5:
                    bad.append((domain, eid, value))
        return bad

    async def _verify(self, key: str, label: str, steps: list[tuple[str, str, Any]], gen: int) -> None:
        """Sprawdza po czasie, czy falownik faktycznie przyjął komendę; raz ponawia."""
        try:
            await asyncio.sleep(VERIFY_FIRST_WAIT_S)
            if gen != self._cmd_gen:
                return  # w międzyczasie wydano nowszą komendę — nie nadpisuj
            bad = self._mismatches(steps)
            if not bad:
                self.log.add("verify", f"{label}: stan falownika potwierdzony", "ok")
                return
            desc = ", ".join(f"{e}≠{v}" for _d, e, v in bad)
            self.log.add("verify", f"{label}: rozbieżność ({desc}) — ponawiam komendę", "warn")
            for domain, eid, value in bad:
                try:
                    await self._call(domain, eid, value)
                except Exception as err:  # noqa: BLE001
                    self.log.add("verify", f"{label}: ponowienie {eid} nieudane: {err}", "error")
            await asyncio.sleep(VERIFY_SECOND_WAIT_S)
            if gen != self._cmd_gen:
                return
            bad = self._mismatches(steps)
            if bad:
                desc = ", ".join(f"{e}≠{v}" for _d, e, v in bad)
                self.log.add("verify", f"{label}: falownik NIE potwierdził zmiany ({desc})", "error")
                await self.monitor.notifier.send(
                    "command_unconfirmed", "⚠ EMS: falownik nie potwierdził komendy",
                    f"{label}: po komendzie i ponowieniu stan się nie zgadza ({desc}). Sprawdź falownik.",
                    key=f"cmd:{key}", level="error")
            else:
                self.log.add("verify", f"{label}: potwierdzone po ponowieniu", "ok")
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS verify: %s", err, exc_info=True)

    # --------------------------------------------------------------- harmonogram
    def _log_skip(self, time_key: str, now_hm: str, msg: str, level: str = "info") -> None:
        marker = f"{now_hm}|{msg}"
        if self._skip_logged.get(time_key) == marker:
            return
        self._skip_logged[time_key] = marker
        self.log.add("schedule", f"Pominięto {time_key}: {msg}", level)
        if time_key in START_KEYS:
            self._spawn(self.monitor.notifier.send("schedule_skipped", "⏭ EMS: pominięty start harmonogramu",
                                                   f"{now_hm} {time_key}: {msg}", key=f"skip:{time_key}", level="info"))

    @staticmethod
    def due_times(now: datetime) -> set[str]:
        """Godziny HH:MM, których reguły są teraz „na czasie”: bieżąca minuta, a tuż po wiosennej zmianie czasu
        (02:00 → 03:00) także cała nieistniejąca godzina 02:xx — inaczej np. STOP ładowania o 02:00 nigdy by nie zadziałał."""
        due = {now.strftime("%H:%M")}
        off = now.utcoffset()
        prev = (now.astimezone(timezone.utc) - timedelta(minutes=2)).astimezone(now.tzinfo)
        poff = prev.utcoffset()
        if off is not None and poff is not None and off > poff:
            gap = int((off - poff).total_seconds() // 60)
            t0 = now.replace(minute=0, second=0, microsecond=0, tzinfo=None) - timedelta(minutes=gap)
            due.update((t0 + timedelta(minutes=i)).strftime("%H:%M") for i in range(gap))
        return due

    GC_WINDOWS = (("start_grid_charge", "stop_grid_charge", "ladowanie_z_sieci_1"),
                  ("start_grid_charge_2", "stop_grid_charge_2", "ladowanie_z_sieci_2"))

    def in_grid_charge_window(self, now: datetime) -> bool:
        """Czy teraz trwa zaplanowane okno ładowania z sieci (zestaw włączony, Start–Stop ustawione i różne od 00:00)."""
        cur = dt_util.as_local(now).strftime("%H:%M")
        for start_key, stop_key, sw_key in self.GC_WINDOWS:
            sw = self.hass.states.get(find_eid(self.hass, "switch", sw_key))
            ts = self.hass.states.get(find_eid(self.hass, "time", start_key))
            te = self.hass.states.get(find_eid(self.hass, "time", stop_key))
            if not sw or sw.state != "on" or not ts or not te:
                continue
            s_hm, e_hm = str(ts.state)[:5], str(te.state)[:5]
            if "00:00" in (s_hm, e_hm) or ":" not in s_hm or ":" not in e_hm or s_hm == e_hm:
                continue
            if (s_hm <= cur < e_hm) if s_hm < e_hm else (cur >= s_hm or cur < e_hm):
                return True
        return False

    async def _catchup_grid_windows(self, now: datetime) -> None:
        """Okno ładowania z sieci już trwa, a jego START nie zadziałał (np. zatwierdzono propozycję o 05:13 dla okna 05:00–06:00,
        albo restart HA w trakcie okna) — włącz ładowanie teraz, raz na okno. Reguły czasowe łapią tylko dokładną minutę startu."""
        day_ok = self.day_info(now)[0]
        if not day_ok:
            return
        for start_key, stop_key, sw_key in self.GC_WINDOWS:
            try:
                sw = self.hass.states.get(find_eid(self.hass, "switch", sw_key))
                ts = self.hass.states.get(find_eid(self.hass, "time", start_key))
                te = self.hass.states.get(find_eid(self.hass, "time", stop_key))
                if not sw or sw.state != "on" or not ts or not te:
                    continue
                s_hm, e_hm = str(ts.state)[:5], str(te.state)[:5]
                if "00:00" in (s_hm, e_hm) or ":" not in s_hm or ":" not in e_hm or s_hm == e_hm:
                    continue
                cur = now.strftime("%H:%M")
                inside = (s_hm <= cur < e_hm) if s_hm < e_hm else (cur >= s_hm or cur < e_hm)
                if not inside or cur == s_hm:
                    continue                      # poza oknem albo minuta startu (obsłuży zwykła reguła)
                stamp = f"{now.date().isoformat()} {s_hm}-{e_hm}"
                done = self.state.setdefault("gc_catchup", {})
                if done.get(start_key) == stamp or self.grid_charging_on():
                    done[start_key] = stamp       # już ładuje (np. ręcznie / „Wymuś”) — nic nie rób
                    continue
                done[start_key] = stamp
                self._save_state()
                self.fired[start_key] = now
                await self.run_command("wlacz_ladowanie_siec", source=f"harmonogram {start_key} (nadrobienie {cur})", enforce_guard=False)
                await self.monitor.notifier.send(
                    "grid_charge", "🔌 EMS: start ładowania z sieci (w trakcie okna)",
                    f"{cur} — okno {s_hm}–{e_hm} już trwało, więc włączono ładowanie od razu.", key=f"gc:{start_key}", level="info")
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS SCHEDULE: nadrabianie okna %s: %s", start_key, err)

    async def process_rules(self, now: datetime, dry_run: bool = False) -> dict[str, Any]:
        now = dt_util.as_local(now)
        if not dry_run:
            await self._catchup_grid_windows(now)
        now_hm = now.strftime("%H:%M")
        due = self.due_times(now)
        soc_val = self.soc()
        results: list[dict[str, Any]] = []
        day_ok, day_key, is_hol = self.day_info(now)
        recurring = switch_on(self.hass, "recurring_schedule", False)
        pr = self.state["price_reaction"]
        lg = _LOGGER.warning if dry_run else _LOGGER.debug

        if dry_run:
            _LOGGER.warning(
                "EMS TEST (dry-run): godzina=%s SOC=%s%% dzień=%s (%s) święto=%s cykliczny=%s",
                now_hm, soc_val, day_key, "aktywny" if day_ok else "wyłączony", is_hol, recurring,
            )

        for time_key, switch_key, button_key, soc_key, is_stop in SCHEDULE_RULES:
            time_eid = find_eid(self.hass, "time", time_key)
            button_eid = find_eid(self.hass, "button", button_key)
            switch_eid = find_eid(self.hass, "switch", switch_key) if switch_key else None

            t_st = self.hass.states.get(time_eid)
            t_val = str(t_st.state) if t_st else "BRAK"
            sw = self.hass.states.get(switch_eid) if switch_eid else None
            sw_state = (sw.state if sw else "BRAK") if switch_eid else None

            if dry_run:
                _LOGGER.warning(
                    "EMS TEST: %s=%s | switch(%s)=%s | -> %s | SOC_now=%s",
                    time_eid, t_val, switch_eid or "—", sw_state or "—", button_eid, soc_val,
                )

            if not t_st or t_val in ("unknown", "unavailable", "", "BRAK"):
                continue
            if t_val[:5] == "00:00" or t_val[:5] not in due:
                continue
            if now.fold and not dry_run:        # jesienna zmiana czasu: godzina 02:xx powtarza się, a reguły wykonały się w pierwszym przejściu
                continue

            last = self.fired.get(time_key)
            if not dry_run and last is not None and (now - last).total_seconds() < 90:
                continue

            # --- filtr dni tygodnia / świąt (tylko starty)
            if time_key in START_KEYS and not day_ok:
                why = "święto" if is_hol else "dzień tygodnia"
                self._log_skip(time_key, now_hm, f"harmonogram wyłączony dla dnia ({why}: {day_key})")
                continue

            # --- próg SOC (dla sprzedaży: dynamiczna rezerwa)
            if soc_key is not None:
                thr = (self.sell_soc_threshold() if button_key == "sprzedaz_6000w"
                       else number_value(self.hass, soc_key, SOC_DEFAULTS.get(soc_key, 0.0)))
                if soc_val is None:
                    self._log_skip(time_key, now_hm, "SOC nieznany", "warn")
                    lg("EMS SCHEDULE: SKIP %s — SOC nieznany", time_key)
                    continue
                if soc_val < thr:
                    self._log_skip(time_key, now_hm, f"SOC {soc_val:.0f}% < próg {thr:.0f}%")
                    lg("EMS SCHEDULE: SKIP %s — SOC %.1f%% < próg %.1f%%", time_key, soc_val, thr)
                    continue

            # --- przełącznik zestawu
            started_recently = False
            if switch_key and sw_state != "on":
                partner = STOP_PARTNER.get(time_key)
                started = self.fired.get(partner) if partner else None
                started_recently = started is not None and (now - started).total_seconds() < 24 * 3600
                if not (is_stop and started_recently):
                    lg("EMS SCHEDULE: SKIP %s — przełącznik %s = %s", time_key, switch_eid, sw_state)
                    continue

            # --- zabezpieczenia startu sprzedaży
            if button_key == "sprzedaz_6000w":
                reason = self.sell_block_reason(strict_grid=True)
                if reason:
                    self._log_skip(time_key, now_hm, f"zakaz sprzedaży — {reason}", "warn")
                    continue
                if switch_on(self.hass, "negative_price_reaction", False):
                    price = self.sell_price()
                    thr_p = number_value(self.hass, "low_price_threshold", 0.0)
                    if price is not None and price < thr_p:
                        self._log_skip(time_key, now_hm,
                                       f"cena RCE {price:.3f} < próg {thr_p:.3f} PLN/kWh", "warn")
                        continue
                if switch_on(self.hass, "profit_check", False):
                    ps = self.profit_status()
                    if ps["ok"] is False:
                        self._log_skip(
                            time_key, now_hm,
                            f"sprzedaż nieopłacalna (cena {ps['price']:.3f}, sprawność {ps['eff']:.0%}, "
                            f"ref. {(ps['ref'] or 0):.3f}, marża min. {ps['margin']:.2f} PLN/kWh)", "warn")
                        continue

            if not self.hass.states.get(button_eid):
                _LOGGER.warning("EMS SCHEDULE: BRAK przycisku %s", button_eid)
                continue

            if dry_run:
                _LOGGER.warning("EMS TEST: %s -> ZADZIAŁAŁBY %s", time_eid, button_eid)
                results.append({"time_key": time_key, "button": button_eid, "fired": False, "dry_run": True})
                continue

            self.fired[time_key] = now
            try:
                await self.run_command(button_key, source=f"harmonogram {time_key} {now_hm}", enforce_guard=False)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS SCHEDULE: błąd %s: %s", button_eid, err)
                self.fired.pop(time_key, None)
                results.append({"time_key": time_key, "button": button_eid, "fired": False, "error": str(err)})
                continue

            await self._notify_fired(time_key, button_key, now_hm, soc_val)

            if button_key == "nadwyzka_9700w" and pr.get("active"):
                pr["prev_mode"] = None      # sprzedaż zakończona harmonogramem — nie przywracaj po cenach
                self._save_state()

            if is_stop and switch_eid and not recurring:
                try:
                    await self.hass.services.async_call("switch", "turn_off", {"entity_id": switch_eid}, blocking=True)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("EMS SCHEDULE: off %s: %s", switch_eid, err)

            results.append({"time_key": time_key, "button": button_eid, "fired": True})

        return {"checked_at": now_hm, "results": results}

    async def _notify_fired(self, time_key: str, button_key: str, now_hm: str, soc: float | None) -> None:
        """Powiadomienia o wykonanej regule harmonogramu (sprzedaż / ładowanie z sieci) i o celu ładowania."""
        n = self.monitor.notifier
        soc_txt = f" SOC {soc:.0f}%." if soc is not None else ""
        set_no = "2" if time_key.endswith("_2") else "1"
        if button_key == "sprzedaz_6000w":
            await n.send("sale", "💰 EMS: start sprzedaży z baterii", f"{now_hm} — zestaw {set_no}.{soc_txt}", key=f"sale:{time_key}", level="info")
        elif button_key == "nadwyzka_9700w" and time_key.startswith("bateria_sprzedaz_stop"):
            await n.send("sale", "💰 EMS: koniec sprzedaży z baterii", f"{now_hm} — zestaw {set_no}.{soc_txt}", key=f"sale:{time_key}", level="info")
        elif button_key == "wlacz_ladowanie_siec":
            await n.send("grid_charge", "🔌 EMS: start ładowania z sieci", f"{now_hm} — zestaw {set_no}.{soc_txt}", key=f"gc:{time_key}", level="info")
        elif button_key == "wylacz_ladowanie_siec":
            await n.send("grid_charge", "🔌 EMS: koniec ładowania z sieci", f"{now_hm} — zestaw {set_no}.{soc_txt}", key=f"gc:{time_key}", level="info")
            tgt = self.state.get("grid_target_plan") or {}
            tol = n.cfg()["kinds"]["grid_charge_target"].get("thr", 5.0)
            if soc is not None and isinstance(tgt.get("target"), (int, float)) and soc < float(tgt["target"]) - float(tol):
                await n.send("grid_charge_target", "🔋 EMS: ładowanie z sieci poniżej celu",
                             f"Po ładowaniu z sieci SOC {soc:.0f}%, a plan zakładał ~{float(tgt['target']):.0f}%. "
                             "Sprawdź prąd ładowania z sieci w falowniku i program Time of Use.", key="gc_target")

    # --------------------------------------------------------------- urządzenia
    async def _device_event(self, ev: dict[str, Any]) -> None:
        """Powiadomienia o zdarzeniach urządzeń (koniec cyklu, nietypowa praca, „uruchom teraz”)."""
        d, n = ev["device"], self.monitor.notifier
        name = f"{d.get('icon', '')} {d['name']}".strip()
        if ev["type"] == "cycle" and d.get("notify_cycle"):
            c = ev["cycle"]
            cost = f", koszt {_pl(c['cost'], 2)} zł" if c.get("cost") is not None else ""
            await n.send("device_cycle", f"✅ EMS: {name} — koniec", f"Cykl trwał {c['min']:.0f} min, zużył {_pl(c['kwh'], 2)} kWh{cost}.",
                         key=f"cycle:{d['id']}:{c['start']}", level="info")
        elif ev["type"] == "anomaly" and d.get("notify_anomaly"):
            await n.send("device_anomaly", f"⚠ EMS: {name} pracuje bez przerwy",
                         f"Od {ev['hours']:.1f} h ciągła praca (teraz {ev['power']:.0f} W), limit {d['max_run_h']:.0f} h. Sprawdź urządzenie.",
                         key=f"anom:{d['id']}")
        elif ev["type"] == "hint" and d.get("notify_hint"):
            why = (f"nadwyżka PV — eksport do sieci {ev['export_w'] / 1000:.1f} kW, bateria pełna" if ev["why"] == "surplus"
                   else "trwa jedna z najtańszych godzin doby")
            await n.send("device_hint", f"💡 EMS: dobry moment na {d['name']}", f"Teraz {why}.", key=f"hint:{d['id']}:{ev['why']}", level="info")

    def _cheap_now(self, now: datetime) -> bool:
        """Taryfa dynamiczna: bieżąca godzina jest wśród 3 najtańszych z pozostałych godzin doby."""
        try:
            from .tariff import get_profile
            if not get_profile().dynamic_for(now.date()):
                return False
            arr = self.optimizer.buy_hourly_for(now.date()) or []
            rest = [(h, float(v)) for h, v in enumerate(arr) if h >= now.hour and isinstance(v, (int, float))]
            if len(rest) < 4:
                return False
            cheapest = sorted(rest, key=lambda x: x[1])[:3]
            return any(h == now.hour for h, _v in cheapest)
        except Exception:  # noqa: BLE001
            return False

    async def _devices_tick(self, now: datetime) -> None:
        dm = self.devices
        if not dm.devices:
            return
        loc = dt_util.as_local(now)
        day = loc.date().isoformat()
        for ev in dm.hints(now, self.coordinator.data or {}, self.soc(), self._cheap_now(loc)):
            await self._device_event(ev)
        done = self.state.setdefault("dev_done", {})
        n = self.monitor.notifier
        # wieczorem: plan na jutro dla elastycznych urządzeń
        if loc.strftime("%H:%M") >= "20:00" and done.get("plan") != day:
            done["plan"] = day
            plan = dm.flex_plan(((self.plan() or {}).get("curve")))
            if plan:
                lines = [f"{p['icon']} {p['name']}: {p['start'][11:16]}–{p['end'][11:16]} (~{_pl(p['kwh'], 1)} kWh, {p['why']}, ok. {_pl(p['cost'], 2)} zł)"
                         for p in plan]
                await n.send("device_plan", "🗓 EMS: najlepsze godziny dla urządzeń", "\n".join(lines), key=f"devplan:{day}", level="info")
        # 22:00: zużycie dnia ponad 2× typowe
        if loc.hour >= 22 and done.get("daily_high") != day:
            done["daily_high"] = day
            for d in dm.devices:
                if not d.get("notify_anomaly"):
                    continue
                rec = dm.data.get(d["id"]) or {}
                dl = rec.get("daily") or {}
                hist = [dl[k] for k in dm._days_back(15, loc.date())[1:] if k in dl]  # noqa: SLF001
                today_kwh = dl.get(day, 0.0)
                if len(hist) >= 7:
                    med = sorted(hist)[len(hist) // 2]
                    if today_kwh > max(1.0, 2.0 * med):
                        await n.send("device_anomaly", f"⚠ EMS: {d['name']} — dziś dużo więcej niż zwykle",
                                     f"Dziś {_pl(today_kwh, 1)} kWh, zwykle ok. {_pl(med, 1)} kWh na dobę.", key=f"high:{d['id']}:{day}")
        # raz w tygodniu (poniedziałek 12:00): nierozpoznany odbiornik w „reszcie domu”
        if loc.weekday() == 0 and loc.hour >= 12 and done.get("unknown") != day:
            done["unknown"] = day
            lf = getattr(self.coordinator, "load_forecast", None)
            u = dm.unknown_load(getattr(lf, "profiles", {}) or {}, getattr(lf, "days", {}) or {}) if lf else None
            if u:
                await n.send("devices_unknown", "🔎 EMS: nierozpoznany odbiornik",
                             f"Przez {u['days']} z {u['of']} ostatnich dni ok. {u['hour']:02d}:00 dom pobiera ok. {_pl(u['kwh'], 1)} kWh więcej niż w innych godzinach, "
                             "a żadne dodane urządzenie tego nie tłumaczy. Jeśli wiesz, co to jest, dodaj je w zakładce Urządzenia.",
                             key="unknown")
        # zanik sieci: duży pobór z baterii
        go = self.state.get("grid_outage") or {}
        if go.get("notified"):
            load = (self.coordinator.data or {}).get("load_power")
            thr = (n.cfg()["kinds"].get("island_overload") or {}).get("thr", 5.0)
            if isinstance(load, (int, float)) and load > float(thr) * 1000.0:
                top = ", ".join(f"{nm} {p / 1000:.1f} kW" for nm, p in dm.top_now())
                await n.send("island_overload", "⚡ EMS: duży pobór przy zaniku sieci",
                             f"Dom pobiera {load / 1000:.1f} kW z baterii (próg {float(thr):.1f} kW)." + (f" Największe: {top}." if top else ""),
                             key="island")

    def _remember_grid_target(self, plan: dict[str, Any] | None) -> None:
        """Zapamiętuje cel ładowania z sieci z planu (ostatnia godzina ładowania) — do porównania po STOP."""
        try:
            cur = (plan or {}).get("curve") or {}
            grid, tgt = cur.get("grid") or [], cur.get("target") or []
            idx = [i for i, g in enumerate(grid) if g and i < len(tgt) and isinstance(tgt[i], (int, float))]
            if idx:
                self.state["grid_target_plan"] = {"target": float(tgt[idx[-1]]), "at": plan.get("generated_at")}
        except Exception:  # noqa: BLE001
            pass

    def _remember_sale_power(self, plan: dict[str, Any] | None) -> None:
        """Zapamiętuje okna sprzedaży z planu (start, stop, moc) — plan liczy tylko przyszłe godziny, więc w chwili
        startu okna go już nie ma. Wpisy mają klucz „data|start”; starsze niż wczoraj są usuwane."""
        try:
            today = dt_util.now().date()
            mem = self.state.setdefault("sale_power_plan", {})
            for w in ((plan or {}).get("assumptions") or {}).get("sale_windows") or []:
                d = today + timedelta(days=int(w["day"]))
                mem[f"{d.isoformat()}|{int(w['start']):02d}"] = {"stop": int(w["stop"]), "power_w": w.get("power_w")}
            keep = (today - timedelta(days=1)).isoformat()
            for k in [k for k in mem if k.split("|")[0] < keep]:
                mem.pop(k, None)
        except Exception:  # noqa: BLE001
            pass

    PLAN_LOG_GROUPS = (
        ("ładowanie z sieci (noc)", ("start_grid_charge", "stop_grid_charge")),
        ("ładowanie z sieci (zestaw 2)", ("start_grid_charge_2", "stop_grid_charge_2")),
        ("sprzedaż z baterii (zestaw 1)", ("bateria_sprzedaz_start", "bateria_sprzedaz_stop")),
        ("sprzedaż z baterii (zestaw 2)", ("bateria_sprzedaz_start_2", "bateria_sprzedaz_stop_2")),
        ("blokada ładowania z PV", ("pv_export_start", "pv_export_stop")),
    )

    def _log_plan_decisions(self, plan: dict[str, Any] | None) -> None:
        """Dziennik decyzji: wpis „Plan: …” tylko wtedy, gdy decyzja planu się zmieniła (zaplanowano / pominięto / inne godziny).
        Dzięki temu widać, DLACZEGO plan coś zrobił albo nie zrobił i o której godzinie zmienił zdanie."""
        try:
            props = (plan or {}).get("proposals") or {}
            sigs = self.state.setdefault("plan_sig", {})
            for name, (k1, k2) in self.PLAN_LOG_GROUPS:
                a, b = props.get(k1), props.get(k2)
                if not isinstance(a, dict):
                    continue
                skip = bool(a.get("skip")) or not a.get("proposed")
                sig = ["skip"] if skip else [str(a.get("proposed")), str((b or {}).get("proposed"))]
                if sigs.get(name) == sig:
                    continue
                had = name in sigs
                sigs[name] = sig
                reason = str(a.get("reason") or "").replace("Pomiń — ", "").strip()
                if skip:
                    msg = f"Plan: {name} — pomijam" + (f": {reason[:260]}" if reason else ".")
                    self.log.add("plan", msg, "info", changed=had)
                else:
                    msg = f"Plan: {name} {sig[0]}–{sig[1]}" + (f". {reason[:260]}" if reason else "")
                    self.log.add("plan", msg, "info", changed=had)
        except Exception:  # noqa: BLE001
            pass

    def planned_sale_power_w(self, now: datetime | None = None) -> float | None:
        """Moc sprzedaży z planu dla bieżącej godziny (gdy plan ją obniżył), albo None = bez ograniczenia."""
        try:
            if not switch_on(self.hass, "sale_power_fit", True):
                return None
            now = dt_util.as_local(now or dt_util.now())
            for k, v in (self.state.get("sale_power_plan") or {}).items():
                d, h = k.split("|")
                if d == now.date().isoformat() and int(h) <= now.hour < int(v["stop"]):
                    p = v.get("power_w")
                    return float(p) if isinstance(p, (int, float)) and p >= 500 else None
        except Exception:  # noqa: BLE001
            return None
        return None

    # --------------------------------------------------------------- zabezpieczenia
    def _cooldown_ok(self, name: str, now: datetime) -> bool:
        last = self._guard_last.get(name)
        if last is not None and (now - last).total_seconds() < GUARD_COOLDOWN_S:
            return False
        self._guard_last[name] = now
        return True

    async def enforce_guard(self, now: datetime) -> None:
        soc = self.soc()

        if self.is_selling():
            reasons: list[str] = []
            br = self.sell_block_reason(strict_grid=False)
            if br:
                reasons.append(br)
            if soc is not None:
                stop_soc = number_value(self.hass, "minimalny_soc_dla_wylaczenia_sprzedazy", 20.0)
                label = "minimalny SOC"
                if switch_on(self.hass, "dynamic_reserve", False):
                    res = float(self.reserve()["pct"])
                    if res > stop_soc:
                        stop_soc, label = res, "dynamiczna rezerwa SOC"
                if soc < stop_soc:
                    reasons.append(f"SOC {soc:.0f}% < {label} {stop_soc:.0f}%")
            if reasons and self._cooldown_ok("stop_sale", now):
                self.log.add("guard", "Zatrzymuję sprzedaż: " + "; ".join(reasons), "warn")
                try:
                    await self.run_command("nadwyzka_9700w", source="zabezpieczenie")
                    await self.monitor.notifier.send("guard_action", "🛡 EMS: zabezpieczenie zatrzymało sprzedaż",
                                                     "Powód: " + "; ".join(reasons) + ".", key="guard:sale")
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("EMS GUARD: błąd zatrzymania sprzedaży: %s", err)

        if self.pv_charge_blocked() and soc is not None:
            floor = number_value(self.hass, "min_soc_for_pv_export_stop", SOC_DEFAULTS["min_soc_for_pv_export_stop"])
            if soc < floor and self._cooldown_ok("unblock_charge", now):
                self.log.add("guard", f"SOC {soc:.0f}% < {floor:.0f}% — odblokowuję ładowanie z PV", "warn")
                try:
                    await self.run_command("odblokuj_ladowanie", source="zabezpieczenie")
                    await self.monitor.notifier.send("guard_action", "🛡 EMS: odblokowano ładowanie z PV",
                                                     f"SOC {soc:.0f}% spadł poniżej {floor:.0f}% przy zablokowanym ładowaniu z PV.", key="guard:charge")
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("EMS GUARD: błąd odblokowania ładowania: %s", err)

        # okno ładowania z sieci trwa, a prąd ładowania baterii wynosi 0 A (blokada ładowania z PV): falownik nie naładuje
        # baterii z żadnego źródła — zdejmujemy blokadę (okno ładowania z sieci ma pierwszeństwo)
        try:
            gc_on = self.grid_charging_on() and self.in_grid_charge_window(now)
        except Exception:  # noqa: BLE001
            gc_on = False
        if gc_on and self.pv_charge_blocked() and self._cooldown_ok("unblock_for_grid", now):
            self.log.add("guard", "Okno ładowania z sieci trwa, a prąd ładowania baterii wynosi 0 A — przywracam prąd ładowania", "warn")
            try:
                await self.run_command("odblokuj_ladowanie", source="zabezpieczenie (okno ładowania z sieci)")
                await self.monitor.notifier.send("guard_action", "🛡 EMS: przywrócono prąd ładowania baterii",
                                                 "W oknie ładowania z sieci „Battery Max Charging Current” wynosił 0 A (blokada ładowania z PV), "
                                                 "więc falownik nie ładowałby baterii. Prąd został przywrócony.", key="guard:gc_unblock")
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS GUARD: błąd przywracania prądu ładowania: %s", err)

    # --------------------------------------------- niskie/ujemne ceny (funkcja 1)
    async def price_reaction_tick(self, now: datetime) -> None:
        pr = self.state["price_reaction"]
        enabled = switch_on(self.hass, "negative_price_reaction", False)
        price = self.sell_price()
        thr = number_value(self.hass, "low_price_threshold", 0.0)

        if pr.get("active") and (not enabled or (price is not None and price >= thr + PRICE_HYSTERESIS)):
            prev = pr.get("prev_mode")
            pr["active"] = False
            pr["prev_mode"] = None
            self._save_state()
            why = "funkcja wyłączona" if not enabled else f"cena RCE wróciła do {price:.3f} PLN/kWh"
            if prev and self.is_mode_export(prev):
                reason = self.sell_block_reason(strict_grid=True)
                if reason:
                    self.log.add("price", f"{why}; nie wznawiam sprzedaży: {reason}", "info")
                else:
                    self.log.add("price", f"{why} — wznawiam sprzedaż", "ok")
                    try:
                        await self.run_command("sprzedaz_6000w", source="cena RCE")
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.error("EMS price: wznowienie nieudane: %s", err)
            else:
                self.log.add("price", f"{why} — koniec ograniczenia eksportu", "ok")
            await self.monitor.notifier.send("price_reaction", "💹 EMS: koniec ograniczenia eksportu", f"{why}.", key="price_end", level="info")
            return

        if not enabled or price is None:
            return

        if not pr.get("active") and price < thr:
            wm = SELLING_TOKEN if (self.brand() != brands.DEYE and self.is_selling()) else self.work_mode()
            pr["active"] = True
            pr["prev_mode"] = wm
            self._save_state()
            self.log.add(
                "price",
                f"Cena RCE {price:.3f} < próg {thr:.3f} PLN/kWh — wstrzymuję eksport do sieci",
                "warn", price=round(price, 4), threshold=thr,
            )
            await self.monitor.notifier.send("price_reaction", "💹 EMS: niska cena — eksport wstrzymany",
                                             f"Cena RCE {price:.3f} < próg {thr:.3f} zł/kWh.", key="price_start", level="info")
            if self.is_mode_export(wm):
                try:
                    await self.run_command("nadwyzka_9700w", source="cena RCE")
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("EMS price: wstrzymanie nieudane: %s", err)
        elif pr.get("active") and self.is_selling() and self._cooldown_ok("price_stop", now):
            self.log.add("price", "Sprzedaż włączona przy niskiej cenie — zatrzymuję", "warn")
            try:
                await self.run_command("nadwyzka_9700w", source="cena RCE")
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS price: zatrzymanie nieudane: %s", err)

    # --------------------------------------------------------------- tick / listenery
    # --------------------------------------------------------- tryby burza / urlop
    async def modes_tick(self, now: datetime) -> None:
        """Tryb burzowy wygasa sam po `storm_mode_hours` (żeby nie zostać włączonym na zawsze i nie blokować sprzedaży).

        Urlop tylko zmienia prognozę zużycia (nie ma limitu czasu), ale zapamiętujemy datę włączenia do raportu."""
        st = self.state
        now_ts = now.timestamp()
        if self.storm_active():
            until = st.get("storm_until")
            if not isinstance(until, (int, float)):
                hours = max(1.0, number_value(self.hass, "storm_mode_hours", 24.0))
                st["storm_until"] = until = now_ts + hours * 3600.0
                self._save_state()
                self._reserve_cache = None
                self.log.add("mode", f"Tryb burzowy WŁĄCZONY: rezerwa 100%, sprzedaż zablokowana, "
                                     f"auto-wyłączenie za {hours:.0f} h", "warn")
                await self.monitor.notifier.send(
                    "storm", "⛈ EMS: tryb burzowy włączony",
                    f"Bateria jest ładowana do 100% w najbliższym tanim oknie i nie sprzedaje energii. "
                    f"Tryb wyłączy się sam za {hours:.0f} h.", key="storm_on", cooldown_s=300, level="info")
                self._plan_ts = 0.0
            elif now_ts >= float(until):
                st["storm_until"] = None
                self._save_state()
                self._reserve_cache = None
                self.log.add("mode", "Tryb burzowy wygasł — wyłączam", "ok")
                await self.monitor.notifier.send("storm", "⛈ EMS: tryb burzowy wyłączony", "Minął ustawiony czas — wracam do zwykłego planu.",
                                                 key="storm_off", level="info")
                try:
                    await self.hass.services.async_call(
                        "switch", "turn_off", {"entity_id": find_eid(self.hass, "switch", "storm_mode")}, blocking=True)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("EMS: nie udało się wyłączyć trybu burzowego: %s", err)
                self._plan_ts = 0.0
        elif st.get("storm_until") is not None:
            st["storm_until"] = None
            self._save_state()
            self._reserve_cache = None
            self._plan_ts = 0.0
            self.log.add("mode", "Tryb burzowy wyłączony", "ok")
        if self.vacation_active():
            if st.get("vacation_since") is None:
                st["vacation_since"] = dt_util.as_local(now).date().isoformat()
                self._save_state()
                self._plan_ts = 0.0
                self.log.add("mode", "Tryb urlopowy WŁĄCZONY: prognoza zużycia = stałe minimalne zużycie", "info")
        elif st.get("vacation_since") is not None:
            st["vacation_since"] = None
            self._save_state()
            self._plan_ts = 0.0
            self.log.add("mode", "Tryb urlopowy wyłączony", "ok")

    # ----------------------------------------------------------- plan 24 h (krzywa SOC)
    async def refresh_plan(self, force: bool = False) -> dict[str, Any] | None:
        """Przelicza plan co ~15 min (lub na żądanie) i trzyma go w pamięci dla sensora/karty."""
        now_ts = dt_util.now().timestamp()
        if not force and self._plan is not None and now_ts - self._plan_ts < self._plan_ttl():
            return self._plan
        async with self._plan_lock:
            if not force and self._plan is not None and now_ts - self._plan_ts < self._plan_ttl():
                return self._plan
            try:
                res = await self.optimizer.suggest()
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("EMS: plan 24 h niedostępny: %s", err, exc_info=True)
                return self._plan
            self._plan_ts = dt_util.now().timestamp()
            self._plan = {
                "generated_at": res.get("generated_at"), "mode": res.get("mode"),
                "error": res.get("error"), "curve": res.get("curve"), "assumptions": res.get("assumptions"),
                "proposals": {k: {"proposed": p.get("proposed"), "current": p.get("current"), "skip": p.get("skip"),
                                  "label": p.get("label"), "reason": str(p.get("reason") or "")[:600],
                                  **{x: p[x] for x in ("gain_pln", "required", "confidence") if x in p}}
                              for k, p in (res.get("proposals") or {}).items()},
            }
            blk = self.daily_import_block()
            if blk:       # dziś pobrano z sieci za dużo — plan nie obiecuje sprzedaży, której zabezpieczenie i tak nie wykona
                for k, p in self._plan["proposals"].items():
                    if k.startswith("bateria_sprzedaz_") and p.get("proposed") and not p.get("skip"):
                        p["skip"] = True
                        p["reason"] = f"Blokada sprzedaży: {blk}. " + p["reason"]
            if res.get("error"):
                self._spawn(self.monitor.notifier.send("plan_error", "📉 EMS: plan niedostępny", str(res["error"]), key="plan_error"))
            else:
                inbox.prune_rejected(self.state, self._plan["proposals"])
                self._remember_grid_target(self._plan)
                self._remember_sale_power(self._plan)
                self._log_plan_decisions(self._plan)
            return self._plan

    def _plan_ttl(self) -> float:
        return PLAN_ERROR_TTL_S if (self._plan or {}).get("error") else PLAN_TTL_S

    def plan(self) -> dict[str, Any] | None:
        return self._plan

    # --------------------------------------------------------- raport miesięczny
    def monthly_report(self, year: int | None = None, month: int | None = None) -> dict[str, Any]:
        today = dt_util.now().date()
        if year is None or month is None:
            year, month = today.year, today.month
        cap = float(self.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
        return report_mod.monthly_report(self.ledger, self.stats, int(year), int(month), cap)

    def report_cached(self) -> dict[str, Any]:
        """Raport bieżącego miesiąca z krótkim cache (sensor odświeża się co 10 s)."""
        today = dt_util.now()
        tag = f"{today:%Y-%m-%d %H:%M}"
        if self._report_cache and self._report_cache[0] == tag:
            return self._report_cache[1]
        rep = self.monthly_report()
        self._report_cache = (tag, rep)
        return rep

    async def report_tick(self, now: datetime) -> None:
        """Raport za miesiąc poprzedni w dniu i o godzinie z konfiguratora (domyślnie 1. dnia o 8:00) — raz, nawet po restarcie HA."""
        loc = dt_util.as_local(now)
        ms = self.monitor.notifier.cfg()["sched"]["monthly"]
        if loc.day != ms["day"] or loc.strftime("%H:%M") < ms["time"]:
            return
        prev = (loc.replace(day=1) - timedelta(days=1))
        tag = f"{prev.year:04d}-{prev.month:02d}"
        if self.state.get("report_sent") == tag:
            return
        rep = self.monthly_report(prev.year, prev.month)
        self.state["report_sent"] = tag
        self._save_state()
        if rep["days_with_data"] <= 0:
            return
        text = report_mod.report_text(rep)
        pm = (prev.replace(day=1) - timedelta(days=1))
        try:
            prev_rep = self.monthly_report(pm.year, pm.month)
            cmp = report_mod.compare_line(rep.get("net"), prev_rep.get("net") if prev_rep.get("days_with_data") else None, "poprzedniego miesiąca")
            if cmp:
                text += "\n" + cmp
        except Exception:  # noqa: BLE001
            pass
        await self.monitor.notifier.send(
            "summary_monthly", f"📊 EMS: raport za {rep['title']}", text,
            key=f"report:{tag}", level="info")

    # --------------------------------------------------------------- podsumowania (konfigurator powiadomień)
    def summary_text(self, kind: str, day) -> str:
        """Treść podsumowania dnia („day”) albo 7 dni kończących się w `day` („week”)."""
        if kind == "week":
            start = day - timedelta(days=6)
            t = report_mod.period_totals(self.ledger, self.stats, start, day)
            p = report_mod.period_totals(self.ledger, self.stats, start - timedelta(days=7), start - timedelta(days=1))
            lines = [f"Tydzień {start:%d.%m}–{day:%d.%m} (dni z danymi: {t['days']})"] + report_mod.totals_lines(t)
            cmp = report_mod.compare_line(t["net"], p["net"] if p["days"] else None, "poprzedniego tygodnia")
            if cmp:
                lines.append(cmp)
            if t.get("best"):
                lines.append(f"Najlepszy dzień: {t['best'][0]} ({t['best'][1]:+.2f} zł), najsłabszy: {t['worst'][0]} ({t['worst'][1]:+.2f} zł)".replace(".", ","))
            try:
                lines.extend(money_mod.lines(self.ledger, self.stats, day, "week", start))
            except Exception:  # noqa: BLE001
                pass
            try:
                cap = float(self.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
                s7 = self.stats.summary(cap)
                if s7.get("eff_7d") is not None:
                    lines.append(f"Sprawność cyklu baterii (7 dni): {s7['eff_7d']}%".replace(".", ","))
            except Exception:  # noqa: BLE001
                pass
            return "\n".join(lines)
        t = report_mod.period_totals(self.ledger, self.stats, day, day)
        lines = report_mod.totals_lines(t)
        try:
            lines.extend(money_mod.lines(self.ledger, self.stats, day, "day"))
        except Exception:  # noqa: BLE001
            pass
        sd = self.state.get("soc_day") or {}
        if sd.get("date") == day.isoformat():
            lines.append(f"SOC: min {float(sd['min']):.0f}%, max {float(sd['max']):.0f}%")
        cmds = [e for e in self.log.last(300) if e.get("kind") == "command" and e.get("level") == "ok"
                and str(e.get("ts", "")).startswith(day.isoformat())]
        if cmds:
            lines.append("Wykonane: " + "; ".join(f"{str(e['ts'])[11:16]} {str(e.get('msg', '')).split(' (')[0]}" for e in cmds[-8:]))
        try:
            pv1 = self.optimizer._read_pv_forecast_kwh("pv_forecast_tomorrow", "")  # noqa: SLF001
            lf = (self.coordinator.data or {}).get("load_forecast") or {}
            tom = []
            if pv1 is not None:
                tom.append(f"PV {pv1:.1f} kWh".replace(".", ","))
            if isinstance(lf.get("tomorrow_forecast"), (int, float)):
                tom.append(f"zużycie {lf['tomorrow_forecast']:.1f} kWh".replace(".", ","))
            props = (self.plan() or {}).get("proposals") or {}
            acts = [f"{p.get('label')} {p.get('proposed')}" for p in props.values()
                    if isinstance(p, dict) and p.get("proposed") and not p.get("skip")]
            if tom:
                lines.append("Jutro: " + ", ".join(tom))
            if acts:
                lines.append("Plan: " + "; ".join(acts[:6]))
        except Exception:  # noqa: BLE001
            pass
        return "\n".join(lines)

    # --------------------------------------------------------------- tick / listenery
    async def tick(self, now: datetime) -> None:
        for name, coro in (
            ("snapshot", None),
            ("tryby", self.modes_tick),
            ("ceny", self.price_reaction_tick),
            ("harmonogram", self.process_rules),
            ("zabezpieczenia", self.enforce_guard),
            ("kontrola zapisu", self.watch.tick),
            ("powiadomienia", self.monitor.tick),
            ("raport", self.report_tick),
            ("plan", self._plan_tick),
            ("urządzenia", self._devices_tick),
            ("prognozy", self._insights_tick),
            ("sterowanie urządzeń", self.dev_ctl.tick),
            ("naprawy", self.repairs.tick),
        ):
            try:
                if name == "plan":
                    await self.optimizer.pv_fc.async_refresh()     # Forecast.Solar: dane godzinowe (co 10 min)
                if name == "snapshot":
                    self.update_daily_snapshot(now)
                else:
                    await coro(now)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS tick [%s]: %s", name, err, exc_info=True)
        try:
            self.optimizer.tariff.sample()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._remember_charge_current()
            self._learn_battery_sign(now)
        except Exception:  # noqa: BLE001
            pass

    async def _plan_tick(self, now: datetime) -> None:
        await self.refresh_plan()

    def battery_params(self) -> dict[str, float]:
        """Pojemność, sprawność, próg rozładowania i moce — do symulacji „bateria bez planera”."""
        cfg = self.optimizer.config if isinstance(getattr(self.optimizer, "config", None), dict) else {}

        def num(key: str, default: float) -> float:
            try:
                v = float(cfg.get(key, default))
            except (TypeError, ValueError):
                return default
            return v if v > 0 else default

        floor = 10.0
        try:
            floor = max(float(number_value(self.hass, "reserve_floor_soc", 15.0)), max(self.inverter_floor().get("hourly") or [0.0]))
        except Exception:  # noqa: BLE001
            pass
        return {"cap": num(CONF_BATTERY_CAPACITY_KWH, float(DEFAULT_BATTERY_CAPACITY_KWH)),
                "eff": min(1.0, max(0.5, number_value(self.hass, "cycle_efficiency", 90.0) / 100.0)),
                "floor": floor,
                "max_chg_kw": num("max_charge_power_w", 5000.0) / 1000.0,
                "max_dis_kw": num("max_discharge_power_w", 5000.0) / 1000.0}

    async def _insights_tick(self, now: datetime) -> None:
        """Co minutę: parametry baterii do symulacji i (raz dziennie od 6:00) zapis porannej prognozy PV i planu SOC."""
        self.insights.set_params(**self.battery_params())
        loc = dt_util.as_local(now)
        self._pv_horizon_snapshot(now)
        if loc.hour < 6 or "pv_fc" in (self.insights.fc.get(loc.date().isoformat()) or {}):
            return
        plan = self.plan()
        if plan is None or plan.get("error"):
            return                      # poczekaj na plan (po restarcie powstaje w ciągu minuty)
        kwh, hourly = (None, None)
        if hasattr(self.optimizer, "pv_raw_today"):
            kwh, hourly = self.optimizer.pv_raw_today()
        self.insights.snapshot(now, kwh, hourly, plan)

    def _pv_horizon_snapshot(self, now: datetime) -> None:
        """Od 6:00 raz dziennie: prognoza PV (surowa i po korekcie) na 7 dni do przodu — materiał do uczenia korekty."""
        loc = dt_util.as_local(now)
        if loc.hour < 6:
            return
        today = loc.date().isoformat()
        by_h = (self.insights.fc.get(today) or {}).get("pv_fc_by_h") or {}
        if "6" in by_h and "0" in by_h:
            return
        opt = self.optimizer
        if not hasattr(opt, "pv_card_payload_raw"):
            return
        try:
            raw = [r.get("kwh") for r in (opt.pv_card_payload_raw().get("pv_daily") or [])]
            adj = [r.get("kwh") for r in (opt.pv_card_payload().get("pv_daily") or [])]
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: zapis prognoz PV na 7 dni: %s", err)
            return
        self.insights.snapshot_horizons(now, raw, adj)

    def on_coordinator_update(self) -> None:
        """Wywoływane co 10 s: całkowanie bilansu PLN i statystyk baterii."""
        now = dt_util.now()
        try:
            try:
                peak = bool(get_profile().is_peak(dt_util.as_local(now)))
            except Exception:  # noqa: BLE001
                peak = None
            self.ledger.update(now, self.grid_power(), self.sell_price(), self.buy_price(), peak)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS ledger: %s", err)
        try:
            for ev in self.devices.update(now, self.coordinator.data or {}, self.buy_price()):
                self._spawn(self._device_event(ev))
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS urządzenia: %s", err)
        try:
            self.insights.update(now, self.coordinator.data or {}, self.buy_price(), self.sell_price(),
                                 int(self.battery_sign()["sign"]), self.soc())
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS insights: %s", err)
        try:
            data = self.coordinator.data or {}
            soc = self.soc()
            self.stats.update_day(now, data, soc)
            self.stats.add_power(now, soc, data.get("battery_power"), int(self.battery_sign()["sign"]))
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS stats: %s", err)

    # --------------------------------------------------------------- dane dla encji
    def holiday_label(self) -> str | None:
        return holiday_name(dt_util.now().date())
