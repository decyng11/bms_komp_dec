"""Config flow for BMS komp-dec."""
from __future__ import annotations

import asyncio
import logging
import re

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    DOMAIN, DEFAULT_CONFIG,
    CONF_BATTERY_CAPACITY_KWH, CONF_MAX_CHARGE_POWER_W, CONF_MAX_DISCHARGE_POWER_W,
    CONF_TARGET_SOC_CHARGE, CONF_PRICE_BUY_ENTITY, CONF_PRICE_SELL_ENTITY,
    CONF_PV_FORECAST_TODAY, CONF_PV_FORECAST_TOMORROW, CONF_MIN_SELL_MARGIN,
    DEFAULT_BATTERY_CAPACITY_KWH, DEFAULT_MAX_CHARGE_POWER_W, DEFAULT_MAX_DISCHARGE_POWER_W,
    DEFAULT_TARGET_SOC_CHARGE, DEFAULT_PRICE_BUY_ENTITY, DEFAULT_PRICE_SELL_ENTITY,
    DEFAULT_PV_FORECAST_TODAY, DEFAULT_PV_FORECAST_TOMORROW, DEFAULT_MIN_SELL_MARGIN,
    CONF_SOC, CONF_PV_POWER, CONF_LOAD_POWER, CONF_BATTERY_POWER, CONF_GRID_POWER,
    CONF_ENERGY_PV_TODAY, CONF_ENERGY_LOAD_TODAY,
    CONF_ENERGY_GRID_EXPORT_TODAY, CONF_ENERGY_GRID_IMPORT_TODAY,
    CONF_ENERGY_BATT_CHARGE_TODAY, CONF_ENERGY_BATT_DISCHARGE_TODAY,
    CONF_PV1_VOLTAGE, CONF_PV1_CURRENT, CONF_PV2_VOLTAGE, CONF_PV2_CURRENT,
    CONF_GRID_VOLTAGE_L1, CONF_GRID_CURRENT_L1, CONF_LOAD_VOLTAGE_L1, CONF_LOAD_CURRENT_L1,
    CONF_GRID_VOLTAGE_L2, CONF_GRID_VOLTAGE_L3, CONF_GRID_CURRENT_L2, CONF_GRID_CURRENT_L3,
    CONF_LOAD_VOLTAGE_L2, CONF_LOAD_VOLTAGE_L3, CONF_LOAD_CURRENT_L2, CONF_LOAD_CURRENT_L3,
    CONF_GRID_POWER_L1, CONF_GRID_POWER_L2, CONF_GRID_POWER_L3,
    CONF_LOAD_POWER_L1, CONF_LOAD_POWER_L2, CONF_LOAD_POWER_L3,
    CONF_BATTERY_VOLTAGE, CONF_BATTERY_CURRENT, CONF_BATTERY_TEMPERATURE,
    CONF_WORK_MODE, CONF_CHARGE_CURRENT, CONF_EXPORT_SURPLUS, CONF_TOU,
    CONF_NOTIFY_SERVICE, CONF_TARIFF_PEAKS, CONF_TARIFF_WEEKEND_OFFPEAK, CONF_TARIFF_HOLIDAY_OFFPEAK, DEFAULT_TARIFF_PEAKS,
    CONF_TARIFF_MODE,
)
from .direct import is_inverter_entry
from .helpers import entry_settings
from .tariff import TARIFF_MODE_NEW, TARIFF_MODES, parse_peaks, tariff_mode_from_config
from .presets import (detect_inverter_brand, detect_entities, detect_solarman, collect_records, detect_price_entities,
                      detect_forecast_entities, detect_battery_capacity)

_LOGGER = logging.getLogger(__name__)

# Mapowanie klucza presetu (presets.py) -> klucz CONF_* w DEFAULT_CONFIG
_PRESET_TO_CONF: dict[str, str] = {
    "soc": CONF_SOC,
    "battery_power": CONF_BATTERY_POWER,
    "pv_power": CONF_PV_POWER,
    "load_power": CONF_LOAD_POWER,
    "grid_power": CONF_GRID_POWER,
    "pv_production_today": CONF_ENERGY_PV_TODAY,
    "battery_charge_today": CONF_ENERGY_BATT_CHARGE_TODAY,
    "battery_discharge_today": CONF_ENERGY_BATT_DISCHARGE_TODAY,
    "grid_export_today": CONF_ENERGY_GRID_EXPORT_TODAY,
    "grid_import_today": CONF_ENERGY_GRID_IMPORT_TODAY,
    "load_consumption_today": CONF_ENERGY_LOAD_TODAY,
    "work_mode": CONF_WORK_MODE,
    "charge_current": CONF_CHARGE_CURRENT,
    "export_surplus": CONF_EXPORT_SURPLUS,
    "tou_select": CONF_TOU,
    "battery_voltage": CONF_BATTERY_VOLTAGE,
    "battery_current": CONF_BATTERY_CURRENT,
    "battery_temperature": CONF_BATTERY_TEMPERATURE,
}
# role fazowe (L1–L3): nazwa roli w presets.py = klucz konfiguracji
_PRESET_TO_CONF.update({k: k for k in (
    "grid_voltage_l1", "grid_voltage_l2", "grid_voltage_l3", "grid_current_l1", "grid_current_l2", "grid_current_l3",
    "grid_power_l1", "grid_power_l2", "grid_power_l3", "load_voltage_l1", "load_voltage_l2", "load_voltage_l3",
    "load_current_l1", "load_current_l2", "load_current_l3", "load_power_l1", "load_power_l2", "load_power_l3")})

