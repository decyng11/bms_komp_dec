"""Rdzeń logiki EMS komp-dec.

Zawiera: wykonywanie komend na falowniku (z odczytem zwrotnym), harmonogram (dni tygodnia,
święta), zabezpieczenia sprzedaży, reakcję na niskie/ujemne ceny RCE, sprawdzanie
opłacalności, dynamiczną rezerwę SOC, dziennik decyzji i księgę zysków.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATTERY_CAPACITY_KWH, CONF_GRID_POWER, CONF_PRICE_BUY_ENTITY, CONF_PRICE_SELL_ENTITY, CONF_SOC, DOMAIN,
    DEFAULT_BATTERY_CAPACITY_KWH, DEFAULT_PRICE_BUY_ENTITY, DEFAULT_PRICE_SELL_ENTITY, WEEKDAY_SWITCH_KEYS,
)
from . import inbox
from . import planhold
from . import planstory
from . import settingsio
from . import yoy as yoy_mod
from .gridlimit import GridLimiter
from . import brands
from . import inverter_ctl as ictl
from .battery_sign import SignLearner
from .battery_stats import BatteryStats
from .decision_log import DecisionLog
from .diag_store import DiagStore
from . import devices as devmod
from .helpers import (
    ThrottledStore, backup_raw, find_eid, normalize_price, number_value, state_float, state_str, switch_on,
)
from . import store_guard as SG
from . import review as review_mod
from . import profiles as prof_mod
from . import arbproof as arb_mod
from . import autonomy as auto_mod
from . import pvcaution as pvc_mod
from . import summtable as summtable_mod
from . import billing as bill_mod
from . import deeds as deeds_mod
from . import outage as outage_mod
from . import adviser as adviser_mod
from . import expand as expand_mod
from . import fleet as fleet_mod
from . import pricefeed as pricefeed_mod
from . import costforecast as costforecast_mod

ISSUES_EVERY_S = 55          # lista „co dziś nie działa” liczy się co tyle sekund
from .holidays_pl import holiday_name, is_holiday
from .device_ctl import DeviceController
from .insights import Insights, SOC as _INS_SOC
from .repairs_bms import Repairs
from .ledger import Ledger
from . import money as money_mod
from .tariff import get_profile
from .monitor import Monitor
from . import report as report_mod
from .reserve import compute_reserve
from .inverter_floor import floor_profile
from .watch import WriteWatch
from . import overrides as ovr_mod
from . import planview
from . import analysis as analysis_mod

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

START_PARTNER = {v: k for k, v in STOP_PARTNER.items()}

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
# awaryjny STOP: co zapamiętujemy przy starcie z harmonogramu i która komenda kończy okno
SCHED_START_CMD = {"wlacz_ladowanie_siec": "gc_sched", "sprzedaz_6000w": "sale_sched"}
SCHED_END_CMD = {"wylacz_ladowanie_siec": "gc_sched", "nadwyzka_9700w": "sale_sched"}
SCHED_STOP_CMD = {"gc_sched": "wylacz_ladowanie_siec", "sale_sched": "nadwyzka_9700w"}
SCHED_SETTLE_S = 300       # tyle czekamy, aż falownik potwierdzi start, zanim uznamy, że okno nie trwa
SELLING_TOKEN = "__sprzedaz__"     # zapamiętany „tryb” przy falownikach bez trybu Export First (Sofar)
PRICE_HYSTERESIS = 0.02          # PLN/kWh powyżej progu, by uznać cenę za "wróconą do normy"
GUARD_COOLDOWN_S = 120
PV_STREAK_DAYS = 3         # tyle dni z rzędu PV wyraźnie poniżej prognozy → ostrzeżenie
PV_STREAK_RATIO = 0.7
STARTUP_CHECK_S = 180      # kiedy po starcie robimy samokontrolę
FAILSAFE_NODATA_S = 900    # brak SOC dłużej niż tyle → tryb awaryjny (nie sterujemy „na ślepo”)
MISMATCH_GRACE_S = 600     # tyle czasu falownik może ładować z sieci „bez właściciela”, zanim zgłosimy rozjazd
MISMATCH_RENOTIFY_S = 6 * 3600
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
        try:
            optimizer.block_fn = self.blocked_kinds          # plan nie proponuje tego, co jest zablokowane (tryb prosty / nadpisania)
        except Exception:  # noqa: BLE001
            pass
        try:
            optimizer.full_due_fn = self.full_charge_due       # plan podnosi cel ładowania do 100%, gdy minął termin pełnego ładowania
        except Exception:  # noqa: BLE001
            pass
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
        self._plan_hold: dict[str, Any] = {}
        self.sensor_faults: list[dict[str, str]] = []
        self._sf_state: dict[str, Any] | None = None
        self._plan_lock = asyncio.Lock()
        self._report_cache: tuple[str, dict[str, Any]] | None = None
        self._state_store = ThrottledStore(hass, 1, "bms_komp_dec_runtime", delay=30)
        self._state_integrity = SG.Integrity("bms_komp_dec_runtime", "stan EMS")
        self._repairs_reported = False
        self.issues: list[dict[str, Any]] = []             # „co dziś nie działa” (issues.collect), odświeżane co minutę
        self._issues_seen: dict[str, float] = {}           # od kiedy dany problem trwa (id → znacznik czasu)
        self._issues_at = 0.0
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
            "overrides": [],                   # ręczne nadpisania planu (overrides.py)
            "analysis_cfg": {},                # ceny alternatyw i nakłady do analiz (analysis.py)
            "control_test": None,              # wynik ostatniego testu sterowania falownikiem
            "deeds": {},                       # „co EMS zrobił za Ciebie”: liczniki miesięczne (deeds.py)
            "fleet": {},                       # flota: klastry, falowniki, baterie (fleet.py), tylko odczyt
        }
        self._sign = SignLearner()
        self.log.on_entry = self._count_deed

    # ------------------------------------------------------------ lifecycle
    async def async_load(self) -> None:
        # każdy plik osobno: uszkodzony jeden nie może zatrzymać startu ani pozostałych (kopia i powiadomienie — store_repair_tick)
        for label, store in (("dziennika decyzji", self.log), ("księgi zysków", self.ledger), ("statystyk baterii", self.stats),
                             ("magazynu Diagnostyki", self.diag_store), ("urządzeń", self.devices), ("historii godzinowej", self.insights)):
            try:
                await store.async_load()
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("EMS: nie udało się wczytać %s: %s", label, err, exc_info=True)
                integ = getattr(store, "integrity", None)
                if integ is not None:
                    integ.note(f"wczytywanie nie powiodło się ({type(err).__name__}) — zaczynam od zera")
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
            try:
                from .state_guard import sanitize
                fixed = sanitize(self.state)
            except Exception as err:  # noqa: BLE001
                fixed = []
                _LOGGER.warning("EMS: kontrola zapisanego stanu nie powiodła się: %s", err)
            if fixed:
                _LOGGER.warning("EMS: uszkodzone wartości w zapisanym stanie przywrócono do domyślnych: %s", ", ".join(fixed))
                self._state_integrity.note(f"pola przywrócone do domyślnych: {', '.join(fixed)}", data)
                self.log.add("system", f"Naprawiono uszkodzony zapis stanu (pola: {', '.join(fixed)}) — wartości wróciły do domyślnych", "warn")
            try:
                self._sign = SignLearner(self.state.get("battery_sign_votes"))
            except Exception:  # noqa: BLE001
                self._sign = SignLearner()

    def _save_state(self) -> None:
        self._state_store.request_save(lambda: dict(self.state))

    async def issues_tick(self, now: datetime, force: bool = False) -> None:
        """Co ~minutę odświeża listę „co dziś nie działa” i pamięta, od kiedy każdy problem trwa."""
        ts = now.timestamp()
        if not force and ts - self._issues_at < ISSUES_EVERY_S:
            return
        self._issues_at = ts
        from . import issues as issues_mod
        found = issues_mod.collect(self, now)
        seen = {i["id"]: self._issues_seen.get(i["id"], ts) for i in found}
        self._issues_seen = seen
        self.issues = [dict(i, since=round(seen[i["id"]])) for i in found]

    def integrity_items(self) -> list[SG.Integrity]:
        """Pliki zapisu, które przy wczytywaniu trzeba było naprawić (do raportu po starcie)."""
        stores = (self.log, self.ledger, self.stats, self.devices, self.insights, self.diag_store,
                  getattr(self.coordinator, "load_forecast", None), getattr(self.optimizer, "tariff", None))
        items = [st.integrity for st in stores if st is not None and isinstance(getattr(st, "integrity", None), SG.Integrity)]
        items.append(self._state_integrity)
        return [i for i in items if i]

    async def store_repair_tick(self, now: datetime) -> None:
        """Raz po starcie: kopia oryginału każdego naprawionego pliku, wpis w dzienniku i jedno powiadomienie."""
        if self._repairs_reported:
            return
        self._repairs_reported = True
        items = self.integrity_items()
        if not items:
            return
        for it in items:
            saved = await backup_raw(self.hass, it.key, it.raw)
            tail = f" Kopia oryginału: .storage/{it.key}_backup." if saved else ""
            self.log.add("system", f"Naprawiono uszkodzone dane — {it.summary()}.{tail}", "warn")
            _LOGGER.warning("EMS: naprawiono uszkodzone dane — %s", it.summary())
        msg = " ".join(f"{i.summary()}." for i in items) + " Oryginały zapisano w .storage (pliki …_backup); EMS działa dalej na naprawionych danych."
        await self.monitor.notifier.send("data_repair", "🛠 EMS: naprawiono uszkodzone dane", msg[:1400], key="data_repair", level="warn")

    def start_settings_log(self):
        """Nasłuch zmian encji integracji → dziennik zmian ustawień (kto, kiedy, było → jest). Zwraca funkcję odpinającą."""
        from homeassistant.const import EVENT_STATE_CHANGED
        from homeassistant.core import callback
        from homeassistant.helpers import entity_registry as er
        from . import settings_log as sl

        reg = er.async_get(self.hass)
        own: dict[str, bool] = {}

        def is_own(eid: str) -> bool:
            if eid not in own:
                ent = reg.async_get(eid)
                own[eid] = bool(ent and ent.platform == DOMAIN and eid.split(".", 1)[0] in sl.DOMAINS)
            return own[eid]

        @callback
        def _on_change(event) -> None:
            data = event.data
            eid = data.get("entity_id") or ""
            if "." not in eid or eid.split(".", 1)[0] not in sl.DOMAINS:
                return
            old, new = data.get("old_state"), data.get("new_state")
            if old is None or new is None or not is_own(eid):
                return
            ctx = event.context
            if ctx is None or (ctx.user_id is None and ctx.parent_id is None):
                return                                    # zmiana wewnętrzna integracji
            who = "automatyzacja / skrypt"
            if ctx.user_id:
                who = f"użytkownik {ctx.user_id[:8]}"
                self._spawn(self._name_settings_log_user(ctx.user_id))
            if sl.record(self.state, eid, old.state, new.state, who) is not None:
                self._save_state()

        return self.hass.bus.async_listen(EVENT_STATE_CHANGED, _on_change)

    async def _name_settings_log_user(self, user_id: str) -> None:
        """Podmienia skrót identyfikatora w ostatnich wpisach na nazwę użytkownika HA (jednorazowo na użytkownika)."""
        try:
            user = await self.hass.auth.async_get_user(user_id)
        except Exception:  # noqa: BLE001
            return
        if not user or not user.name:
            return
        short = f"użytkownik {user_id[:8]}"
        changed = False
        for e in self.state.get("settings_log") or []:
            if isinstance(e, dict) and e.get("who") == short:
                e["who"] = user.name
                changed = True
        if changed:
            self._save_state()

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
        """Marka falownika (Deye / Sofar G3 / Sofar hybrydowy / GoodWe) — wykrywana po opcjach trybu pracy."""
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

    def buy_price_signed(self) -> float | None:
        """Bieżąca cena zakupu, także ujemna (buy_price() odrzuca wartości ≤ 0 i wraca do taryfy). Sterowanie urządzeniami
        przy ujemnej cenie potrzebuje prawdziwej wartości z encji; poza zakresem ±20 zł/kWh albo bez odczytu → cena z taryfy."""
        eid = self.optimizer.config.get(CONF_PRICE_BUY_ENTITY, DEFAULT_PRICE_BUY_ENTITY)
        val = state_float(self.hass, eid)
        if val is not None and math.isfinite(val) and -20.0 <= val <= 20.0:
            return val
        try:
            v = float(self.optimizer.tariff.get_price(dt_util.now()))
            return v if math.isfinite(v) else None
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

    # ------------------------------------------ energia z sieci w baterii (zakaz „ładuj z sieci → sprzedaj”)
    GRID_BATT_DEADBAND_W = 100.0     # drobny pobór z sieci przy ładowaniu z PV (szum regulacji falownika) nie liczy się
    GRID_BATT_MAX_GAP_S = 120.0

    def grid_batt_kwh(self) -> float:
        """Ile kWh energii naładowanej z sieci jest jeszcze w baterii (dom jej nie zużył)."""
        try:
            return max(0.0, float((self.state.get("grid_batt") or {}).get("kwh") or 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _track_grid_batt(self, now: datetime) -> None:
        """Licznik energii z sieci w baterii: rośnie, gdy bateria ładuje się przy poborze z sieci (ładowanie z sieci),
        maleje, gdy bateria zasila dom (energia z sieci schodzi pierwsza). Sprzedaż do sieci go nie zmniejsza.
        Nigdy nie przekracza energii faktycznie zgromadzonej w baterii (SOC × pojemność)."""
        prev = getattr(self, "_gb_ts", None)
        self._gb_ts = now
        if prev is None:
            return
        dt_s = (now - prev).total_seconds()
        if dt_s <= 0 or dt_s > self.GRID_BATT_MAX_GAP_S:
            return
        bp = (self.coordinator.data or {}).get("battery_power")
        try:
            bp = float(bp)
        except (TypeError, ValueError):
            return
        if not math.isfinite(bp) or abs(bp) > 100000:
            return
        chg_w = bp * (1 if int(self.battery_sign()["sign"]) >= 0 else -1)     # dodatnia = ładowanie
        gp = self.grid_power()                                                # dodatnia = pobór z sieci
        mem = self.state.get("grid_batt")
        if not isinstance(mem, dict):
            mem = self.state["grid_batt"] = {"kwh": 0.0}
        kwh = self.grid_batt_kwh()
        before = kwh
        h = dt_s / 3600.0
        pool = getattr(self, "_arb_pool", None)
        pool = kwh if pool is None else min(float(pool), kwh)            # po restarcie: najgorszy przypadek = cały licznik
        arb_in = arb_out = arb_leak = 0.0
        if chg_w > 0:
            gc = False
            try:
                gc = self.grid_charging_on()
            except Exception:  # noqa: BLE001
                gc = False
            if gp is None:
                from_grid = chg_w if gc else 0.0
            else:
                from_grid = min(chg_w, max(0.0, gp - (0.0 if gc else self.GRID_BATT_DEADBAND_W)))
            kwh += from_grid / 1000.0 * h
            arb_in = from_grid / 1000.0 * h
            pool += arb_in
        elif chg_w < 0:
            export = max(0.0, -gp) if gp is not None else 0.0
            to_grid = min(-chg_w, export)                                # bateria oddaje do sieci (nie PV)
            to_house = max(0.0, -chg_w - export)
            arb_out = to_grid / 1000.0 * h
            if pool > 0:
                arb_leak = min(arb_out, pool)                            # najpierw schodzi do sieci energia z sieci (górna granica)
                pool = max(0.0, pool - arb_leak - to_house / 1000.0 * h)
            if kwh > 0:
                kwh = max(0.0, kwh - to_house / 1000.0 * h)
        soc = self.soc()
        if soc is not None:
            try:
                cap = float(self.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
                kwh = min(kwh, max(0.0, soc) / 100.0 * cap)
            except Exception:  # noqa: BLE001
                pass
        mem["kwh"] = round(kwh, 4)
        self._arb_pool = min(pool, kwh)
        if arb_in or arb_out:
            self._arb_note(dt_util.as_local(now).date().isoformat(), arb_in, arb_out, arb_leak)
        if abs(kwh - float(mem.get("saved", 0.0) or 0.0)) >= 0.05 or (kwh == 0.0 and before > 0.0):
            mem["saved"] = mem["kwh"]
            self._save_state()

    # ------------------------------------------ na ile godzin starczy baterii
    def _track_load(self, now: datetime) -> None:
        """Wygładzony pobór domu (średnia wykładnicza, ~5 min) — baza szacunku „na ile godzin starczy baterii”."""
        prev_ts = getattr(self, "_load_ts", None)
        self._load_ts = now
        dt_s = 0.0 if prev_ts is None else (now - prev_ts).total_seconds()
        self._load_ema = auto_mod.ema(getattr(self, "_load_ema", None), (self.coordinator.data or {}).get("load_power"), dt_s)

    def autonomy(self) -> dict[str, Any] | None:
        """Ile godzin bateria utrzyma dom bez PV i sieci: energia nad progiem odcięcia ÷ wygładzony pobór; None, gdy brak danych."""
        soc = self.soc()
        w = getattr(self, "_load_ema", None)
        if soc is None or w is None:
            return None
        try:
            floor = float(self.inverter_floor()["hourly"][dt_util.now().hour])
        except Exception:  # noqa: BLE001
            floor = number_value(self.hass, "reserve_floor_soc", 15.0)
        cap = float(self.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
        est = auto_mod.estimate(soc, floor, cap, w)
        if est is None:
            return None
        est["text"] = auto_mod.fmt_hours(est["hours"], est["capped"])
        est["floor"] = round(floor, 1)
        est["soc"] = round(float(soc), 1)
        return est

    def _arb_note(self, day: str, grid_in: float, out: float, leak: float) -> None:
        store = self.state.get("arb_proof")
        if not isinstance(store, dict):
            store = self.state["arb_proof"] = {}
        arb_mod.add(store, day, grid_in, out, leak)

    def arb_tol(self) -> float:
        return number_value(self.hass, "grid_arbitrage_block_kwh", 0.5)

    def arb_proof(self, n: int = 14) -> list[dict[str, Any]]:
        """Dowód zakazu arbitrażu dla ostatnich dób (najnowsze pierwsze)."""
        return arb_mod.rows(self.state.get("arb_proof"), n, self.arb_tol())

    def grid_batt_block(self) -> str | None:
        """Zakaz sprzedaży, dopóki w baterii jest energia naładowana z sieci (tolerancja = „Blokada arbitrażu”; 0 = wył.)."""
        tol = number_value(self.hass, "grid_arbitrage_block_kwh", 0.5)
        if tol <= 0:
            return None
        kwh = self.grid_batt_kwh()
        if kwh > tol:
            return (f"w baterii jest ~{kwh:.1f} kWh energii naładowanej z sieci (tolerancja {tol:.1f} kWh) — "
                    f"sprzedaż dopiero, gdy dom ją zużyje")
        return None

    def storm_active(self) -> bool:
        return switch_on(self.hass, "storm_mode", False)

    def vacation_active(self) -> bool:
        return switch_on(self.hass, "vacation_mode", False)

    def sell_block_reason(self, strict_grid: bool = False) -> str | None:
        """Powód zakazu sprzedaży (tryb burzowy / import z sieci / arbitraż) albo None.

        strict_grid=True: brak odczytu mocy sieci również blokuje (start z harmonogramu)."""
        if self.storm_active():
            return "tryb burzowy — energia zostaje w baterii (rezerwa 100%)"
        if not switch_on(self.hass, "sell_enabled", True):
            return "sprzedaż z baterii wyłączona w ustawieniach (przełącznik „Sprzedawaj z baterii”)"
        ov = self.override_active(dt_util.now(), "no_sell")
        if ov:
            return f"ręczne nadpisanie: nie sprzedawaj do {self._hm(ov[0]['end'])}"
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
        gb = self.grid_batt_block()
        if gb:
            return f"arbitraż: {gb}"
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
        if key == "wlacz_ladowanie_siec":
            self.state["gc_origin"] = {"src": source, "ts": dt_util.now().timestamp()}   # ktoś świadomie włączył
            self._save_state()
        elif key == "wylacz_ladowanie_siec" and self.state.pop("gc_origin", None) is not None:
            self._save_state()
        if key in SCHED_END_CMD and self.state.pop(SCHED_END_CMD[key], None) is not None:
            self._save_state()                 # okno zakończone (STOP, zabezpieczenie albo ręcznie) — awaryjny STOP niepotrzebny
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
        if not day_ok or "grid" in self.blocked_kinds():
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
                self._mark_sched(start_key, "wlacz_ladowanie_siec", now)
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
            pair_key = STOP_PARTNER.get(time_key) or START_PARTNER.get(time_key)
            if pair_key:
                p_st = self.hass.states.get(find_eid(self.hass, "time", pair_key))
                if p_st is not None and str(p_st.state)[:5] == t_val[:5]:
                    continue                    # puste okno (start = stop, np. wyzerowane przez plan) — nic nie wykonujemy
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

            if button_key == "wlacz_ladowanie_siec" and "grid" in self.blocked_kinds():
                self._log_skip(time_key, now_hm, self.blocked_kinds()["grid"])
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

            self._mark_sched(time_key, button_key, now)
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
                top_l = dm.top_now()
                top = ", ".join(f"{nm} {p / 1000:.1f} kW" for nm, p in top_l)
                try:
                    au = self.autonomy()
                except Exception:  # noqa: BLE001
                    au = None
                left = (f" Bateria wystarczy na ok. {au['text']}." + auto_mod.extend_hint(au, top_l)) if au else ""
                await n.send("island_overload", "⚡ EMS: duży pobór przy zaniku sieci",
                             f"Dom pobiera {load / 1000:.1f} kW z baterii (próg {float(thr):.1f} kW)." + left + (f" Największe: {top}." if top else ""),
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

    PLAN_LOG_GROUPS_FLAT = tuple((n, k[0], k[1]) for n, k in PLAN_LOG_GROUPS)

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
    def _mark_sched(self, start_key: str, button_key: str, now: datetime) -> None:
        """Start okna z harmonogramu (ładowanie z sieci / sprzedaż) — zapamiętany także na czas restartu HA."""
        slot = SCHED_START_CMD.get(button_key)
        if slot:
            self.state[slot] = {"start_key": start_key, "ts": now.timestamp()}
            self._save_state()

    def _sched_window_open(self, start_key: str, now: datetime) -> bool:
        """Czy okno zestawu (bieżące godziny Start–Stop) obejmuje teraz? Puste albo nieustawione okno = nie."""
        stop_key = START_PARTNER.get(start_key)
        ts = self.hass.states.get(find_eid(self.hass, "time", start_key))
        te = self.hass.states.get(find_eid(self.hass, "time", stop_key)) if stop_key else None
        if not ts or not te:
            return False
        s_hm, e_hm = str(ts.state)[:5], str(te.state)[:5]
        if "00:00" in (s_hm, e_hm) or ":" not in s_hm or ":" not in e_hm or s_hm == e_hm:
            return False
        cur = dt_util.as_local(now).strftime("%H:%M")
        return (s_hm <= cur < e_hm) if s_hm < e_hm else (cur >= s_hm or cur < e_hm)

    async def _late_stop(self, now: datetime) -> None:
        """Awaryjny STOP: okno wystartowało z harmonogramu, a jego STOP nie zadziałał w swojej minucie (restart HA,
        przeładowanie integracji, chwilowo niedostępna encja) — ładowanie z sieci / sprzedaż trwa po czasie. Kończymy je.
        Nie dotyczy startów ręcznych („Wymuś ładowanie”, przyciski) — te nie zostawiają znacznika."""
        for slot, active in (("gc_sched", self.grid_charging_on), ("sale_sched", self.is_selling)):
            mark = self.state.get(slot)
            if not isinstance(mark, dict) or not mark.get("start_key"):
                continue
            try:
                on = bool(active())
            except Exception:  # noqa: BLE001
                continue
            age = now.timestamp() - float(mark.get("ts") or 0.0)
            if not on:
                if age > SCHED_SETTLE_S:           # okno skończyło się inną drogą (np. zabezpieczenie SOC)
                    self.state.pop(slot, None)
                    self._save_state()
                continue
            if self._sched_window_open(str(mark["start_key"]), now):
                continue
            if slot == "gc_sched" and (switch_on(self.hass, "force_charge_battery", False) or self.in_grid_charge_window(now)):
                continue                           # trwa „Wymuś ładowanie” albo okno drugiego zestawu
            if slot == "sale_sched" and any(self._sched_window_open(k, now) and switch_on(self.hass, sw, False)
                                            for k, sw in (("bateria_sprzedaz_start", "bateria_sprzedaz_1"),
                                                          ("bateria_sprzedaz_start_2", "bateria_sprzedaz_2"))):
                continue                           # trwa okno drugiego zestawu sprzedaży
            if not self._cooldown_ok(f"late_stop:{slot}", now):
                continue
            what = "ładowanie z sieci" if slot == "gc_sched" else "sprzedaż z baterii"
            self.log.add("guard", f"Awaryjny STOP: {what} trwa po zakończeniu okna ({mark['start_key']}) — "
                                  f"STOP z harmonogramu nie zadziałał, kończę teraz", "warn")
            try:
                await self.run_command(SCHED_STOP_CMD[slot], source="zabezpieczenie (STOP po czasie)")
                await self.monitor.notifier.send(
                    "guard_action", f"🛡 EMS: awaryjny STOP — {what}",
                    f"Okno z harmonogramu już się skończyło, a {what} nadal trwało (STOP nie zadziałał o swojej godzinie, "
                    f"np. przez restart Home Assistanta). Zakończono teraz.", key=f"guard:late:{slot}")
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS GUARD: awaryjny STOP (%s) nieudany: %s", slot, err)

    def pv_streak(self, today) -> dict[str, Any] | None:
        """Passa dni, w których produkcja PV była wyraźnie niższa niż prognoza (ostatnie PV_STREAK_DAYS pełnych dni).
        Zwraca {"days", "ratio"} albo None, gdy passy nie ma lub brakuje danych."""
        ratios: list[float] = []
        for i in range(1, PV_STREAK_DAYS + 1):
            rec = self.insights.fc.get((today - timedelta(days=i)).isoformat()) or {}
            try:
                f_, a_ = float(rec.get("pv_fc")), float(rec.get("pv_act"))
            except (TypeError, ValueError):
                return None
            if f_ < 2.0:                       # prognoza prawie zerowa — stosunek nic nie mówi
                return None
            ratios.append(a_ / f_)
        if all(r < PV_STREAK_RATIO for r in ratios):
            return {"days": PV_STREAK_DAYS, "ratio": round(sum(ratios) / len(ratios), 2)}
        return None

    async def _pv_streak_check(self, now: datetime) -> None:
        """Zbyt optymistyczne PV: kilka dni z rzędu produkcja <70% prognozy. Planer, który pomija ładowanie z sieci przy
        dobrej prognozie PV, powinien wtedy być ostrożniejszy — zgłaszamy to raz dziennie (wpis w dzienniku + powiadomienie)."""
        today = dt_util.as_local(now).date()
        if self.state.get("pv_streak_day") == today.isoformat():
            return
        st = self.pv_streak(today)
        if not st:
            return
        self.state["pv_streak_day"] = today.isoformat()
        self._save_state()
        pct = round(st["ratio"] * 100)
        self.log.add("guard", f"Prognoza PV zawyżona {st['days']} dni z rzędu (produkcja ok. {pct}% prognozy)", "warn")
        try:
            await self.monitor.notifier.send(
                "guard_action", "⚠ EMS: prognoza PV zbyt optymistyczna",
                f"Przez {st['days']} dni z rzędu produkcja PV wynosiła ok. {pct}% prognozy. Plan, który polega na dobrej "
                f"pogodzie i pomija ładowanie z sieci, może zostawić za mało energii — rozważ wyższą rezerwę albo sprawdź "
                f"źródło prognozy PV.", key="guard:pvstreak")
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS GUARD: powiadomienie o passie PV: %s", err)

    async def _startup_check(self, now: datetime) -> None:
        """Samokontrola po (re)starcie: raz, kilka minut po uruchomieniu, porównuje stan falownika ze znacznikami EMS
        (kto zlecił ładowanie z sieci / sprzedaż) i zostawia w dzienniku jednoznaczny wynik. Rozjazdy zgłaszają strażnicy
        (rozjazdu, awaryjny STOP); tu tylko podsumowanie, żeby po restarcie nie zgadywać, czy wszystko jest zgodne."""
        if getattr(self, "_startup_done", False):
            return
        t0 = getattr(self, "_startup_t0", None)
        if t0 is None:
            self._startup_t0 = now
            return
        if (now - t0).total_seconds() < STARTUP_CHECK_S or self.soc() is None:
            return
        self._startup_done = True
        try:
            gc, sale = bool(self.grid_charging_on()), bool(self.is_selling())
        except Exception:  # noqa: BLE001
            return
        issues: list[str] = []
        gc_owner = self._mismatch_owner(now)
        if gc and not gc_owner:
            issues.append("falownik ładuje z sieci bez zlecenia EMS")
        if not gc and (self.state.get("gc_sched") or self.state.get("gc_origin")):
            issues.append("zapisane ładowanie z sieci, a falownik nie ładuje (znacznik nieaktualny)")
            self.state.pop("gc_sched", None); self.state.pop("gc_origin", None); self._save_state()
        if not sale and self.state.get("sale_sched"):
            issues.append("zapisana sprzedaż, a falownik nie sprzedaje (znacznik nieaktualny)")
            self.state.pop("sale_sched", None); self._save_state()
        if sale and not self.state.get("sale_sched") and not any(
                self._sched_window_open(k, now) for k in ("bateria_sprzedaz_start", "bateria_sprzedaz_start_2")):
            issues.append("falownik sprzedaje poza oknem sprzedaży (start ręczny lub z aplikacji producenta)")
        stan = f"ładowanie z sieci: {'tak' if gc else 'nie'}, sprzedaż: {'tak' if sale else 'nie'}"
        if issues:
            self.log.add("guard", f"Samokontrola po starcie: {stan}. Rozbieżności: " + "; ".join(issues), "warn")
        else:
            self.log.add("guard", f"Samokontrola po starcie: stan falownika zgodny z planem ({stan})", "ok")

    async def _failsafe_check(self, now: datetime) -> None:
        """Tryb awaryjny: brak odczytu SOC dłużej niż FAILSAFE_NODATA_S (falownik/internet/integracja milczy). Bez SOC nie da
        się bezpiecznie ładować z sieci ani sprzedawać — kończymy to, co EMS sam zlecił (wg znaczników, nie odczytu z falownika),
        i zgłaszamy. Po powrocie danych wpis w dzienniku; plan wznawia się sam."""
        soc = self.soc()
        if soc is not None:
            if getattr(self, "_nodata_since", None) is not None:
                if getattr(self, "_failsafe_on", False):
                    self.log.add("guard", "Dane z falownika wróciły — tryb awaryjny zakończony, plan działa normalnie", "ok")
                self._nodata_since = None
                self._failsafe_on = False
            return
        since = getattr(self, "_nodata_since", None)
        if since is None:
            self._nodata_since = now
            return
        if getattr(self, "_failsafe_on", False) or (now - since).total_seconds() < FAILSAFE_NODATA_S:
            return
        self._failsafe_on = True
        mins = int((now - since).total_seconds() // 60)
        stopped: list[str] = []
        if self.state.get("gc_sched") or self.state.get("gc_origin"):
            try:
                await self.run_command("wylacz_ladowanie_siec", source="tryb awaryjny")
                stopped.append("ładowanie z sieci")
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS GUARD: tryb awaryjny — STOP ładowania: %s", err)
        if self.state.get("sale_sched"):
            try:
                await self.run_command("nadwyzka_9700w", source="tryb awaryjny")
                stopped.append("sprzedaż z baterii")
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS GUARD: tryb awaryjny — STOP sprzedaży: %s", err)
        what = (" Zatrzymano: " + ", ".join(stopped) + ".") if stopped else ""
        self.log.add("guard", f"Tryb awaryjny: brak danych SOC od {mins} min.{what}", "warn")
        try:
            await self.monitor.notifier.send(
                "guard_action", "⚠ EMS: brak danych z falownika",
                f"Brak odczytu SOC od ok. {mins} min — sterowanie wstrzymane dla bezpieczeństwa.{what} "
                f"Sprawdź połączenie z falownikiem (Ustawienia → Łączność). Plan wznowi się sam po powrocie danych.",
                key="guard:failsafe")
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS GUARD: powiadomienie o trybie awaryjnym: %s", err)

    def failsafe_active(self) -> bool:
        return bool(getattr(self, "_failsafe_on", False))

    def mismatch_active(self) -> bool:
        return getattr(self, "_mismatch_notified", None) is not None and getattr(self, "_mismatch_since", None) is not None

    def grid_charge_owner(self, now: datetime) -> str | None:
        """Kto zlecił trwające ładowanie z sieci (do opisu „dlaczego”)."""
        return self._mismatch_owner(now)

    def _mismatch_owner(self, now: datetime) -> str | None:
        """Kto „odpowiada” za trwające ładowanie z sieci: harmonogram, okno, wymuszenie albo ręczna komenda.
        None = nikt (falownik ładuje z sieci, a EMS tego nie zlecał)."""
        if self.state.get("gc_sched"):
            return "harmonogram"
        if self.state.get("gc_origin"):
            return "komenda"
        if self.in_grid_charge_window(now):
            return "okno"
        if switch_on(self.hass, "force_charge_battery", False):
            return "wymuszenie"
        return None

    async def _mismatch_check(self, now: datetime) -> None:
        """Strażnik rozjazdu: falownik ładuje z sieci, choć żadne okno, harmonogram, wymuszenie ani komenda tego nie zleciły
        (np. zmiana godzin okna w trakcie, ustawienie zmienione w aplikacji producenta). Tylko zgłasza — nie wyłącza,
        bo to może być świadoma konfiguracja w falowniku."""
        try:
            on = bool(self.grid_charging_on())
        except Exception:  # noqa: BLE001
            return
        if not on:
            org = self.state.get("gc_origin")
            if isinstance(org, dict) and now.timestamp() - float(org.get("ts") or 0.0) > SCHED_SETTLE_S:
                self.state.pop("gc_origin", None)      # ktoś wyłączył ładowanie poza EMS — właściciel nieaktualny
                self._save_state()
        if not on or self._mismatch_owner(now):
            self._mismatch_since = None
            return
        since = getattr(self, "_mismatch_since", None)
        if since is None:
            self._mismatch_since = now
            return
        if (now - since).total_seconds() < MISMATCH_GRACE_S:
            return
        last = getattr(self, "_mismatch_notified", None)
        if last is not None and (now - last).total_seconds() < MISMATCH_RENOTIFY_S:
            return
        self._mismatch_notified = now
        mins = int((now - since).total_seconds() // 60)
        self.log.add("guard", f"Rozjazd: falownik ładuje z sieci od ok. {mins} min, a EMS tego nie zlecał "
                              f"(brak okna, harmonogramu, wymuszenia i ręcznej komendy)", "warn")
        try:
            await self.monitor.notifier.send(
                "guard_action", "⚠ EMS: ładowanie z sieci poza planem",
                f"Falownik ładuje baterię z sieci od ok. {mins} min, a żadne okno ładowania, harmonogram ani komenda tego nie "
                f"zlecały. Sprawdź ustawienia falownika albo wyłącz ładowanie z sieci przyciskiem w panelu.",
                key="guard:mismatch")
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS GUARD: powiadomienie o rozjeździe: %s", err)

    def _cooldown_ok(self, name: str, now: datetime) -> bool:
        last = self._guard_last.get(name)
        if last is not None and (now - last).total_seconds() < GUARD_COOLDOWN_S:
            return False
        self._guard_last[name] = now
        return True

    async def enforce_guard(self, now: datetime) -> None:
        soc = self.soc()

        try:
            await self._late_stop(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS GUARD: awaryjny STOP: %s", err)
        try:
            await self._stop_at_target(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS GUARD: koniec ładowania po osiągnięciu celu: %s", err)
        try:
            await self._pv_streak_check(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS GUARD: passa PV: %s", err)
        try:
            await self._startup_check(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS GUARD: samokontrola po starcie: %s", err)
        try:
            await self._failsafe_check(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS GUARD: tryb awaryjny: %s", err)
        try:
            await self._mismatch_check(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS GUARD: kontrola rozjazdu: %s", err)

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

    # ------------------------------------------ ręczne nadpisania planu (14)
    @staticmethod
    def _hm(ts: float) -> str:
        return dt_util.as_local(datetime.fromtimestamp(float(ts), tz=timezone.utc)).strftime("%H:%M")

    def override_list(self, now: datetime | None = None) -> list[dict]:
        ts = (now or dt_util.now()).timestamp()
        return ovr_mod.prune(list(self.state.get("overrides") or []), ts)

    def override_active(self, now: datetime, kind: str | None = None) -> list[dict]:
        return ovr_mod.active(self.override_list(now), now.timestamp(), kind)

    def override_text(self, o: dict) -> str:
        what = {"charge": "ładuję z sieci", "no_sell": "nie sprzedaję", "no_grid": "nie ładuję z sieci"}.get(o.get("kind"), "?")
        tgt = f" (do {o['target']:.0f}%)" if o.get("target") else ""
        return f"Ręczne nadpisanie: {what}{tgt} do {self._hm(o['end'])}."

    def override_add(self, kind: str, start_ts: float, end_ts: float, target: float | None = None) -> list[dict]:
        now = dt_util.now()
        items = ovr_mod.add(self.override_list(now), kind, start_ts, end_ts, now.timestamp(), target)
        self.state["overrides"] = items
        self.state.pop("ovr_charge_done", None)
        self._save_state()
        self.log.add("command", f"Nadpisanie planu: {ovr_mod.KINDS[kind]} {self._hm(start_ts)}–{self._hm(end_ts)}"
                                + (f", cel {target:.0f}%" if target else "") + " (ręcznie)", "ok")
        self._plan_ts = 0.0                                  # plan i propozycje liczą się od nowa z uwzględnieniem nadpisania
        return items

    def override_remove(self, oid: str | None) -> list[dict]:
        self.state["overrides"] = ovr_mod.remove(self.override_list(), oid)
        self._save_state()
        self.log.add("command", "Usunięto nadpisanie planu" + (" (wszystkie)" if oid is None else "") + " (ręcznie)", "ok")
        self._plan_ts = 0.0
        return self.state["overrides"]

    def blocked_kinds(self) -> dict[str, str]:
        """Co plan ma teraz pomijać: {"sell"|"grid": powód} — z przełączników trybu prostego albo z ręcznych nadpisań."""
        out: dict[str, str] = {}
        now = dt_util.now()
        kinds = {o.get("kind"): o for o in self.override_list(now)}
        if not switch_on(self.hass, "sell_enabled", True):
            out["sell"] = "sprzedaż z baterii wyłączona w ustawieniach"
        elif "no_sell" in kinds:
            out["sell"] = f"ręczne nadpisanie „nie sprzedawaj” do {self._hm(kinds['no_sell']['end'])}"
        if not switch_on(self.hass, "grid_charge_enabled", True):
            out["grid"] = "ładowanie z sieci wyłączone w ustawieniach"
        elif "no_grid" in kinds:
            out["grid"] = f"ręczne nadpisanie „nie ładuj z sieci” do {self._hm(kinds['no_grid']['end'])}"
        return out

    async def override_tick(self, now: datetime) -> None:
        """Wykonuje nadpisania: „ładuj z sieci” (z opcjonalnym celem SOC) i „nie ładuj z sieci”; po wygaśnięciu sprząta."""
        items = self.override_list(now)
        if len(items) != len(self.state.get("overrides") or []):
            self.state["overrides"] = items
            self._save_state()
        ts = now.timestamp()
        flag = self.state.get("ovr_charge_on")
        ch = ovr_mod.active(items, ts, "charge")
        try:
            gc_on = bool(self.grid_charging_on())
        except Exception:  # noqa: BLE001
            return
        if ch:
            o = ch[0]
            soc = self.soc()
            tgt = o.get("target")
            reached = tgt is not None and soc is not None and soc >= float(tgt)
            if reached or (soc is not None and soc >= 100):
                if gc_on and flag and self._cooldown_ok("ovr_stop", now):
                    self.log.add("guard", f"Nadpisanie „ładuj z sieci”: SOC {soc:.0f}% osiągnął cel — kończę ładowanie", "ok")
                    await self.run_command("wylacz_ladowanie_siec", source="nadpisanie (cel osiągnięty)")
                self.state.pop("ovr_charge_on", None)
                self.state["ovr_charge_done"] = o["id"]
                self._save_state()
            elif not gc_on and self.state.get("ovr_charge_done") != o["id"]:
                if self.is_selling():
                    return
                if self._cooldown_ok("ovr_start", now):
                    try:
                        await self.run_command("wlacz_ladowanie_siec", source="ręczne nadpisanie")
                        self.state["ovr_charge_on"] = o["id"]
                        self._save_state()
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.error("EMS nadpisanie: start ładowania nieudany: %s", err)
            elif gc_on and not flag:
                self.state["ovr_charge_on"] = o["id"]      # ładowanie już trwa (np. okno z harmonogramu) — przejmujemy cel
                self._save_state()
        elif flag:
            self.state.pop("ovr_charge_on", None)
            self.state.pop("ovr_charge_done", None)
            self._save_state()
            if gc_on and not self.in_grid_charge_window(now) and not switch_on(self.hass, "force_charge_battery", False):
                self.log.add("guard", "Nadpisanie „ładuj z sieci” wygasło — kończę ładowanie", "ok")
                await self.run_command("wylacz_ladowanie_siec", source="nadpisanie (koniec okna)")
        if ovr_mod.active(items, ts, "no_grid") and gc_on and self._cooldown_ok("ovr_nogrid", now):
            self.log.add("guard", "Nadpisanie „nie ładuj z sieci” — przerywam ładowanie z sieci", "warn")
            try:
                await self.run_command("wylacz_ladowanie_siec", source="nadpisanie (nie ładuj z sieci)")
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS nadpisanie: stop ładowania nieudany: %s", err)

    # ------------------------------------------ koniec ładowania z sieci po osiągnięciu celu z planu (6)
    TARGET_MAX_AGE_S = 6 * 3600

    async def _stop_at_target(self, now: datetime) -> None:
        """Okno ładowania z sieci trwa, a bateria osiągnęła cel z planu — kończymy ładowanie od razu (nie dopiero o STOP):
        reszta okna to płacenie za energię, której plan nie potrzebuje."""
        if not switch_on(self.hass, "grid_stop_at_target", True):
            return
        if self.state.get("ovr_charge_on") or switch_on(self.hass, "force_charge_battery", False):
            return                                    # ręczne ładowanie ma własny cel / trwa do wyłączenia
        try:
            if not self.grid_charging_on() or not self.in_grid_charge_window(now):
                return
        except Exception:  # noqa: BLE001
            return
        tp = self.state.get("grid_target_plan") or {}
        try:
            target = float(tp.get("target"))
            age = now.timestamp() - datetime.fromisoformat(str(tp.get("at"))).timestamp()
        except (TypeError, ValueError):
            return
        soc = self.soc()
        if soc is None or age > self.TARGET_MAX_AGE_S or not 20 <= target < 99:
            return
        if soc < target:
            return
        if not self._cooldown_ok("stop_at_target", now):
            return
        cur = dt_util.as_local(now).strftime("%H:%M")
        for start_key, stop_key, sw_key in self.GC_WINDOWS:           # okno uznajemy za „załatwione” — nadrabianie go nie wznowi
            ts_, te_ = (self.hass.states.get(find_eid(self.hass, "time", k)) for k in (start_key, stop_key))
            if ts_ and te_:
                s_hm, e_hm = str(ts_.state)[:5], str(te_.state)[:5]
                if (s_hm <= cur < e_hm) if s_hm < e_hm else (cur >= s_hm or cur < e_hm):
                    self.state.setdefault("gc_catchup", {})[start_key] = f"{dt_util.as_local(now).date().isoformat()} {s_hm}-{e_hm}"
        self._save_state()
        self.log.add("guard", f"Cel ładowania z sieci osiągnięty (SOC {soc:.0f}% ≥ {target:.0f}% z planu) — kończę ładowanie przed końcem okna", "ok")
        try:
            await self.run_command("wylacz_ladowanie_siec", source="cel ładowania osiągnięty")
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS GUARD: koniec ładowania po osiągnięciu celu: %s", err)

    # ------------------------------------------ widoki dla panelu (13, 17, 20)
    def next_window_text(self, now: datetime) -> str | None:
        """Najbliższe zaplanowane okno (ładowanie z sieci / sprzedaż) — zdanie do „Dlaczego?”."""
        cur = dt_util.as_local(now).strftime("%H:%M")
        best = None
        for (a, b, sw), label in (((self.GC_WINDOWS[0]), "ładowanie z sieci"), ((self.GC_WINDOWS[1]), "ładowanie z sieci"),
                                  (("bateria_sprzedaz_start", "bateria_sprzedaz_stop", "bateria_sprzedaz_1"), "sprzedaż"),
                                  (("bateria_sprzedaz_start_2", "bateria_sprzedaz_stop_2", "bateria_sprzedaz_2"), "sprzedaż")):
            st = self.hass.states.get(find_eid(self.hass, "switch", sw))
            ts_, te_ = (self.hass.states.get(find_eid(self.hass, "time", k)) for k in (a, b))
            if not st or st.state != "on" or not ts_ or not te_:
                continue
            s_hm, e_hm = str(ts_.state)[:5], str(te_.state)[:5]
            if "00:00" in (s_hm, e_hm) or s_hm == e_hm or ":" not in s_hm:
                continue
            if s_hm > cur and (best is None or s_hm < best[0]):
                best = (s_hm, e_hm, label)
        return f"Najbliższe okno dziś: {best[2]} {best[0]}–{best[1]}." if best else None

    def why_now(self, now: datetime | None = None) -> dict[str, Any]:
        return planview.why_now(self, now or dt_util.now())

    def plan_table(self) -> dict[str, Any]:
        cap = float(self.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
        return planview.plan_table((self._plan or {}).get("curve"), cap)

    def cost_forecast(self) -> dict[str, Any]:
        """Prognoza kosztu dziś i jutro (costforecast.py) z księgi i tabeli planu."""
        try:
            return costforecast_mod.forecast(self.ledger.days, self.plan_table().get("rows"), dt_util.now().date())
        except Exception:  # noqa: BLE001
            _LOGGER.debug("EMS: prognoza kosztu nieudana", exc_info=True)
            return {}

    def soc_history(self, days: int = 7) -> list[dict[str, Any]]:
        today = dt_util.now().date()
        keys = [(today - timedelta(days=i)).isoformat() for i in range(days)]
        plans = {k: (self.insights.fc.get(k) or {}).get("soc_plan") for k in keys}
        return planview.soc_history({k: self.insights._buckets(k) for k in keys}, plans, days, today)  # noqa: SLF001

    def analysis_payload(self) -> dict[str, Any]:
        cfg = analysis_mod.clean_cfg(self.state.get("analysis_cfg"))
        today = dt_util.now().date()
        keys = [(today - timedelta(days=i)).isoformat() for i in range(1, 62)]
        buckets = {k: self.insights._buckets(k) for k in keys}  # noqa: SLF001
        avg = None
        try:
            tot = self.ledger.sums(today, "total")
            if tot["import_kwh"] > 0.5 and tot["cost"] > 0:
                avg = tot["cost"] / tot["import_kwh"]
        except Exception:  # noqa: BLE001
            pass
        neg = None
        try:
            neg = analysis_mod.neg_summary({k: b for k, b in buckets.items() if b})
        except Exception:  # noqa: BLE001
            pass
        batt = None
        try:
            from .insights import day_costs as _day_costs
            batt = analysis_mod.battery_size({k: b for k, b in buckets.items() if b}, self.insights._params, cfg,  # noqa: SLF001
                                             _day_costs, self.insights._soc0)  # noqa: SLF001
        except Exception:  # noqa: BLE001
            _LOGGER.debug("EMS: symulacja większej baterii nieudana", exc_info=True)
        auto: dict[str, Any] = {}
        try:
            prof = get_profile()
            base = getattr(prof, "base", prof)
            auto = analysis_mod.auto_cfg({k: b for k, b in buckets.items() if b}, base.as_text().replace("brak", ""),
                                         bool(getattr(base, "weekend_offpeak", True)), bool(getattr(base, "holiday_offpeak", True)))
        except Exception:  # noqa: BLE001
            _LOGGER.debug("EMS: automatyczne stawki taryf nieudane", exc_info=True)
        eff = {**auto, **cfg}                      # to, co wpisał użytkownik, ma pierwszeństwo przed wyliczonym automatycznie
        return {"batt": batt, "tariff": analysis_mod.tariff_compare(buckets, eff, today), "auto": auto,
                "sim": analysis_mod.year_sim(dict(self.insights.days), eff, avg), "cfg": cfg, "neg": neg,
                "neg_reaction": switch_on(self.hass, "negative_price_reaction", False),
                "neg_threshold": number_value(self.hass, "low_price_threshold", 0.0)}

    def analysis_set(self, data: dict) -> dict[str, Any]:
        cur = dict(self.state.get("analysis_cfg") or {})
        for k, v in (data or {}).items():
            if v is None or v == "":
                cur.pop(k, None)
            else:
                cur[k] = v
        self.state["analysis_cfg"] = analysis_mod.clean_cfg(cur)
        self._save_state()
        return self.state["analysis_cfg"]

    # --------------------------------------------- wykres produkcji PV z historią (wczoraj / jutro / zakres dni)
    def pv_chart(self, mode: str = "day", date_iso: str | None = None, days: int = 7) -> dict[str, Any]:
        """Dane do wykresu „Produkcja PV”: doba godzina po godzinie (rzeczywista z koszyków EMS, prognoza z porannego zapisu
        albo — dla jutra — bieżąca z planera) albo zakres dni (wykonanie vs prognoza dobowa)."""
        from .insights import PV as _PV
        today = dt_util.now().date()
        ins = self.insights

        def num(v: Any) -> float | None:
            try:
                x = float(v)
            except (TypeError, ValueError):
                return None
            return x if x == x and abs(x) != float("inf") else None

        def actual_for(d: date) -> list[float | None]:
            return [None if b is None or num(b[_PV]) is None else round(float(b[_PV]), 3) for b in ins._buckets(d.isoformat())]  # noqa: SLF001

        if mode == "range":
            n = max(2, min(90, int(days or 7)))
            rows: list[dict[str, Any]] = []
            for i in range(n, 0, -1):
                d = today - timedelta(days=i)
                rec = ins.fc.get(d.isoformat()) or {}
                fc, act = num(rec.get("pv_fc")), num(rec.get("pv_act"))
                if act is None:
                    hrs = [v for v in actual_for(d) if v is not None]
                    act = round(sum(hrs), 2) if len(hrs) >= 8 else None
                rows.append({"date": d.isoformat(), "pv_fc": fc, "pv_act": act})
            pairs = [(r["pv_fc"], r["pv_act"]) for r in rows if r["pv_fc"] is not None and r["pv_act"] and r["pv_act"] > 0.3]
            err = round(sum(abs(f - a) / a for f, a in pairs) / len(pairs) * 100.0, 1) if pairs else None
            return {"mode": "range", "days": n, "rows": rows, "err_pct": err,
                    "sum_act": round(sum(r["pv_act"] for r in rows if r["pv_act"] is not None), 1),
                    "sum_fc": round(sum(r["pv_fc"] for r in rows if r["pv_fc"] is not None), 1)}
        try:
            d = date.fromisoformat(str(date_iso)[:10]) if date_iso else today
        except ValueError:
            d = today
        kind = "past" if d < today else ("today" if d == today else "future")
        if d > today + timedelta(days=1) or d < today - timedelta(days=62):
            return {"mode": "day", "date": d.isoformat(), "kind": kind, "actual": None, "forecast": None,
                    "note": "Dane godzinowe są dostępne od 62 dni wstecz do jutra."}
        actual = actual_for(d) if d <= today else None
        forecast = None
        if d == today + timedelta(days=1):
            try:
                forecast = self.optimizer._read_pv_hourly(1)  # noqa: SLF001
            except Exception:  # noqa: BLE001
                forecast = None
        else:
            fh = (ins.fc.get(d.isoformat()) or {}).get("pv_fc_h")
            forecast = fh if isinstance(fh, list) and len(fh) == 24 else None
        fc24 = [None if num(v) is None else round(float(v), 3) for v in forecast] if isinstance(forecast, list) else None
        act_has = bool(actual) and any(v is not None for v in actual)
        note = None
        if not act_has and kind == "past":
            note = "Brak zapisanej produkcji z tej doby (EMS zapisuje godziny z ostatnich 62 dni)."
        elif fc24 is None and kind != "today":
            note = "Brak prognozy z tego dnia."
        return {"mode": "day", "date": d.isoformat(), "kind": kind, "actual": actual if act_has else None, "forecast": fc24,
                "sum_act": round(sum(v for v in (actual or []) if v is not None), 2) if act_has else None,
                "sum_fc": round(sum(v for v in (fc24 or []) if v is not None), 2) if fc24 else None, "note": note}

    # --------------------------------------------- pełne ładowanie co N dni (kalibracja SOC, wyrównanie ogniw)
    FULL_SOC = 98.0

    def fullcharge_state(self) -> dict[str, Any]:
        st = self.state.get("fullcharge")
        if not isinstance(st, dict):
            st = self.state["fullcharge"] = {}
        return st

    def full_charge_due(self) -> dict[str, Any] | None:
        """Czy minął termin pełnego ładowania: {"days": ile dni od ostatnich ~100%, "every": co ile} albo None (wyłączone / jeszcze nie pora)."""
        if not switch_on(self.hass, "full_charge", False):
            return None
        every = max(1, int(round(number_value(self.hass, "full_charge_days", 7.0))))
        last = self.fullcharge_state().get("last")
        today = dt_util.now().date()
        try:
            days = (today - date.fromisoformat(str(last))).days if last else None
        except ValueError:
            days = None
        if days is not None and days < every:
            return None
        return {"days": days, "every": every}

    async def fullcharge_tick(self, now: datetime) -> None:
        """Zapamiętuje dzień, w którym bateria dobiła do ~100% (z sieci albo z PV): to zeruje licznik."""
        if not switch_on(self.hass, "full_charge", False):
            return
        try:
            soc = self.optimizer._read_soc()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            return
        if isinstance(soc, (int, float)) and soc >= self.FULL_SOC:
            day = dt_util.as_local(now).date().isoformat()
            st = self.fullcharge_state()
            if st.get("last") != day:
                st["last"] = day
                self._save_state()

    # --------------------------------------------- własne ceny z PSE (RCE) → cena zakupu dopasowana do taryfy
    PRICEFEED_ENTITY = "sensor.bms_buy_rce"
    PRICEFEED_HISTORY_DAYS = 14

    def pricefeed_state(self) -> dict[str, Any]:
        st = self.state.get("pricefeed")
        if not isinstance(st, dict):
            st = self.state["pricefeed"] = {}
        return st

    def pricefeed_is_buy_source(self) -> bool:
        return str(self.optimizer.config.get(CONF_PRICE_BUY_ENTITY, "") or "") == self.PRICEFEED_ENTITY

    async def _pricefeed_fetch_day(self, d: date) -> list[float | None] | None:
        from yarl import URL
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        sess = async_get_clientsession(self.hass)
        resp = await asyncio.wait_for(sess.get(URL(pricefeed_mod.day_url(d), encoded=True)), 20)
        try:
            if resp.status != 200:
                raise RuntimeError(f"PSE odpowiedziało kodem {resp.status}")
            data = await asyncio.wait_for(resp.json(content_type=None), 20)
        finally:
            resp.release()
        return pricefeed_mod.parse_rce(data, d)

    async def pricefeed_tick(self, now: datetime) -> None:
        if not switch_on(self.hass, "price_feed", False):
            return
        st = self.pricefeed_state()
        loc = dt_util.as_local(now)
        today = loc.date()
        tom = today + timedelta(days=1)
        rce = pricefeed_mod.prune(st.get("rce"), today)
        ts = now.timestamp()
        last = float(st.get("fetched_ts") or 0.0)
        hist_missing = [(today - timedelta(days=i)) for i in range(self.PRICEFEED_HISTORY_DAYS, 0, -1)
                        if (today - timedelta(days=i)).isoformat() not in rce]
        tom_missing = tom.isoformat() not in rce
        due = (ts - last >= 3600 or (tom_missing and loc.hour >= 12 and ts - last >= 600)
               or (today.isoformat() not in rce and ts - last >= 60) or (bool(hist_missing) and ts - last >= 20))
        if not due:
            return
        st["fetched_ts"] = ts
        days = [today] + ([tom] if loc.hour >= 11 else []) + hist_missing[-4:]
        got, err = 0, None
        for d in days:
            try:
                arr = await self._pricefeed_fetch_day(d)
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"[:160]
                break
            if arr:
                rce[d.isoformat()] = arr
                got += 1
        st["rce"] = rce
        st["err"] = err
        if got:
            st["ok_at"] = loc.isoformat(timespec="minutes")
        if got and not self.pricefeed_is_buy_source():      # uczymy się tylko z PRAWDZIWEJ ceny zakupu (nie z własnej prognozy)
            fit = pricefeed_mod.fit(rce, self.insights.buy_history(today, self.PRICEFEED_HISTORY_DAYS))
            if fit:
                st["fit"] = fit
                st["fit_at"] = loc.isoformat(timespec="minutes")
        self._save_state()

    def pricefeed_payload(self) -> dict[str, Any]:
        st = self.pricefeed_state()
        now = dt_util.now()
        today = now.date()
        tom = today + timedelta(days=1)
        rce = pricefeed_mod.prune(st.get("rce"), today)
        fit = st.get("fit") if isinstance(st.get("fit"), dict) else None
        enabled = switch_on(self.hass, "price_feed", False)
        tz = lambda d: dt_util.as_local(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc)).strftime("%z")  # noqa: E731
        fmt = lambda d: (lambda z: f"{z[:3]}:{z[3:]}")(tz(d))  # noqa: E731
        p0 = pricefeed_mod.predict(rce.get(today.isoformat()), fit)
        p1 = pricefeed_mod.predict(rce.get(tom.isoformat()), fit)
        cur = p0[now.hour] if p0 else None
        note = None
        if not enabled:
            note = "Włącz przełącznik „Własne ceny z PSE (RCE)”."
        elif st.get("err"):
            note = f"Nie udało się pobrać cen z PSE: {st['err']}"
        elif not rce:
            note = "Czekam na pierwsze pobranie cen z PSE."
        elif not fit:
            note = ("Brak dopasowania do Twojej taryfy: potrzeba co najmniej 3 dób prawdziwych cen zakupu "
                    "(EMS zapisuje je godzina po godzinie). Zostaw na ten czas dotychczasowe źródło ceny zakupu.")
        return {"now": None if cur is None else round(float(cur), 4), "enabled": enabled,
                "prices_today": pricefeed_mod.series(today, p0, fmt(today)),
                "prices_tomorrow": pricefeed_mod.series(tom, p1, fmt(tom)),
                "tomorrow_available": bool(p1), "rce_today": rce.get(today.isoformat()), "rce_tomorrow": rce.get(tom.isoformat()),
                "fit": ({k: fit[k] for k in ("a", "rmse", "quality", "days", "pairs")} if fit else None),
                "fit_at": st.get("fit_at"), "ok_at": st.get("ok_at"), "error": st.get("err"), "note": note,
                "is_buy_source": self.pricefeed_is_buy_source(), "unit_of_measurement": "PLN/kWh"}

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
            prev_plan = self._plan
            self._plan = {
                "generated_at": res.get("generated_at"), "mode": res.get("mode"),
                "error": res.get("error"), "curve": res.get("curve"), "assumptions": res.get("assumptions"),
                "proposals": {k: {"proposed": p.get("proposed"), "current": p.get("current"), "skip": p.get("skip"),
                                  "label": p.get("label"), "reason": str(p.get("reason") or "")[:600],
                                  **{x: p[x] for x in ("gain_pln", "required", "confidence", "sale_kwh", "sale_gross_pln", "sale_day") if x in p}}
                              for k, p in (res.get("proposals") or {}).items()},
            }
            try:
                loc_now = dt_util.as_local(dt_util.now())
                if not self._plan.get("error") and planstory.take(self.state.setdefault("plan_snaps", {}), loc_now.date(), loc_now.hour,
                                                                  self._plan.get("proposals") or {}, self.PLAN_LOG_GROUPS_FLAT):
                    self._save_state()
                for line in planhold.stabilize(prev_plan, self._plan, self._plan_hold, loc_now.hour * 60 + loc_now.minute, force):
                    self.log.add("plan", line, "info")
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("EMS: stabilizacja planu nieudana: %s", err)
            for kind, why in self.blocked_kinds().items():
                pref = {"sell": ("bateria_sprzedaz_",), "grid": ("start_grid_charge", "stop_grid_charge")}[kind]
                for k, p in self._plan["proposals"].items():
                    if k.startswith(pref) and p.get("proposed") and not p.get("skip"):
                        p["skip"] = True
                        p["reason"] = f"Pomiń — {why}. " + p["reason"]
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
                inbox.prune_auto_skip(self.state, self._plan["proposals"])
                self._remember_grid_target(self._plan)
                self._remember_sale_power(self._plan)
                self._log_plan_decisions(self._plan)
            return self._plan

    def _plan_ttl(self) -> float:
        return PLAN_ERROR_TTL_S if (self._plan or {}).get("error") else PLAN_TTL_S

    def plan(self) -> dict[str, Any] | None:
        return self._plan

    # --------------------------------------------------------- „co EMS zrobił”, porady, test zaniku sieci, rozbudowa
    def _count_deed(self, entry: dict[str, Any]) -> None:
        cat = deeds_mod.classify(entry)
        if cat is None:
            return
        self.state["deeds"] = deeds_mod.bump(self.state.get("deeds"), dt_util.now().strftime("%Y-%m"), cat)
        self._save_state()

    def deeds_summary(self) -> dict[str, Any]:
        return deeds_mod.summary(self.state.get("deeds"), dt_util.now().strftime("%Y-%m"))

    def advice(self) -> list[dict[str, str]]:
        """Porady konfiguracji (adviser.py) z ustawień i ostatnich 14 dób; błąd jednego źródła nie blokuje reszty."""
        facts: dict[str, Any] = {}
        today = dt_util.now().date()
        try:
            facts["reserve_pct"] = number_value(self.hass, "reserve_floor_soc", 15.0)
        except Exception:  # noqa: BLE001
            pass
        try:
            socs = [b[10] for i in range(1, 15) for b in self.insights._buckets((today - timedelta(days=i)).isoformat()) if b is not None and isinstance(b[10], (int, float))]  # noqa: SLF001
            days = {(today - timedelta(days=i)).isoformat() for i in range(1, 15)
                    if any(b is not None and isinstance(b[10], (int, float)) for b in self.insights._buckets((today - timedelta(days=i)).isoformat()))}  # noqa: SLF001
            if socs:
                facts["soc_min"], facts["soc_days"] = min(socs), len(days)
        except Exception:  # noqa: BLE001
            pass
        try:
            cap = float(self.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
            s = self.stats.summary(cap)
            facts["cap_conf"], facts["cap_est"], facts["cap_samples"] = s.get("capacity_configured_kwh"), s.get("capacity_est_kwh"), s.get("capacity_samples")
        except Exception:  # noqa: BLE001
            pass
        try:
            facts["cycle_eff"] = number_value(self.hass, "cycle_efficiency", 90.0)
        except Exception:  # noqa: BLE001
            pass
        try:
            facts["battery_price"] = number_value(self.hass, "battery_price_pln", 0.0)
            facts["sell_windows_on"] = switch_on(self.hass, "bateria_sprzedaz_1", False) or switch_on(self.hass, "bateria_sprzedaz_2", False)
        except Exception:  # noqa: BLE001
            pass
        return adviser_mod.advise(facts)

    def plan_story(self) -> dict[str, Any]:
        return planstory.view(self.state.get("plan_snaps") or {}, dt_util.now().date())

    def yoy_view(self) -> dict[str, Any]:
        """Porównanie ostatnich 30 dni z tym samym okresem rok temu (yoy.py)."""
        try:
            return yoy_mod.compare(self.ledger.days, dt_util.now().date())
        except Exception:  # noqa: BLE001
            _LOGGER.debug("EMS: porównanie rok do roku nieudane", exc_info=True)
            return {"available": False, "note": "Porównanie rok do roku jest chwilowo niedostępne."}

    def wear_view(self) -> dict[str, Any]:
        try:
            wear = float(self.optimizer.wear_cost()) if hasattr(self.optimizer, "wear_cost") else 0.0
        except Exception:  # noqa: BLE001
            wear = 0.0
        return planstory.wear_days(self.ledger.days, self.stats.days, dt_util.now().date(), wear)

    def advice_done(self) -> list[dict[str, Any]]:
        """Porady zastosowane z panelu, które można cofnąć (ustawienie nadal ma wartość, jaką nadał EMS)."""
        out = []
        for aid, rec in (self.state.get("advice_applied") or {}).items():
            try:
                key, frm, to = rec["key"], float(rec["from"]), float(rec["to"])
                cur = self._profile_read(key)
            except (KeyError, TypeError, ValueError):
                continue
            if rec.get("reverted") or cur is None or abs(float(cur) - to) > 1e-6:
                continue
            out.append({"id": aid, "label": prof_mod.label(key), "from": frm, "to": to, "date": rec.get("date")})
        return out

    async def advice_apply(self, aid: str) -> dict[str, Any]:
        item = next((a for a in self.advice() if a.get("id") == aid and isinstance(a.get("apply"), dict)), None)
        if not item:
            raise ValueError("Ta porada nie jest już aktualna (ustawienie się zmieniło)")
        ap = item["apply"]
        key, to = ap["key"], float(ap["to"])
        cur = self._profile_read(key)
        if not await self._profile_write(key, to) or abs(float(self._profile_read(key) or -1e9) - to) > 1e-6:
            raise ValueError("Nie udało się ustawić wartości (sprawdź encję w ustawieniach)")
        self.state.setdefault("advice_applied", {})[aid] = {"key": key, "from": cur, "to": to, "date": dt_util.now().date().isoformat(), "reverted": False}
        self._plan_ts = 0.0
        self._save_state()
        self.log.add("mode", f"Porada „{item.get('title')}”: {prof_mod.label(key)} {cur:g} → {to:g} (zatwierdzone w panelu)", "ok")
        return {"ok": True, "key": key, "from": cur, "to": to}

    async def advice_revert(self, aid: str) -> dict[str, Any]:
        rec = (self.state.get("advice_applied") or {}).get(aid)
        done = next((d for d in self.advice_done() if d["id"] == aid), None)
        if not rec or not done:
            raise ValueError("Nie ma czego cofnąć: ustawienie zostało już zmienione inaczej albo wcześniej cofnięte")
        if not await self._profile_write(rec["key"], float(rec["from"])):
            raise ValueError("Nie udało się przywrócić poprzedniej wartości")
        rec["reverted"] = True
        self._plan_ts = 0.0
        self._save_state()
        self.log.add("mode", f"Cofnięto poradę: {done['label']} {done['to']:g} → {done['from']:g}", "ok")
        return {"ok": True, "key": rec["key"], "from": done["to"], "to": done["from"]}

    def fleet_set(self, raw: Any) -> dict[str, Any]:
        cfg = fleet_mod.sanitize(raw)
        self.state["fleet"] = cfg
        self._save_state()
        return cfg

    def fleet_get(self) -> dict[str, Any]:
        """Konfiguracja floty i bieżące sumy/alarmy z odczytów encji (moc w kW, temperatura w °C); nic nie zapisuje do urządzeń."""
        cfg = fleet_mod.sanitize(self.state.get("fleet"))
        vals: dict[str, Any] = {}
        for it in cfg["inverters"] + cfg["batteries"]:
            for k, eid in it.items():
                if not k.endswith("_eid") or not eid or eid in vals:
                    continue
                st = self.hass.states.get(eid)
                if st is None:
                    vals[eid] = {"v": None, "s": None}
                    continue
                v = state_float(self.hass, eid)
                unit = str((st.attributes or {}).get("unit_of_measurement") or "").strip().lower()
                if v is not None and k in ("pv_eid", "power_eid"):
                    v = v / 1000.0 if unit == "w" else (v * 1000.0 if unit == "mw" else v)
                vals[eid] = {"v": v, "s": st.state}
        res = fleet_mod.evaluate(cfg, vals)
        return {"config": cfg, **res, "limits": {"inverters": fleet_mod.MAX_INVERTERS, "batteries": fleet_mod.MAX_BATTERIES, "clusters": fleet_mod.MAX_CLUSTERS}}

    def price_views(self) -> dict[str, Any]:
        """Kalendarz drogich dni (30 dób, średnia cena zakupu) i mapa cieplna cen (14 dób × 24 h) z zapisanych cen; brak cen → puste."""
        today = dt_util.now().date()
        hist = self.insights.buy_history(today, 30)
        rows = []
        for d in sorted(hist):
            vals = [v for v in hist[d] if isinstance(v, (int, float))]
            if len(vals) >= 12:
                rows.append({"date": d, "avg": round(sum(vals) / len(vals), 3), "max": round(max(vals), 3)})
        avgs = sorted(r["avg"] for r in rows)
        med = avgs[len(avgs) // 2] if avgs else None
        for r in rows:
            r["level"] = "high" if med and r["avg"] >= 1.25 * med else ("low" if med and r["avg"] <= 0.8 * med else "mid")
        heat = [{"date": d, "h": [None if not isinstance(v, (int, float)) else round(v, 3) for v in hist[d]]} for d in sorted(hist)[-14:] if len(hist[d]) == 24]
        return {"calendar": rows, "median": med, "heat": heat}

    def grid_outage_test(self) -> dict[str, Any]:
        """Symulacja zaniku sieci: warianty czasu pracy z baterii przy obecnym stanie. Nic nie odcina ani nie zmienia."""
        au = self.autonomy()
        if au is None:
            return {"ok": False, "error": "Brak danych do oszacowania (poziom baterii albo pobór domu)."}
        try:
            top = self.devices.top_now()
        except Exception:  # noqa: BLE001
            top = []
        cap = float(self.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
        return {"ok": True, "soc": au["soc"], "floor": au["floor"], "load_w": au["load_w"], "usable_kwh": au["usable_kwh"],
                "scenarios": outage_mod.scenarios(au["soc"], au["floor"], cap, au["load_w"], top),
                "note": "Szacunek bez produkcji PV, przy stałym poborze. Nic nie zostało odcięte."}

    def expand_estimate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Ocena rozbudowy z własnych danych z ostatnich dób (domyślnie 60). Parametry: batt_kwh, batt_cost_per_kwh, pv_kwp, pv_now_kwp, pv_cost_per_kwp, days."""
        n = int(min(365, max(14, expand_mod._num(data.get("days")) or 60)))     # noqa: SLF001
        today = dt_util.now().date()
        keys = [(today - timedelta(days=i)).isoformat() for i in range(1, n + 1)]
        rows = [{"pv": (self.stats.days.get(k) or {}).get("pv"), "exp": (self.stats.days.get(k) or {}).get("exp")} for k in keys if k in self.stats.days]
        lds = [self.ledger.days[k] for k in keys if k in self.ledger.days]
        imp, cost = sum(v["import_kwh"] for v in lds), sum(v["cost"] for v in lds)
        exp_, rev = sum(v["export_kwh"] for v in lds), sum(v["revenue"] for v in lds)
        out: dict[str, Any] = {"ok": True, "days": len(rows), "battery": None, "pv": None, "avg_buy": None, "avg_sell": None}
        if imp <= 0 or exp_ <= 0 or len(rows) < expand_mod.MIN_DAYS:
            return {**out, "ok": False, "error": f"Za mało danych: potrzeba co najmniej {expand_mod.MIN_DAYS} dób z zakupem i sprzedażą energii (jest {len(rows)})."}
        buy, sell = cost / imp, rev / exp_
        out["avg_buy"], out["avg_sell"] = round(buy, 3), round(sell, 3)
        cap = float(self.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
        bp, cyc = number_value(self.hass, "battery_price_pln", 0.0), number_value(self.hass, "battery_cycles", 6000.0)
        wear = (bp / (cyc * cap)) if bp > 0 and cyc > 0 and cap > 0 else 0.0
        if data.get("batt_kwh") not in (None, ""):
            out["battery"] = expand_mod.battery(rows, data.get("batt_kwh"), data.get("batt_cost_per_kwh"), buy, sell, wear)
        if data.get("pv_kwp") not in (None, ""):
            out["pv"] = expand_mod.pv(rows, data.get("pv_kwp"), data.get("pv_now_kwp"), data.get("pv_cost_per_kwp"), buy, sell)
        if out["battery"] is None and out["pv"] is None:
            out["ok"] = False
            out["error"] = "Podaj parametry rozbudowy (bateria: kWh i zł/kWh; panele: kWp, obecna moc i zł/kWp)."
        out["note"] = "Szacunek rzędu wielkości z danych z ostatnich dób (sezon wpływa na wynik), bez dotacji, podatków i zmian cen."
        return out

    # --------------------------------------------------------- rachunek: prognoza, cel, rozbicie, skarbonka
    def bill(self) -> dict[str, Any]:
        """Prognoza bilansu do końca miesiąca, cel miesięczny, rozbicie bieżącego miesiąca i „skarbonka”. Każda część osobno odporna na błąd."""
        now = dt_util.now()
        today = now.date()
        out: dict[str, Any] = {"forecast": None, "goal": None, "goal_value": 0.0, "breakdown": [], "month_title": None, "piggy": None}
        try:
            nets = {k: self.ledger.net(v) for k, v in self.ledger.days.items()}
            fc = bill_mod.forecast(nets, today, (now.hour * 60 + now.minute) / 1440.0)
            out["forecast"] = fc
            out["goal_value"] = number_value(self.hass, "monthly_goal_pln", 0.0)
            out["goal"] = bill_mod.goal_status(fc, out["goal_value"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: prognoza rachunku: %s", err)
        try:
            rep = self.monthly_report()
            out["breakdown"] = bill_mod.breakdown(rep)
            out["month_title"] = rep.get("title")
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: rozbicie rachunku: %s", err)
        try:
            tot = self.insights.savings(today)["total"]
            cfg = analysis_mod.clean_cfg(self.state.get("analysis_cfg"))
            invest = (cfg.get("invest_pv") or 0.0) + (cfg.get("invest_batt") or 0.0)
            out["piggy"] = bill_mod.piggy(tot["vs_nobat"], invest or None, tot["days"], today)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: skarbonka: %s", err)
        return out

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
        pm = (prev.replace(day=1) - timedelta(days=1))
        prev_rep = None
        try:
            prev_rep = self.monthly_report(pm.year, pm.month)
        except Exception:  # noqa: BLE001
            prev_rep = None
        text = report_mod.report_table_text(rep, prev_rep)
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
            lines = [f"Tydzień {start:%d.%m}–{day:%d.%m} (dni z danymi: {t['days']})"]
            lines += summtable_mod.week_lines(
                summtable_mod.week_days(lambda a, b: report_mod.period_totals(self.ledger, self.stats, a, b), start, day),
                p["net"] if p["days"] else None)
            cmp = report_mod.compare_line(t["net"], p["net"] if p["days"] else None, "poprzedniego tygodnia")
            if cmp:
                lines.append(cmp)
            try:
                lines.extend(money_mod.lines(self.ledger, self.stats, day, "week", start))
            except Exception:  # noqa: BLE001
                pass
            try:
                wl = review_mod.week_line(self.state.get("day_reviews"), start.isoformat(), day.isoformat())
                if wl:
                    lines.append(wl)
            except Exception:  # noqa: BLE001
                pass
            try:
                al = arb_mod.week_line(self.state.get("arb_proof"), start.isoformat(), day.isoformat(), self.arb_tol())
                if al:
                    lines.append(al)
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
        lines = summtable_mod.day_lines(t, report_mod.period_totals(self.ledger, self.stats, day - timedelta(days=1), day - timedelta(days=1)))
        try:
            lines.extend(money_mod.lines(self.ledger, self.stats, day, "day"))
        except Exception:  # noqa: BLE001
            pass
        sd = self.state.get("soc_day") or {}
        if sd.get("date") == day.isoformat():
            lines.append(f"SOC: min {float(sd['min']):.0f}%, max {float(sd['max']):.0f}%")
        try:
            lines.extend(self._plan_vs_actual_lines(day))
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: podsumowanie plan vs wykonanie: %s", err)
        try:
            ar = next((r for r in self.arb_proof(40) if r["date"] == day.isoformat()), None)
            if ar and ar["level"] != "idle":
                lines.append(arb_mod.line(ar))
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: dowód braku arbitrażu: %s", err)
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

    def _plan_vs_actual_lines(self, day) -> list[str]:
        """Wiersze podsumowania dnia: plan kontra wykonanie (prognoza PV, sprzedaż z baterii), blokady i zmiany automatu,
        energia z sieci pozostała w baterii."""
        fmt = lambda v, n=1: f"{v:.{n}f}".replace(".", ",")  # noqa: E731
        key = day.isoformat()
        out: list[str] = []
        rec = self.insights.fc.get(key) or {}
        pv_fc = rec.get("pv_fc")
        pv_act = (self.coordinator.data or {}).get("energy_pv_today") if day == dt_util.now().date() else rec.get("pv_act")
        if pv_act is None:
            pv_act = rec.get("pv_act")
        if isinstance(pv_fc, (int, float)) and isinstance(pv_act, (int, float)):
            diff = f" ({(float(pv_act) - pv_fc) / pv_fc * 100:+.0f}%)" if pv_fc >= 0.5 else ""
            out.append(f"PV: prognoza {fmt(pv_fc)} kWh, wykonanie {fmt(float(pv_act))} kWh{diff}")
        plan = (self.state.get("sale_plan") or {}).get(key)
        act = (self.state.get("sale_actual") or {}).get(key) or {"kwh": 0.0, "rev": 0.0}
        if plan:
            out.append(f"Sprzedaż z baterii: plan ~{fmt(plan['kwh'])} kWh / {fmt(plan['gross'], 2)} zł, "
                       f"w oknach sprzedaży wyeksportowano {fmt(act['kwh'])} kWh / {fmt(act['rev'], 2)} zł")
        elif act["kwh"] >= 0.05:
            out.append(f"Sprzedaż z baterii: bez planu, w oknach sprzedaży wyeksportowano {fmt(act['kwh'])} kWh / {fmt(act['rev'], 2)} zł")
        guards, autos = self._day_guard_counts(key)
        if guards or autos:
            out.append(f"Zabezpieczenia zadziałały: {guards}×, zmiany automatu: {autos}×")
        gb = self.grid_batt_kwh()
        if gb >= 0.1 and day == dt_util.now().date():
            out.append(f"W baterii zostało ~{fmt(gb)} kWh energii z sieci (sprzedaż zablokowana, aż dom ją zużyje)")
        # ocena planu: dla dnia z przeszłości — jego własna; w podsumowaniu „dzisiaj” — wczorajsza (dzisiejsza powstaje dopiero po północy)
        rkey = (day - timedelta(days=1)).isoformat() if day == dt_util.now().date() else key
        rev = (self.state.get("day_reviews") or {}).get(rkey)
        if review_mod.valid(rev):
            out.append(str(rev.get("line") or review_mod.summary_line(rev)))
        return out

    def _day_guard_counts(self, key: str) -> tuple[int, int]:
        """Ile razy tego dnia zadziałały zabezpieczenia (ostrzeżenia „guard”) i ile zmian zrobił automat."""
        ents = [e for e in self.log.last(400) if str(e.get("ts", "")).startswith(key)]
        guards = sum(1 for e in ents if e.get("kind") == "guard" and e.get("level") == "warn")
        autos = sum(1 for e in ents if e.get("kind") == "auto" and e.get("level") in ("ok", "warn"))
        return guards, autos

    # --------------------------------------------------------------- profile pracy (zima / lato / urlop / burza)
    def _profile_read(self, key: str) -> Any:
        """Bieżąca wartość ustawienia integracji: bool (przełącznik), float (liczba) albo None, gdy encja niedostępna."""
        k = prof_mod.kind(key)
        if k is None:
            return None
        raw = state_str(self.hass, find_eid(self.hass, k, key))
        if raw is None:
            return None
        if k == "switch":
            return True if raw == "on" else (False if raw == "off" else None)
        try:
            x = float(raw)
        except (TypeError, ValueError):
            return None
        return x if math.isfinite(x) else None

    async def _profile_write(self, key: str, value: Any) -> bool:
        k = prof_mod.kind(key)
        cv = prof_mod.check_value(key, value)
        if k is None or cv is None:
            return False
        eid = find_eid(self.hass, k, key)
        try:
            if k == "switch":
                await self.hass.services.async_call("switch", "turn_on" if cv else "turn_off", {"entity_id": eid}, blocking=True)
            else:
                await self.hass.services.async_call("number", "set_value", {"entity_id": eid, "value": cv}, blocking=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS: profil — nie udało się ustawić %s: %s", eid, err)
            return False
        return True

    def profile_view(self) -> dict[str, Any]:
        """Dane dla karty: lista profili z podglądem zmian, aktywny profil i możliwość powrotu."""
        cur = prof_mod.clean_state(self.state.get("profile"))
        active = None
        if cur:
            active = {"id": cur["id"], "since": cur["since"], "ended": cur["ended"], "can_revert": bool(cur["prev"]),
                      "name": self._profile_name(cur["id"], None),
                      "restore": [{"key": k, "label": prof_mod.label(k), "now_text": prof_mod.fmt(k, self._profile_read(k)),
                                   "prev_text": prof_mod.fmt(k, v)} for k, v in cur["prev"].items()]}
        profiles = []
        for p in list(prof_mod.PROFILES) + self._custom_profiles():
            ch = prof_mod.changes(p, self._profile_read)
            profiles.append({"id": p["id"], "name": p["name"], "icon": p["icon"], "desc": p["desc"], "changes": ch,
                             "custom": bool(p.get("custom")),
                             "active": bool(cur and cur["id"] == p["id"] and not cur["ended"]),
                             "nothing_to_change": not any(c["differs"] for c in ch if c["available"])})
        plan = prof_mod.clean_plan(self.state.get("profile_plan"))
        plan_v = None
        if plan:
            plan_v = dict(plan, name=self._profile_name(plan["id"], None), phase=prof_mod.plan_phase(plan, dt_util.now().date()))
        return {"profiles": profiles, "active": active, "plan": plan_v, "custom_limit": prof_mod.MAX_CUSTOM,
                "custom_keys": [{"key": k, "label": prof_mod.label(k)} for k in prof_mod.CUSTOM_KEYS],
                "icons": list(prof_mod.CUSTOM_ICONS)}

    # --- własne profile i profil z datami
    def _custom_profiles(self) -> list[dict[str, Any]]:
        return prof_mod.clean_custom(self.state.get("custom_profiles"))

    def _profile_def(self, pid: Any) -> dict[str, Any] | None:
        return prof_mod.find(pid, self._custom_profiles())

    def _profile_name(self, pid: Any, default: Any) -> Any:
        p = self._profile_def(pid)
        if p:
            return p["name"]
        return "Własny profil (usunięty)" if prof_mod.is_custom_id(pid) else default

    def profile_save(self, name: Any, icon: Any = None) -> dict[str, Any]:
        """Zapisuje bieżące ustawienia (tylko z listy CUSTOM_KEYS) jako własny profil; ta sama nazwa = nadpisanie."""
        new, rec, replaced = prof_mod.make_custom(name, icon, self._profile_read, self.state.get("custom_profiles"),
                                                  dt_util.now().isoformat(timespec="seconds"))
        self.state["custom_profiles"] = new
        self._save_state()
        self.log.add("mode", f"Zapisano własny profil „{rec['name']}” ({prof_mod.settings_word(len(rec['set']))})" + (" — nadpisano poprzedni o tej nazwie" if replaced else ""), "ok")
        return {"ok": True, "id": rec["id"], "replaced": replaced}

    def settings_export(self) -> dict[str, Any]:
        """Kopia ustawień EMS do pliku (settingsio.py)."""
        from .const import VERSION
        return settingsio.build(self._profile_read, self.state, VERSION, dt_util.now().isoformat(timespec="seconds"))

    async def settings_import(self, data: Any, apply: bool) -> dict[str, Any]:
        """Podgląd (apply=False) albo wczytanie (apply=True) pliku ustawień. ValueError z polskim opisem przy złym pliku."""
        pl = settingsio.plan(settingsio.parse(data), self._profile_read, self.state)
        out = {"changes": [{k: c[k] for k in ("key", "label", "now", "to")} for c in pl["changes"]],
               "skipped": pl["skipped"], "extras": pl["extras"], "applied": False, "failed": []}
        if not apply:
            return out
        failed = []
        for c in pl["changes"]:
            if not await self._profile_write(c["key"], c["value"]):
                failed.append(c["key"])
        if pl["profiles"]:
            self.state["custom_profiles"] = pl["profiles"]
        if pl["notify_cfg"]:
            self.state["notify_cfg"] = pl["notify_cfg"]
        if pl["analysis_cfg"]:
            self.state["analysis_cfg"] = pl["analysis_cfg"]
        self._save_state()
        self.log.add("mode", f"Wczytano ustawienia z pliku: zmieniono {len(pl['changes']) - len(failed)}"
                             + (f", nieudane: {', '.join(failed)}" if failed else "")
                             + (f", {', '.join(pl['extras'])}" if pl["extras"] else ""), "warn" if failed else "ok")
        out.update(applied=True, failed=failed)
        return out

    def profile_delete(self, pid: Any) -> dict[str, Any]:
        if not prof_mod.is_custom_id(pid):
            raise ValueError("Można usunąć tylko własny profil")
        cur = self._custom_profiles()
        rec = next((c for c in cur if c["id"] == pid), None)
        if rec is None:
            raise ValueError("Nie ma takiego profilu")
        self.state["custom_profiles"] = [c for c in cur if c["id"] != pid]
        plan = prof_mod.clean_plan(self.state.get("profile_plan"))
        dropped_plan = bool(plan and plan["id"] == pid and plan["status"] == "waiting")
        if dropped_plan:
            self.state["profile_plan"] = None           # zaplanowany, a jeszcze niezaczęty — nie ma czego włączać
        self._save_state()
        self.log.add("mode", f"Usunięto własny profil „{rec['name']}”" + (" i jego plan z datami" if dropped_plan else ""), "ok")
        return {"ok": True, "dropped_plan": dropped_plan}

    def profile_schedule(self, pid: Any, d_from: Any, d_to: Any) -> dict[str, Any]:
        """Planuje profil na zakres dat (od pierwszego dnia 00:00 do końca ostatniego dnia). Jeden plan naraz."""
        plan = prof_mod.check_plan(pid, d_from, d_to, dt_util.now().date(), self._custom_profiles())
        old = prof_mod.clean_plan(self.state.get("profile_plan"))
        if old and old["status"] == "active":
            raise ValueError("Poprzedni plan jeszcze trwa — anuluj go albo poczekaj do końca")
        self.state["profile_plan"] = plan
        self._save_state()
        self.log.add("mode", f"Zaplanowano profil „{self._profile_name(pid, pid)}” od {plan['from']} do {plan['to']} (włącza się sam, po ostatnim dniu wraca do poprzednich ustawień)", "ok")
        return {"ok": True, "plan": plan}

    async def profile_schedule_clear(self) -> dict[str, Any]:
        """Anuluje plan. Trwający plan: kończy go od razu (cofa profil, jeśli to nadal ten sam, i wraca do poprzedniego)."""
        plan = prof_mod.clean_plan(self.state.get("profile_plan"))
        if not plan:
            self.state["profile_plan"] = None
            raise ValueError("Nie ma zaplanowanego profilu")
        if plan["status"] == "active":
            await self._profile_plan_finish(plan, "anulowany")
        else:
            self.state["profile_plan"] = None
            self._save_state()
            self.log.add("mode", f"Anulowano zaplanowany profil „{self._profile_name(plan['id'], plan['id'])}”", "ok")
        return {"ok": True}

    async def _profile_plan_finish(self, plan: dict[str, Any], how: str) -> None:
        name = self._profile_name(plan["id"], plan["id"])
        cur = prof_mod.clean_state(self.state.get("profile"))
        reverted = False
        if cur and cur["id"] == plan["id"]:
            await self._profile_restore(cur, quiet=True)
            self.state["profile"] = None
            reverted = True
            self._plan_ts = 0.0
            self._reserve_cache = None
        resumed = None
        if reverted and plan.get("resume") and self._profile_def(plan["resume"]):
            try:
                await self.apply_profile(plan["resume"])
                resumed = self._profile_name(plan["resume"], plan["resume"])
            except ValueError:
                resumed = None
        self.state["profile_plan"] = None
        self._save_state()
        txt = (f"Profil „{name}” {how}: " + ("przywrócono poprzednie ustawienia" if reverted else "nic do przywracania (profil był już zmieniony lub cofnięty ręcznie)")
               + (f"; wrócił profil „{resumed}”" if resumed else ""))
        self.log.add("mode", txt, "ok")
        await self.monitor.notifier.send("profile_plan", f"📅 EMS: koniec profilu „{name}”", txt + ".", level="info")

    async def profile_plan_tick(self, now: datetime) -> None:
        """Start planu pierwszego dnia (po 00:00) i koniec po ostatnim dniu. Po restarcie HA nadrabia: spóźniony start nadal włącza profil,
        o ile ostatni dzień jeszcze trwa; plan, którego termin w całości minął, jest odrzucany z wpisem w dzienniku."""
        raw = self.state.get("profile_plan")
        if raw is None:
            return
        plan = prof_mod.clean_plan(raw)
        if plan is None:
            self.state["profile_plan"] = None
            self._save_state()
            return
        today = dt_util.as_local(now).date()
        phase = prof_mod.plan_phase(plan, today)
        name = self._profile_name(plan["id"], None)
        if plan["status"] == "waiting":
            if phase == "before":
                return
            if phase == "after" or name is None or self._profile_def(plan["id"]) is None:
                self.state["profile_plan"] = None
                self._save_state()
                why = "termin już minął" if phase == "after" else "profil został usunięty"
                self.log.add("mode", f"Zaplanowany profil „{name or plan['id']}” nie został włączony: {why}", "warn")
                await self.monitor.notifier.send("profile_plan", "📅 EMS: plan profilu nie wystartował", f"Profil „{name or plan['id']}” (od {plan['from']} do {plan['to']}) nie został włączony: {why}.", level="warn")
                return
            before = prof_mod.clean_state(self.state.get("profile"))
            resume = before["id"] if before and not before["ended"] and before["id"] != plan["id"] else None
            res = await self.apply_profile(plan["id"])
            self.state["profile_plan"] = dict(plan, status="active", resume=resume)
            self._save_state()
            txt = f"Zaplanowany profil „{name}” włączony (do końca dnia {plan['to']}): zmieniono {prof_mod.settings_word(res.get('changed', 0))}"
            self.log.add("mode", txt, "ok")
            await self.monitor.notifier.send("profile_plan", f"📅 EMS: włączono profil „{name}”", txt + ". Po ostatnim dniu ustawienia wrócą same.", level="info")
            return
        if phase == "after":
            await self._profile_plan_finish(plan, "zakończony (minął ostatni dzień)")

    async def apply_profile(self, pid: str) -> dict[str, Any]:
        """Stosuje profil: najpierw cofa poprzedni (tylko nietknięte ręcznie wartości), potem zapamiętuje stan i ustawia nowe wartości."""
        prof = self._profile_def(pid)
        if prof is None:
            raise ValueError(f"nieznany profil: {pid!r}")
        cur = prof_mod.clean_state(self.state.get("profile"))
        if cur:
            await self._profile_restore(cur, quiet=True)
        prev: dict[str, Any] = {}
        applied: dict[str, Any] = {}
        skipped: list[str] = []
        for key, target in prof["set"].items():
            now = self._profile_read(key)
            if now is None:
                skipped.append(prof_mod.label(key))
                continue
            if prof_mod.same(now, target):
                continue                                   # już ustawione — nie ruszamy i nie zapamiętujemy do cofnięcia
            if await self._profile_write(key, target) and prof_mod.same(self._profile_read(key), target):   # odczyt zwrotny
                prev[key], applied[key] = now, prof_mod.check_value(key, target)
            else:
                skipped.append(prof_mod.label(key))
        # wartości, które i tak były już zgodne z profilem, też należą do niego (do wykrywania, że profil przestał obowiązywać)
        for key, target in prof["set"].items():
            if key not in applied and self._profile_read(key) is not None and prof_mod.same(self._profile_read(key), target):
                applied[key] = prof_mod.check_value(key, target)
        since = dt_util.now().isoformat(timespec="seconds")
        self.state["profile"] = {"id": pid, "since": since, "prev": prev, "applied": applied, "ended": None}
        if pid == "storm":
            self.state["storm_until"] = None               # czas trwania liczony od teraz (modes_tick ustawi nowy)
        self._plan_ts = 0.0
        self._reserve_cache = None
        self._save_state()
        txt = f"Włączono profil „{prof['name']}”: zmieniono {prof_mod.settings_word(len(prev))}" + (f", pominięto {len(skipped)} (brak encji lub zapis nie zadziałał)" if skipped else "")
        self.log.add("mode", txt, "ok" if not skipped else "warn", profile=pid)
        return {"ok": True, "id": pid, "changed": len(prev), "skipped": skipped}

    async def _profile_restore(self, cur: dict[str, Any], quiet: bool = False) -> dict[str, Any]:
        restored, kept = 0, []
        for key, old in cur["prev"].items():
            now = self._profile_read(key)
            if now is not None and prof_mod.same(now, old):
                restored += 1                              # już jest tak jak przed profilem (np. tryb burzowy wygasł sam)
                continue
            if now is not None and not prof_mod.same(now, cur["applied"].get(key)):
                kept.append(prof_mod.label(key))           # po profilu zmieniono ręcznie — zostaje, jak jest
                continue
            if await self._profile_write(key, old):
                restored += 1
        if not quiet:
            name = self._profile_name(cur["id"], cur["id"])
            self.log.add("mode", f"Cofnięto profil „{name}”: przywrócono {prof_mod.settings_word(restored)}" + (f", {len(kept)} zostawiono (zmienione ręcznie)" if kept else ""),
                         "ok", profile=cur["id"])
        return {"restored": restored, "kept": kept}

    async def revert_profile(self) -> dict[str, Any]:
        cur = prof_mod.clean_state(self.state.get("profile"))
        if not cur:
            self.state["profile"] = None
            raise ValueError("żaden profil nie jest zastosowany")
        res = await self._profile_restore(cur)
        self.state["profile"] = None
        self._plan_ts = 0.0
        self._reserve_cache = None
        self._save_state()
        return {"ok": True, **res}

    async def profile_tick(self, now: datetime) -> None:
        """Profil przestaje obowiązywać, gdy któreś z jego ustawień ma dziś inną wartość (ręczna zmiana albo samoczynne wygaśnięcie
        trybu burzowego). Nic wtedy nie cofamy — tylko zapisujemy, że profil się skończył, i zostawiamy możliwość powrotu."""
        raw = self.state.get("profile")
        if raw is None:
            return
        cur = prof_mod.clean_state(raw)
        if cur is None:
            self.state["profile"] = None
            self._save_state()
            return
        if cur["ended"]:
            return
        bad = prof_mod.drifted(cur["applied"], self._profile_read)
        if not bad:
            return
        cur["ended"] = {"at": dt_util.as_local(now).isoformat(timespec="seconds"), "keys": bad[:20]}
        self.state["profile"] = cur
        self._save_state()
        name = self._profile_name(cur["id"], cur["id"])
        self.log.add("mode", f"Profil „{name}” przestał obowiązywać (zmienione: {', '.join(prof_mod.label(k) for k in bad[:4])})", "info", profile=cur["id"])

    # --------------------------------------------------------------- autokorekta ostrożności prognozy PV
    def pv_caution(self) -> dict[str, Any]:
        """Widok dla karty: bieżąca ostrożność, propozycja zmiany (z ocen z ostatnich dób) i ostatnia zmiana do cofnięcia."""
        cur = self._profile_read(pvc_mod.KEY)
        st = self.state.get("pv_caution")
        out: dict[str, Any] = {"current": cur, "proposal": None, "last": None, "can_revert": False}
        last = pvc_mod.clean_state(st)["last"]
        if last:
            out["last"] = dict(last)
            out["can_revert"] = pvc_mod.can_revert(st, cur) is not None
        if cur is None or not switch_on(self.hass, "pv_forecast_correction", True):
            return out                      # bez korekty planer w ogóle nie stosuje ostrożności — nie ma co proponować
        today = dt_util.now().date()
        try:
            lo = None
            try:
                lo = self.optimizer.pv_lo_ratio(1, self.optimizer._read_pv_hourly(1))  # noqa: SLF001
            except Exception:  # noqa: BLE001
                lo = None
            out["proposal"] = pvc_mod.evaluate(self.insights.pv_caution_pairs(today), cur, today, st, lo)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: autokorekta ostrożności PV: %s", err)
        return out

    def _profile_follow(self, key: str, old: Any, new: Any) -> None:
        """Aktywny profil nie ma uznać zmiany ostrożności zrobionej przez autokorektę za ręczną (inaczej „przestałby obowiązywać”)."""
        cur = prof_mod.clean_state(self.state.get("profile"))
        if cur and not cur["ended"] and key in cur["applied"] and prof_mod.same(cur["applied"][key], old):
            raw = self.state.get("profile")
            if isinstance(raw, dict) and isinstance(raw.get("applied"), dict):
                raw["applied"][key] = new

    async def pv_caution_apply(self) -> dict[str, Any]:
        view = self.pv_caution()
        prop = view["proposal"]
        if not prop:
            raise ValueError("Nie ma teraz propozycji zmiany ostrożności (dane się zmieniły albo już ją zastosowano)")
        cur, to = view["current"], prop["to"]
        if not await self._profile_write(pvc_mod.KEY, to) or not prof_mod.same(self._profile_read(pvc_mod.KEY), to):
            raise ValueError("Nie udało się ustawić ostrożności prognozy PV (sprawdź encję w ustawieniach)")
        self.state["pv_caution"] = {"last": {"date": dt_util.now().date().isoformat(), "from": cur, "to": to, "reverted": False}, "dismissed": None}
        self._profile_follow(pvc_mod.KEY, cur, to)
        self._plan_ts = 0.0
        self._save_state()
        self.log.add("mode", f"Ostrożność prognozy PV: {cur:.0f}% → {to:.0f}% (propozycja z ocen dobowych, zatwierdzona w panelu)", "ok")
        return {"ok": True, "from": cur, "to": to}

    async def pv_caution_revert(self) -> dict[str, Any]:
        cur = self._profile_read(pvc_mod.KEY)
        last = pvc_mod.can_revert(self.state.get("pv_caution"), cur)
        if not last:
            raise ValueError("Nie ma czego cofnąć: ostrożność została już zmieniona inaczej albo wcześniej cofnięta")
        if not await self._profile_write(pvc_mod.KEY, last["from"]) or not prof_mod.same(self._profile_read(pvc_mod.KEY), last["from"]):
            raise ValueError("Nie udało się przywrócić poprzedniej ostrożności")
        self.state["pv_caution"] = {"last": dict(last, reverted=True), "dismissed": dt_util.now().date().isoformat()}
        self._profile_follow(pvc_mod.KEY, last["to"], last["from"])
        self._plan_ts = 0.0
        self._save_state()
        self.log.add("mode", f"Cofnięto zmianę ostrożności prognozy PV: {last['to']:.0f}% → {last['from']:.0f}%", "ok")
        return {"ok": True, "from": last["to"], "to": last["from"]}

    def pv_caution_dismiss(self) -> dict[str, Any]:
        st = pvc_mod.clean_state(self.state.get("pv_caution"))
        st["dismissed"] = dt_util.now().date().isoformat()
        self.state["pv_caution"] = st
        self._save_state()
        return {"ok": True}

    # --------------------------------------------------------------- ocena planu po dobie
    def build_day_review(self, day: date) -> dict[str, Any] | None:
        """Plan z rana kontra to, co się stało: PV, zużycie, SOC, sprzedaż z baterii (czysta ocena w review.py)."""
        key = day.isoformat()
        rec = self.insights.fc.get(key) or {}
        row = next((r for r in (self.state.get("accuracy") or []) if isinstance(r, dict) and r.get("date") == key), {})
        lf = getattr(self.coordinator, "load_forecast", None)

        def pick(*vals):
            return next((v for v in vals if v is not None), None)

        pv_fc = pick(rec.get("pv_fc"), row.get("pv_fc"))
        pv_act = pick(rec.get("pv_act"), row.get("pv"))
        load_fc = pick((getattr(lf, "forecast_history", None) or {}).get(key), row.get("load_fc"))
        load_act = pick((getattr(lf, "days", None) or {}).get(key), row.get("load"))
        soc_act = rec.get("soc_act")
        if soc_act is None and rec.get("soc_plan") is not None:      # doba jeszcze niezamknięta w statystykach: weź SOC z godzin
            try:
                soc_act = [None if b is None else b[_INS_SOC] for b in self.insights._buckets(key)]  # noqa: SLF001
            except Exception:  # noqa: BLE001
                soc_act = None
        guards, autos = self._day_guard_counts(key)
        try:
            net = self.ledger.day_net(day)
        except Exception:  # noqa: BLE001
            net = None
        sale_plan = (self.state.get("sale_plan") or {}).get(key)
        sale_act = (self.state.get("sale_actual") or {}).get(key)
        sale_why = None
        if sale_plan:
            try:
                socs = [float(x) for x in (soc_act or []) if isinstance(x, (int, float)) and not isinstance(x, bool)]
                sale_why = review_mod.sale_reason(self.log.last(600), key, soc_max=max(socs) if socs else None,
                                                  min_soc=number_value(self.hass, "min_soc_for_sell", 0.0))
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("EMS: powód braku sprzedaży: %s", err)
        return review_mod.build(key, pv_fc=pv_fc, pv_act=pv_act, pv_limited=rec.get("pv_lim"), load_fc=load_fc, load_act=load_act,
                                soc_plan=rec.get("soc_plan"), soc_act=soc_act, sale_plan=sale_plan, sale_act=sale_act,
                                sale_why=sale_why, net=net, guards=guards, autos=autos)

    def store_day_review(self, rev: dict[str, Any]) -> None:
        review_mod.store(self.state.setdefault("day_reviews", {}), rev)
        self.log.add("profit", rev.get("line") or review_mod.summary_line(rev), "ok" if rev["verdict"] == "trafny" else "info",
                     verdict=rev["verdict"], score=rev.get("score"))

    def day_reviews(self, n: int = 14) -> list[dict[str, Any]]:
        return review_mod.recent(self.state.get("day_reviews"), n)

    async def review_tick(self, now: datetime) -> None:
        """Po północy: ocena wczorajszego planu (raz na dobę). Czeka, aż statystyki zamkną dobę (SOC z całego dnia);
        od 2:00 ocenia z tym, co jest."""
        loc = dt_util.as_local(now)
        day = loc.date() - timedelta(days=1)
        key = day.isoformat()
        if self.state.get("review_done") == key:
            return
        rec = self.insights.fc.get(key)
        if not (rec is not None and "soc_act" in rec) and loc.hour < 2:
            return
        self.state["review_done"] = key
        rev = self.build_day_review(day)
        if rev is not None:
            self.store_day_review(rev)
        self._save_state()

    # --------------------------------------------------------------- tick / listenery
    async def tick(self, now: datetime) -> None:
        for name, coro in (
            ("snapshot", None),
            ("tryby", self.modes_tick),
            ("ceny", self.price_reaction_tick),
            ("ceny z PSE", self.pricefeed_tick),
            ("pełne ładowanie", self.fullcharge_tick),
            ("nadpisania", self.override_tick),
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
            ("naprawa danych", self.store_repair_tick),
            ("ocena planu", self.review_tick),
            ("profil", self.profile_tick),
            ("profil z datami", self.profile_plan_tick),
            ("problemy", self.issues_tick),
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
        try:
            from .automation import async_live_apply, async_morning_guard, async_notify_sets_off
            await async_live_apply(self, self.hass, self._plan, now)
            await async_notify_sets_off(self, self.hass, self._plan, now)
            await async_morning_guard(self, self.hass, self._plan, now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS auto-stosowanie z planu: %s", err, exc_info=True)

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

    SALE_KEEP_DAYS = 14

    def _track_sale(self, now: datetime) -> None:
        """Ile faktycznie wyeksportowano do sieci w oknach sprzedaży (tryb eksportu) — do porównania z planem.

        Uwaga: w trybie eksportu do sieci idzie też nadwyżka PV, więc to eksport w oknach sprzedaży, a nie sama energia z baterii."""
        prev = getattr(self, "_sale_ts", None)
        self._sale_ts = now
        local = dt_util.as_local(now)
        today = local.date().isoformat()
        done = self.state.get("sale_report_done")
        if done != today:                                      # pierwsza chwila nowej doby: podsumuj wczoraj
            self.state["sale_report_done"] = today
            if done is not None:
                self._sale_report(local.date() - timedelta(days=1))
        gp = self.grid_power()
        if prev is None or gp is None or gp >= 0 or not self.is_selling():
            return
        dt_s = (now - prev).total_seconds()
        if dt_s <= 0 or dt_s > 120 or abs(gp) > 100000:
            return
        kwh = abs(gp) * dt_s / 3_600_000.0
        price = self.sell_price()
        act = self.state.setdefault("sale_actual", {}).setdefault(today, {"kwh": 0.0, "rev": 0.0})
        act["kwh"] += kwh
        if price is not None:
            act["rev"] += kwh * price
        self._save_state()

    def _sale_report(self, day: date) -> None:
        """Wpis w dzienniku: plan vs faktyczny eksport w oknach sprzedaży za dzień `day`; porządkuje stare dane."""
        key = day.isoformat()
        try:
            ar = next((r for r in self.arb_proof(40) if r["date"] == key), None)
            if ar and ar["level"] != "idle":
                self.log.add("profit", arb_mod.line(ar), {"ok": "ok", "warn": "warn", "bad": "warn"}.get(ar["level"], "info"), leak=ar["leak"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: wpis o arbitrażu: %s", err)
        plan = (self.state.get("sale_plan") or {}).get(key)
        act = (self.state.get("sale_actual") or {}).get(key) or {"kwh": 0.0, "rev": 0.0}
        cut = (day - timedelta(days=self.SALE_KEEP_DAYS)).isoformat()
        for name in ("sale_plan", "sale_actual"):
            d = self.state.get(name)
            if isinstance(d, dict):
                for k in [k for k in d if k < cut]:
                    d.pop(k, None)
        if not plan and act["kwh"] < 0.05:
            return
        fmt = lambda v: f"{v:.2f}".replace(".", ",")  # noqa: E731
        if plan:
            msg = (f"Sprzedaż {key}: plan ~{plan['kwh']:.1f} kWh / {fmt(plan['gross'])} zł; w oknach sprzedaży wyeksportowano "
                   f"{act['kwh']:.1f} kWh / {fmt(act['rev'])} zł (zysk netto planu ~{fmt(plan.get('net', 0.0))} zł)")
            level = "warn" if act["kwh"] < 0.5 * plan["kwh"] else "ok"
        else:
            msg = f"Sprzedaż {key}: bez planu, ale w oknach sprzedaży wyeksportowano {act['kwh']:.1f} kWh / {fmt(act['rev'])} zł"
            level = "info"
        self.log.add("profit", msg, level, plan_kwh=(plan or {}).get("kwh"), actual_kwh=round(act["kwh"], 2),
                     actual_pln=round(act["rev"], 2))

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
            self._track_load(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS wygładzony pobór domu: %s", err)
        try:
            self._track_grid_batt(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS licznik energii z sieci w baterii: %s", err)
        try:
            self._track_sale(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS rozliczenie sprzedaży: %s", err)
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