# Kluczowe encje (pokazywane w formularzu)
_CORE_KEYS = [
    CONF_SOC, CONF_PV_POWER, CONF_LOAD_POWER, CONF_BATTERY_POWER, CONF_GRID_POWER,
    CONF_ENERGY_PV_TODAY, CONF_ENERGY_LOAD_TODAY,
    CONF_ENERGY_GRID_IMPORT_TODAY, CONF_ENERGY_GRID_EXPORT_TODAY,
    CONF_ENERGY_BATT_CHARGE_TODAY, CONF_ENERGY_BATT_DISCHARGE_TODAY,
]

# Encje szczegółowe: PV stringi, fazy (L1/L2/L3), bateria, sterowanie
_DETAIL_KEYS = [
    CONF_PV1_VOLTAGE, CONF_PV1_CURRENT, CONF_PV2_VOLTAGE, CONF_PV2_CURRENT,
    CONF_GRID_VOLTAGE_L1, CONF_GRID_VOLTAGE_L2, CONF_GRID_VOLTAGE_L3,
    CONF_GRID_CURRENT_L1, CONF_GRID_CURRENT_L2, CONF_GRID_CURRENT_L3,
    CONF_GRID_POWER_L1, CONF_GRID_POWER_L2, CONF_GRID_POWER_L3,
    CONF_LOAD_VOLTAGE_L1, CONF_LOAD_VOLTAGE_L2, CONF_LOAD_VOLTAGE_L3,
    CONF_LOAD_CURRENT_L1, CONF_LOAD_CURRENT_L2, CONF_LOAD_CURRENT_L3,
    CONF_LOAD_POWER_L1, CONF_LOAD_POWER_L2, CONF_LOAD_POWER_L3,
    CONF_BATTERY_VOLTAGE, CONF_BATTERY_CURRENT, CONF_BATTERY_TEMPERATURE,
    CONF_WORK_MODE, CONF_CHARGE_CURRENT, CONF_EXPORT_SURPLUS, CONF_TOU,
]


_NUM_DEFAULTS = {
    CONF_BATTERY_CAPACITY_KWH: DEFAULT_BATTERY_CAPACITY_KWH,
    CONF_MAX_CHARGE_POWER_W: DEFAULT_MAX_CHARGE_POWER_W,
    CONF_MAX_DISCHARGE_POWER_W: DEFAULT_MAX_DISCHARGE_POWER_W,
    CONF_TARGET_SOC_CHARGE: DEFAULT_TARGET_SOC_CHARGE,
    CONF_MIN_SELL_MARGIN: DEFAULT_MIN_SELL_MARGIN,
}
_PRICE_FORECAST_DEFAULTS = {
    CONF_PRICE_BUY_ENTITY: DEFAULT_PRICE_BUY_ENTITY,
    CONF_PRICE_SELL_ENTITY: DEFAULT_PRICE_SELL_ENTITY,
    CONF_PV_FORECAST_TODAY: DEFAULT_PV_FORECAST_TODAY,
    CONF_PV_FORECAST_TOMORROW: DEFAULT_PV_FORECAST_TOMORROW,
}


def _num(min_, max_, step, unit, mode="box"):
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=min_, max=max_, step=step, unit_of_measurement=unit, mode=mode))


def build_schema(values: dict, redetect: bool = False) -> vol.Schema:
    """Wspólny formularz (instalacja i rekonfiguracja). values = wartości wstępne.

    Pusty default ("") nie przechodzi walidacji EntitySelector i blokował zapis,
    dlatego encje dostają suggested_value (można je wyczyścić)."""
    d: dict = {}
    for k in _CORE_KEYS + _DETAIL_KEYS + list(_PRICE_FORECAST_DEFAULTS):
        cur = values.get(k) or _PRICE_FORECAST_DEFAULTS.get(k)
        key = vol.Optional(k, description={"suggested_value": cur}) if cur else vol.Optional(k)
        d[key] = selector.EntitySelector()
    d[vol.Optional(CONF_BATTERY_CAPACITY_KWH, default=values.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))] = _num(1, 100, 0.01, "kWh")
    d[vol.Optional(CONF_MAX_CHARGE_POWER_W, default=values.get(CONF_MAX_CHARGE_POWER_W, DEFAULT_MAX_CHARGE_POWER_W))] = _num(100, 20000, 100, "W")
    d[vol.Optional(CONF_MAX_DISCHARGE_POWER_W, default=values.get(CONF_MAX_DISCHARGE_POWER_W, DEFAULT_MAX_DISCHARGE_POWER_W))] = _num(100, 20000, 100, "W")
    d[vol.Optional(CONF_TARGET_SOC_CHARGE, default=values.get(CONF_TARGET_SOC_CHARGE, DEFAULT_TARGET_SOC_CHARGE))] = _num(50, 100, 1, "%", "slider")
    d[vol.Optional(CONF_MIN_SELL_MARGIN, default=values.get(CONF_MIN_SELL_MARGIN, DEFAULT_MIN_SELL_MARGIN))] = _num(0, 2, 0.01, "PLN/kWh")
    d[vol.Optional(CONF_NOTIFY_SERVICE, description={"suggested_value": values.get(CONF_NOTIFY_SERVICE) or ""})] = selector.TextSelector()
    d[vol.Optional(CONF_TARIFF_PEAKS, default=values.get(CONF_TARIFF_PEAKS) or DEFAULT_TARIFF_PEAKS)] = selector.TextSelector()
    d[vol.Optional(CONF_TARIFF_WEEKEND_OFFPEAK, default=bool(values.get(CONF_TARIFF_WEEKEND_OFFPEAK, True)))] = selector.BooleanSelector()
    d[vol.Optional(CONF_TARIFF_HOLIDAY_OFFPEAK, default=bool(values.get(CONF_TARIFF_HOLIDAY_OFFPEAK, True)))] = selector.BooleanSelector()
    # tryb taryfy: wpis bez tego pola (sprzed 0.8.0) = „zone”, czyli bez zmiany zachowania
    d[vol.Optional(CONF_TARIFF_MODE, default=tariff_mode_from_config(values))] = selector.SelectSelector(
        selector.SelectSelectorConfig(options=list(TARIFF_MODES), mode="dropdown", translation_key="tariff_mode"))
    if redetect:
        d[vol.Optional("auto_detect", default=False)] = selector.BooleanSelector()
    return vol.Schema(d)


def validate_input(user_input: dict) -> dict[str, str]:
    """Błędy formularza (klucz pola → klucz tłumaczenia). Okna szczytu muszą być czytelne."""
    errors: dict[str, str] = {}
    peaks, err = parse_peaks(str(user_input.get(CONF_TARIFF_PEAKS) or ""))
    if peaks is None:
        _LOGGER.warning("BMS config flow: nieprawidłowe okna szczytu: %s", err)
        errors[CONF_TARIFF_PEAKS] = "invalid_peaks"
    svc = str(user_input.get(CONF_NOTIFY_SERVICE) or "").strip()
    if svc and not re.fullmatch(r"(notify\.)?[a-z0-9_]+", svc):
        errors[CONF_NOTIFY_SERVICE] = "invalid_notify"
    return errors


def clean(user_input: dict) -> dict:
    return {k: v for k, v in user_input.items() if v not in (None, "") and k != "auto_detect"}


def apply_detection(hass, user_input: dict) -> dict:
    """Gdy zaznaczono „Wykryj encje ponownie” — wykryte encje nadpisują wybrane."""
    data = clean(user_input)
    if not user_input.get("auto_detect"):
        return data
    try:
        found = detect_solarman(collect_records(hass))
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("BMS: wykrywanie ha-solarman nieudane: %s", err)
        found = None
    if found:
        for role, eid in found["entities"].items():
            conf_key = _PRESET_TO_CONF.get(role)
            if conf_key:
                data[conf_key] = eid
        _LOGGER.info("BMS: wykryto %s (%d encji)", found["label"], found["matched"])
    # ceny: gdy wskazana encja nie istnieje — pierwsza znana encja (RCE PSE, Pstryk…), osobno dla sprzedaży i zakupu
    try:
        for key, eid in detect_price_entities(hass).items():
            if hass.states.get(data.get(key) or "") is None:
                data[key] = eid
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("BMS: wykrywanie encji cen nieudane: %s", err)
    # prognozy PV: gdy wskazana encja nie istnieje — Solcast albo Forecast.Solar
    try:
        for key, eid in detect_forecast_entities(hass).items():
            if hass.states.get(data.get(key) or "") is None:
                data[key] = eid
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("BMS: wykrywanie prognoz PV nieudane: %s", err)
    return data


# ---------------------------------------------------------------- kreator „wszystko w jednym”
WIZARD_WAIT = 40.0            # ile sekund czekamy, aż nowo dodany falownik się załaduje
WIZARD_ENTITIES_WAIT = 12.0   # ile dodatkowo, aż jego encje pojawią się w rejestrze
WIZARD_POLL = 0.5
WIZARD_DATA_WAIT = 45.0       # ile sekund czekamy na pierwsze prawdziwe odczyty z falownika
WIZARD_DATA_RETRY = 20.0      # ile przy ponownej próbie z ekranu „falownik jeszcze nie odpowiada”
_WIZARD_MIN_CORE = 3          # tyle głównych ról musi być widocznych, zanim przejdziemy do dopasowania

_REQUIRED_CORE = (CONF_SOC, CONF_PV_POWER, CONF_LOAD_POWER, CONF_BATTERY_POWER, CONF_GRID_POWER)
# domena encji dla pól, które nie są czujnikami
_KEY_DOMAIN = {CONF_WORK_MODE: "select", CONF_TOU: "select", CONF_CHARGE_CURRENT: "number", CONF_EXPORT_SURPLUS: "number"}
# wartości, które kreator zapisuje obok wybranych encji (jak formularz „Planer BMS”)
_STATIC_DEFAULTS = {
    CONF_MAX_CHARGE_POWER_W: DEFAULT_MAX_CHARGE_POWER_W, CONF_MAX_DISCHARGE_POWER_W: DEFAULT_MAX_DISCHARGE_POWER_W,
    CONF_TARGET_SOC_CHARGE: DEFAULT_TARGET_SOC_CHARGE, CONF_MIN_SELL_MARGIN: DEFAULT_MIN_SELL_MARGIN,
    CONF_TARIFF_PEAKS: DEFAULT_TARIFF_PEAKS, CONF_TARIFF_WEEKEND_OFFPEAK: True, CONF_TARIFF_HOLIDAY_OFFPEAK: True,
}


def _unit_family(key: str) -> tuple[str, ...] | None:
    """Dozwolone jednostki czujnika dla pola konfiguracji (None = nie sprawdzamy)."""
    if _KEY_DOMAIN.get(key, "sensor") != "sensor":
        return None
    if key == CONF_SOC:
        return ("%",)
    if key.endswith("_voltage") or "_voltage_l" in key:
        return ("V",)
    if key.endswith("_current") or "_current_l" in key:
        return ("A",)
    if key.endswith("_power") or "_power_l" in key:
        return ("W", "kW")
    if key.startswith("energy_"):
        return ("kWh", "Wh", "MWh")
    if key.endswith("_temperature"):
        return ("°C", "°F")
    return None


def validate_roles(hass, data: dict) -> tuple[list[str], list[str], list[str]]:
    """(brakujące główne role, nieistniejące encje, encje złego typu) dla wybranych encji falownika."""
    core_empty: list[str] = []
    missing: list[str] = []
    wrong: list[str] = []
    for key in _CORE_KEYS + _DETAIL_KEYS:
        eid = data.get(key)
        if not eid:
            if key in _REQUIRED_CORE:
                core_empty.append(key)
            continue
        st = hass.states.get(eid)
        if st is None:
            missing.append(f"{key}: {eid}")
            continue
        want = _KEY_DOMAIN.get(key, "sensor")
        if str(eid).split(".", 1)[0] != want:
            wrong.append(f"{key}: {eid} (oczekiwano {want}.*)")
            continue
        fam = _unit_family(key)
        unit = (getattr(st, "attributes", None) or {}).get("unit_of_measurement")
        if fam and unit and unit not in fam:
            wrong.append(f"{key}: {eid} ({unit}, oczekiwano {'/'.join(fam)})")
    return core_empty, missing, wrong


def prune_missing(hass, defaults: dict) -> dict:
    """Usuwa z podpowiedzi encje, których nie ma w HA (zamiast „Wybrano nieznaną encję” w formularzu)."""
    out = dict(defaults)
    for key in _CORE_KEYS + _DETAIL_KEYS + [CONF_PRICE_SELL_ENTITY, CONF_PRICE_BUY_ENTITY, CONF_PV_FORECAST_TODAY, CONF_PV_FORECAST_TOMORROW]:
        eid = out.get(key)
        if eid and hass.states.get(eid) is None:
            out.pop(key, None)
    return out


def _entity_selector(key: str):
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=_KEY_DOMAIN.get(key, "sensor")))


def build_match_schema(values: dict) -> vol.Schema:
    """Krok „dopasowanie encji”: główne encje i najważniejsze ustawienia na wierzchu, reszta (fazy, PV, bateria) w sekcji."""
    def ent(k):
        cur = values.get(k)
        return vol.Optional(k, description={"suggested_value": cur}) if cur else vol.Optional(k)
    d: dict = {}
    for k in _REQUIRED_CORE:
        d[ent(k)] = _entity_selector(k)
    d[vol.Optional(CONF_BATTERY_CAPACITY_KWH, default=values.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))] = _num(1, 100, 0.01, "kWh")
    d[vol.Optional(CONF_TARIFF_MODE, default=tariff_mode_from_config(values))] = selector.SelectSelector(
        selector.SelectSelectorConfig(options=list(TARIFF_MODES), mode="dropdown", translation_key="tariff_mode"))
    for k in (CONF_PRICE_SELL_ENTITY, CONF_PRICE_BUY_ENTITY, CONF_PV_FORECAST_TODAY, CONF_PV_FORECAST_TOMORROW):
        d[ent(k)] = _entity_selector(k)
    details = {ent(k): _entity_selector(k) for k in [c for c in _CORE_KEYS if c not in _REQUIRED_CORE] + _DETAIL_KEYS}   # liczniki dzienne + fazy, PV, bateria, sterowanie
    d[vol.Required("details")] = section(vol.Schema(details), {"collapsed": True})
    return vol.Schema(d)


def flatten_match(user_input: dict) -> dict:
    """Wynik formularza z sekcją → płaski słownik ustawień."""
    flat = {k: v for k, v in user_input.items() if k != "details"}
    flat.update(user_input.get("details") or {})
    return flat


class BmsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._detected_brand: str = "custom"

    @staticmethod
    def async_get_options_flow(config_entry):
        if is_inverter_entry(config_entry):
            return InverterOptionsFlow(config_entry)
        return BmsOptionsFlow(config_entry)

    def _has_bms_entry(self) -> bool:
        return any(not is_inverter_entry(e) for e in self._async_current_entries())

    async def async_step_user(self, user_input=None):
        """Menu: BMS (planer; tylko jeden) albo falownik połączony bezpośrednio (może być kilka)."""
        if self._has_bms_entry():
            return await self.async_step_inverter()
        return self.async_show_menu(step_id="user", menu_options=["wizard", "bms", "inverter"])

    async def async_step_inverter(self, user_input=None):
        """Falownik dodawany bezpośrednio (bez integracji ha-solarman): host, port, transport, profil."""
        return await self._inverter_form("inverter", user_input)

    async def async_step_wizard_inverter(self, user_input=None):
        """Kreator, krok 2: ten sam formularz falownika, ale po zatwierdzeniu czeka na encje i przechodzi do dopasowania."""
        return await self._inverter_form("wizard_inverter", user_input, wizard=True)

    async def _inverter_form(self, step_id: str, user_input, wizard: bool = False, extra_errors: dict | None = None):
        from .direct.discovery import discover
        from .direct.flow import (
            CONF_NAME, configuration_schema, creation_schema, data_schema, remove_defaults, validate_connection,
        )
        from .direct.const import (
            CONF_ALLOW_WRITE, CONF_HOST, CONF_KIND, CONF_ADDITIONAL_OPTIONS, CONF_LOOKUP_FILE, CONF_PORT,
            CONF_TRANSPORT, DEFAULT_, KIND_INVERTER,
        )

        inverters = [e for e in self._async_current_entries() if is_inverter_entry(e)]
        taken_names = {e.title for e in inverters}
        taken_hosts = {str((e.options or {}).get(CONF_HOST, "")) for e in inverters}

        if user_input is None:
            name = DEFAULT_[CONF_NAME]
            i = 1
            while name in taken_names:
                i += 1
                name = f"{DEFAULT_[CONF_NAME]} {i}"
            ip = None
            try:
                async for found in await discover(self.hass):
                    if found["ip"] not in taken_hosts:
                        ip = found["ip"]
                        break
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("BMS: wyszukiwanie loggera Solarman nieudane: %s", err)
            schema = await data_schema(self.hass, creation_schema() | configuration_schema())
            return self.async_show_form(
                step_id=step_id,
                data_schema=self.add_suggested_values_to_schema(schema, {CONF_NAME: name, CONF_HOST: ip}),
            )

        if extra_errors:                       # ponowne pokazanie formularza po porażce kreatora (dane już sprawdzone)
            errors = extra_errors
        else:
            errors = await self.hass.async_add_executor_job(validate_connection, user_input)   # DNS poza pętlą zdarzeń
            if not errors and str(user_input.get(CONF_HOST, "")) in taken_hosts:
                errors = {"base": "already_configured_device"}
            if not errors and user_input.get(CONF_NAME) in taken_names:
                errors = {"base": "name_in_use"}
        if errors:
            schema = await data_schema(self.hass, creation_schema() | configuration_schema())
            return self.async_show_form(
                step_id=step_id,
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors=errors,
            )
        keys = (CONF_HOST, CONF_PORT, CONF_TRANSPORT, CONF_LOOKUP_FILE, CONF_ALLOW_WRITE, CONF_ADDITIONAL_OPTIONS)
        options = remove_defaults({k: v for k, v in user_input.items() if k in keys})
        if wizard:
            return await self._wizard_add_inverter(user_input, user_input[CONF_NAME], options)
        return self.async_create_entry(title=user_input[CONF_NAME], data={CONF_KIND: KIND_INVERTER}, options=options)

    async def async_step_import(self, import_data):
        """Tworzy wpis falownika na polecenie kreatora (nazwa i opcje już sprawdzone w formularzu)."""
        from .direct.const import CONF_HOST, CONF_KIND, KIND_INVERTER
        name = str((import_data or {}).get("name") or "Inverter")
        options = dict((import_data or {}).get("options") or {})
        inverters = [e for e in self._async_current_entries() if is_inverter_entry(e)]
        if str(options.get(CONF_HOST, "")) in {str((e.options or {}).get(CONF_HOST, "")) for e in inverters}:
            return self.async_abort(reason="already_configured_device")
        if name in {e.title for e in inverters}:
            return self.async_abort(reason="name_in_use")
        return self.async_create_entry(title=name, data={CONF_KIND: KIND_INVERTER}, options=options)

    # ----------------------------------------------------------- kreator „wszystko w jednym”
    async def async_step_wizard(self, user_input=None):
        """Krok 1: skąd są encje falownika — połączenie bezpośrednie (kreator doda falownik) albo istniejące ha-solarman."""
        if self._has_bms_entry():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            if user_input.get("connection") == "solarman":
                return await self.async_step_wizard_match()
            return await self.async_step_wizard_inverter()
        return self.async_show_form(step_id="wizard", data_schema=vol.Schema({
            vol.Required("connection", default="direct"): selector.SelectSelector(selector.SelectSelectorConfig(
                options=["direct", "solarman"], mode="list", translation_key="wizard_connection")),
        }))

    async def _wizard_add_inverter(self, user_input: dict, name: str, options: dict):
        """Dodaje wpis falownika, czeka aż się załaduje i jego encje będą widoczne; przy porażce sprząta po sobie."""
        result = await self.hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data={"name": name, "options": options})
        if result.get("type") != "create_entry" or result.get("result") is None:
            reason = str(result.get("reason") or "unknown")
            return await self._inverter_form("wizard_inverter", user_input, wizard=True,
                                             extra_errors={"base": reason if reason in ("already_configured_device", "name_in_use") else "unknown"})
        entry = result["result"]
        if not await self._wizard_wait(entry.entry_id):
            try:
                await self.hass.config_entries.async_remove(entry.entry_id)    # bez porzuconego, niedziałającego wpisu
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("BMS kreator: nie udało się usunąć nieudanego wpisu falownika: %s", err)
            return await self._inverter_form("wizard_inverter", user_input, wizard=True, extra_errors={"base": "setup_failed"})
        if not await self._wizard_data_ready(WIZARD_DATA_WAIT):
            return await self.async_step_wizard_wait()
        return await self.async_step_wizard_match()

    def _wizard_core_ready(self) -> int:
        """Ile głównych ról (SOC, PV, dom, bateria, sieć) ma już liczbowy stan (nie unavailable/unknown)."""
        found = self._detect_solarman()
        if not found:
            return 0
        n = 0
        for role, eid in found["entities"].items():
            if _PRESET_TO_CONF.get(role) in _REQUIRED_CORE:
                st = self.hass.states.get(eid)
                try:
                    if st is not None and st.state not in ("unavailable", "unknown", "", None):
                        float(str(st.state).replace(",", "."))
                        n += 1
                except ValueError:
                    pass
        return n

    async def _wizard_data_ready(self, wait: float) -> bool:
        """True, gdy falownik odpowiada: co najmniej _WIZARD_MIN_CORE głównych encji ma prawdziwą wartość."""
        loop = asyncio.get_running_loop()
        end = loop.time() + wait
        while True:
            if self._wizard_core_ready() >= _WIZARD_MIN_CORE:
                return True
            if loop.time() > end:
                return False
            await asyncio.sleep(WIZARD_POLL)

    async def async_step_wizard_wait(self, user_input=None):
        """Falownik jest dodany, ale jeszcze nie odpowiada: „Zatwierdź” sprawdza ponownie, bez dodawania drugiego wpisu."""
        if self._has_bms_entry():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None and await self._wizard_data_ready(WIZARD_DATA_RETRY):
            return await self.async_step_wizard_match()
        return self.async_show_form(step_id="wizard_wait", data_schema=vol.Schema({}),
                                    errors={"base": "no_data"} if user_input is not None else {})

    async def _wizard_wait(self, entry_id: str) -> bool:
        """True, gdy wpis jest załadowany, a jego encje widać w rejestrze (przynajmniej główne role)."""
        loop = asyncio.get_running_loop()
        end = loop.time() + WIZARD_WAIT
        while True:
            entry = self.hass.config_entries.async_get_entry(entry_id)
            state = getattr(getattr(entry, "state", None), "value", getattr(entry, "state", None))
            if state == "loaded":
                break
            if entry is None or state in ("setup_error", "failed_unload", "migration_error") or loop.time() > end:
                return False
            await asyncio.sleep(WIZARD_POLL)
        end = loop.time() + WIZARD_ENTITIES_WAIT
        while loop.time() < end:
            found = self._detect_solarman()
            if found and sum(1 for c in _REQUIRED_CORE if c in {_PRESET_TO_CONF.get(r) for r in found["entities"]}) >= _WIZARD_MIN_CORE:
                break
            await asyncio.sleep(WIZARD_POLL)
        return True

    async def async_step_wizard_match(self, user_input=None):
        """Krok 3: dopasowanie encji. Podpowiedzi wyłącznie z istniejących encji; zatwierdzenie tylko po sprawdzeniu typów."""
        if self._has_bms_entry():
            return self.async_abort(reason="single_instance_allowed")
        defaults = prune_missing(self.hass, self._build_defaults())
        errors: dict[str, str] = {}
        problems = ""
        cap = detect_battery_capacity(self.hass)
        cap_note = ""
        if cap:
            defaults[CONF_BATTERY_CAPACITY_KWH] = cap[0]
            cap_note = (f" Pojemność baterii: {cap[0]:g} kWh (z falownika)." if cap[1] == "kwh"
                        else f" Pojemność baterii: ok. {cap[0]:g} kWh (przybliżenie: Ah × napięcie baterii — sprawdź).")
        if user_input is not None:
            flat = flatten_match(user_input)
            core_empty, missing, wrong = validate_roles(self.hass, flat)
            if core_empty:
                errors["base"], problems = "core_missing", ", ".join(core_empty)
            elif missing:
                errors["base"], problems = "entities_missing", "; ".join(missing)
            elif wrong:
                errors["base"], problems = "wrong_type", "; ".join(wrong)
            elif (e := validate_input(flat)):
                errors = e
            if not errors:
                return self.async_create_entry(title="BMS komp-dec", data=clean({**_STATIC_DEFAULTS, **flat}))
            defaults = {**defaults, **flat}
        found = self._detect_solarman()
        if found:
            summary = f"{found['label']}, fazy: {found.get('phases') or 1}, dopasowano encji: {found['matched'] + len([k for k in found['entities'] if k.endswith(('_l1', '_l2', '_l3'))])}"
        else:
            summary = "nie znaleziono encji falownika — wybierz je ręcznie"
        summary += cap_note
        return self.async_show_form(
            step_id="wizard_match",
            errors=errors,
            data_schema=build_match_schema(defaults),
            description_placeholders={"summary": summary, "problems": problems or "—"},
        )

    async def async_step_bms(self, user_input=None):
        # Integracja BMS działa jako jedna instancja (stałe unique_id encji, usługi globalne).
        if self._has_bms_entry():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        defaults = self._build_defaults()
        if user_input is not None:
            errors = validate_input(user_input)
            if not errors:
                return self.async_create_entry(title="BMS komp-dec", data=clean(user_input))
            defaults = {**defaults, **user_input}

        return self.async_show_form(
            step_id="bms",
            errors=errors,
            data_schema=build_schema(defaults),
            description_placeholders={
                "brand": self._detected_brand,
                "hint": (
                    f"Auto-wykryto inwerter: {self._detected_brand}. "
                    f"Encje zostały wstępnie wypełnione — sprawdź i popraw jeśli trzeba."
                ),
            },
        )

    async def async_step_reconfigure(self, user_input=None):
        """Rekonfiguracja bez usuwania integracji (Ustawienia → Urządzenia i usługi → ⋮ → Zmień konfigurację)."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")
        errors: dict[str, str] = {}
        values = {**DEFAULT_CONFIG, **entry_settings(entry)}
        if user_input is not None:
            errors = validate_input(user_input)
            if not errors:
                # listener w __init__ przeładuje wpis po zapisie
                self.hass.config_entries.async_update_entry(entry, data=apply_detection(self.hass, user_input), options={})
                return self.async_abort(reason="reconfigure_successful")
            values = {**values, **user_input}
        return self.async_show_form(
            step_id="reconfigure",
            errors=errors,
            data_schema=build_schema(values, redetect=True),
        )

    def _detect_solarman(self) -> dict | None:
        try:
            return detect_solarman(collect_records(self.hass))
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("BMS config flow: wykrywanie ha-solarman nieudane: %s", err)
            return None

    def _build_defaults(self) -> dict[str, str]:
        """DEFAULT_CONFIG + auto-detekcja (detected ma priorytet)."""
        defaults: dict[str, str] = dict(DEFAULT_CONFIG)
        defaults[CONF_TARIFF_MODE] = TARIFF_MODE_NEW        # nowa instalacja: ceny godzinowe, gdy encja zakupu je podaje
        # ceny: domyślne encje, a gdy ich nie ma — pierwsza znana encja (RCE PSE, Pstryk…), osobno dla sprzedaży i zakupu
        for key, eid in detect_price_entities(self.hass).items():
            if self.hass.states.get(defaults.get(key) or "") is None:
                defaults[key] = eid
        for key, eid in detect_forecast_entities(self.hass).items():
            if self.hass.states.get(defaults.get(key) or "") is None:
                defaults[key] = eid
        found = self._detect_solarman()
        if found:
            for role, eid in found["entities"].items():
                conf_key = _PRESET_TO_CONF.get(role)
                if conf_key:
                    defaults[conf_key] = eid
            self._detected_brand = found["label"]
            return defaults
        try:
            all_entity_ids = self.hass.states.async_entity_ids()
            self._detected_brand = detect_inverter_brand(all_entity_ids)
            if self._detected_brand != "custom":
                detected = detect_entities(all_entity_ids, self._detected_brand)
                for preset_key, eid in detected.items():
                    conf_key = _PRESET_TO_CONF.get(preset_key)
                    if conf_key:
                        defaults[conf_key] = eid
                _LOGGER.info(
                    "BMS config flow: wykryto %s, dopasowano %d/%d encji",
                    self._detected_brand, len(detected), len(_PRESET_TO_CONF),
                )
            else:
                _LOGGER.info("BMS config flow: brak znanej marki, używam DEFAULT_CONFIG")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("BMS config flow: auto-detekcja nieudana: %s", err)
            self._detected_brand = "custom"
        return defaults


class BmsOptionsFlow(config_entries.OptionsFlow):
    """Przycisk „Konfiguruj” przy integracji — zmiana encji i parametrów bez usuwania wpisu."""

    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}
        values = {**DEFAULT_CONFIG, **entry_settings(self._entry)}
        if user_input is not None:
            errors = validate_input(user_input)
            if not errors:
                # options zastępują data w całości (wyczyszczone pole = wartość domyślna)
                return self.async_create_entry(title="", data=apply_detection(self.hass, user_input))
            values = {**values, **user_input}
        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=build_schema(values, redetect=True),
        )


class InverterOptionsFlow(config_entries.OptionsFlow):
    """„Konfiguruj” przy falowniku dodanym bezpośrednio: adres, port, transport, profil, Modbus ID, zapis."""

    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        # osobny step_id, żeby tłumaczenia nie myliły się z opcjami planera BMS (też „init”)
        return await self.async_step_inverter(user_input)

    async def async_step_inverter(self, user_input=None):
        from .direct.flow import configuration_schema, data_schema, remove_defaults, validate_connection

        if user_input is None:
            schema = await data_schema(self.hass, configuration_schema())
            return self.async_show_form(
                step_id="inverter",
                data_schema=self.add_suggested_values_to_schema(schema, self._entry.options),
            )
        errors = await self.hass.async_add_executor_job(validate_connection, user_input)   # DNS poza pętlą zdarzeń
        if errors:
            schema = await data_schema(self.hass, configuration_schema())
            return self.async_show_form(
                step_id="inverter",
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors=errors,
            )
        return self.async_create_entry(title="", data=remove_defaults(dict(user_input)))
