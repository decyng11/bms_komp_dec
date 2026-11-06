"""Constants for BMS komp-dec integration."""
DOMAIN = "bms_komp_dec"
VERSION = "0.8.4"

# Mapowanie encji źródłowych
CONF_PV_POWER = "pv_power"
CONF_LOAD_POWER = "load_power"
CONF_BATTERY_POWER = "battery_power"
CONF_GRID_POWER = "grid_power"
CONF_SOC = "soc"
CONF_ENERGY_PV_TODAY = "energy_pv_today"
CONF_ENERGY_LOAD_TODAY = "energy_load_today"
CONF_ENERGY_GRID_EXPORT_TODAY = "energy_grid_export_today"
CONF_ENERGY_GRID_IMPORT_TODAY = "energy_grid_import_today"
CONF_ENERGY_BATT_CHARGE_TODAY = "energy_batt_charge_today"
CONF_ENERGY_BATT_DISCHARGE_TODAY = "energy_batt_discharge_today"

CONF_PV1_VOLTAGE = "pv1_voltage"
CONF_PV1_CURRENT = "pv1_current"
CONF_PV2_VOLTAGE = "pv2_voltage"
CONF_PV2_CURRENT = "pv2_current"
CONF_GRID_VOLTAGE_L1 = "grid_voltage_l1"
CONF_GRID_VOLTAGE_L2 = "grid_voltage_l2"
CONF_GRID_VOLTAGE_L3 = "grid_voltage_l3"
CONF_GRID_CURRENT_L1 = "grid_current_l1"
CONF_GRID_CURRENT_L2 = "grid_current_l2"
CONF_GRID_CURRENT_L3 = "grid_current_l3"
CONF_GRID_POWER_L1 = "grid_power_l1"
CONF_GRID_POWER_L2 = "grid_power_l2"
CONF_GRID_POWER_L3 = "grid_power_l3"
CONF_LOAD_VOLTAGE_L1 = "load_voltage_l1"
CONF_LOAD_VOLTAGE_L2 = "load_voltage_l2"
CONF_LOAD_VOLTAGE_L3 = "load_voltage_l3"
CONF_LOAD_CURRENT_L1 = "load_current_l1"
CONF_LOAD_CURRENT_L2 = "load_current_l2"
CONF_LOAD_CURRENT_L3 = "load_current_l3"
CONF_LOAD_POWER_L1 = "load_power_l1"
CONF_LOAD_POWER_L2 = "load_power_l2"
CONF_LOAD_POWER_L3 = "load_power_l3"
CONF_BATTERY_VOLTAGE = "battery_voltage"
CONF_BATTERY_CURRENT = "battery_current"
CONF_BATTERY_TEMPERATURE = "battery_temperature"

CONF_WORK_MODE = "work_mode"
CONF_CHARGE_CURRENT = "charge_current"
CONF_EXPORT_SURPLUS = "export_surplus"      # number: moc eksportu/nadwyżki (Deye „Export Surplus Power”)
CONF_TOU = "tou_select"                     # select: Time of Use (włącza/wyłącza programy czasowe)

# Taryfa strefowa (domyślnie G12w): okna szczytu i traktowanie weekendów/świąt
CONF_NOTIFY_SERVICE = "notify_service"        # np. notify.mobile_app_telefon (opcjonalnie; zawsze też powiadomienie w HA)
CONF_TARIFF_PEAKS = "tariff_peaks"
CONF_TARIFF_WEEKEND_OFFPEAK = "tariff_weekend_offpeak"
CONF_TARIFF_HOLIDAY_OFFPEAK = "tariff_holiday_offpeak"
CONF_TARIFF_MODE = "tariff_mode"          # auto / zone / dynamic (patrz tariff.TARIFF_MODES)
DEFAULT_TARIFF_PEAKS = "6-13,15-22"

CONF_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
CONF_MAX_CHARGE_POWER_W = "max_charge_power_w"
CONF_MAX_DISCHARGE_POWER_W = "max_discharge_power_w"
CONF_TARGET_SOC_CHARGE = "target_soc_grid_charge"
CONF_PRICE_BUY_ENTITY = "price_buy_entity"
CONF_PRICE_SELL_ENTITY = "price_sell_entity"
CONF_PV_FORECAST_TODAY = "pv_forecast_today"
CONF_PV_FORECAST_TOMORROW = "pv_forecast_tomorrow"
CONF_MIN_SELL_MARGIN = "min_sell_margin"

DEFAULT_BATTERY_CAPACITY_KWH = 10.0
DEFAULT_MAX_CHARGE_POWER_W = 5000
DEFAULT_MAX_DISCHARGE_POWER_W = 5000
DEFAULT_TARGET_SOC_CHARGE = 90
DEFAULT_PRICE_BUY_ENTITY = "sensor.energy_hub_aktualna_cena_g12w"
DEFAULT_PRICE_SELL_ENTITY = "sensor.rce_pse_cena"
DEFAULT_PV_FORECAST_TODAY = "sensor.solcast_pv_forecast_forecast_today"
DEFAULT_PV_FORECAST_TOMORROW = "sensor.solcast_pv_forecast_forecast_tomorrow"
DEFAULT_MIN_SELL_MARGIN = 0.15

SCHEDULER_DEFAULTS = {
    CONF_BATTERY_CAPACITY_KWH: DEFAULT_BATTERY_CAPACITY_KWH,
    CONF_MAX_CHARGE_POWER_W: DEFAULT_MAX_CHARGE_POWER_W,
    CONF_MAX_DISCHARGE_POWER_W: DEFAULT_MAX_DISCHARGE_POWER_W,
    CONF_TARGET_SOC_CHARGE: DEFAULT_TARGET_SOC_CHARGE,
    CONF_PRICE_BUY_ENTITY: DEFAULT_PRICE_BUY_ENTITY,
    CONF_PRICE_SELL_ENTITY: DEFAULT_PRICE_SELL_ENTITY,
    CONF_PV_FORECAST_TODAY: DEFAULT_PV_FORECAST_TODAY,
    CONF_PV_FORECAST_TOMORROW: DEFAULT_PV_FORECAST_TOMORROW,
    CONF_MIN_SELL_MARGIN: DEFAULT_MIN_SELL_MARGIN,
    CONF_TARIFF_PEAKS: DEFAULT_TARIFF_PEAKS,
    CONF_TARIFF_WEEKEND_OFFPEAK: True,
    CONF_TARIFF_HOLIDAY_OFFPEAK: True,
}

DEFAULT_CONFIG = {
    CONF_PV_POWER: "sensor.inverter_pv_power",
    CONF_LOAD_POWER: "sensor.inverter_load_power",
    CONF_BATTERY_POWER: "sensor.inverter_battery_power",
    CONF_GRID_POWER: "sensor.inverter_grid_power",
    CONF_SOC: "sensor.inverter_battery",
    CONF_ENERGY_PV_TODAY: "sensor.inverter_today_production",
    CONF_ENERGY_LOAD_TODAY: "sensor.inverter_today_load_consumption",
    CONF_ENERGY_GRID_EXPORT_TODAY: "sensor.inverter_today_energy_export",
    CONF_ENERGY_GRID_IMPORT_TODAY: "sensor.inverter_today_energy_import",
    CONF_ENERGY_BATT_CHARGE_TODAY: "sensor.inverter_today_battery_charge",
    CONF_ENERGY_BATT_DISCHARGE_TODAY: "sensor.inverter_today_battery_discharge",
    CONF_PV1_VOLTAGE: "sensor.inverter_pv1_voltage",
    CONF_PV1_CURRENT: "sensor.inverter_pv1_current",
    CONF_PV2_VOLTAGE: "sensor.inverter_pv2_voltage",
    CONF_PV2_CURRENT: "sensor.inverter_pv2_current",
    CONF_GRID_VOLTAGE_L1: "sensor.inverter_grid_l1_voltage",
    CONF_GRID_CURRENT_L1: "sensor.inverter_grid_l1_current",
    CONF_GRID_CURRENT_L2: "sensor.inverter_grid_l2_current",
    CONF_GRID_CURRENT_L3: "sensor.inverter_grid_l3_current",
    CONF_LOAD_VOLTAGE_L1: "sensor.inverter_load_l1_voltage",
    CONF_LOAD_VOLTAGE_L2: "sensor.inverter_load_l2_voltage",
    CONF_LOAD_VOLTAGE_L3: "sensor.inverter_load_l3_voltage",
    CONF_LOAD_CURRENT_L1: "sensor.inverter_load_l1_current",
    CONF_LOAD_CURRENT_L2: "sensor.inverter_load_l2_current",
    CONF_LOAD_CURRENT_L3: "sensor.inverter_load_l3_current",
    CONF_GRID_VOLTAGE_L2: "sensor.inverter_grid_l2_voltage",
    CONF_GRID_VOLTAGE_L3: "sensor.inverter_grid_l3_voltage",
    CONF_GRID_POWER_L1: "sensor.inverter_grid_l1_power",
    CONF_GRID_POWER_L2: "sensor.inverter_grid_l2_power",
    CONF_GRID_POWER_L3: "sensor.inverter_grid_l3_power",
    CONF_LOAD_POWER_L1: "sensor.inverter_load_l1_power",
    CONF_LOAD_POWER_L2: "sensor.inverter_load_l2_power",
    CONF_LOAD_POWER_L3: "sensor.inverter_load_l3_power",
    CONF_BATTERY_VOLTAGE: "sensor.inverter_battery_voltage",
    CONF_BATTERY_CURRENT: "sensor.inverter_battery_current",
    CONF_BATTERY_TEMPERATURE: "sensor.inverter_battery_temperature",
    CONF_WORK_MODE: "select.inverter_work_mode",
    CONF_CHARGE_CURRENT: "number.inverter_battery_max_charging_current",
    CONF_EXPORT_SURPLUS: "number.inverter_export_surplus_power",
    CONF_TOU: "select.inverter_time_of_use",
}

SENSORS = [
    ("soc", "BMS SOC", "%", "mdi:battery", CONF_SOC),
    ("pv_power", "BMS PV Power", "W", "mdi:solar-power", CONF_PV_POWER),
    ("load_power", "BMS Load Power", "W", "mdi:home", CONF_LOAD_POWER),
    ("battery_power", "BMS Battery Power", "W", "mdi:battery", CONF_BATTERY_POWER),
    ("grid_power", "BMS Grid Power", "W", "mdi:transmission-tower", CONF_GRID_POWER),
    ("energy_pv_today", "BMS Energy PV Today", "kWh", "mdi:solar-power", CONF_ENERGY_PV_TODAY),
    ("energy_load_today", "BMS Energy Load Today", "kWh", "mdi:home", CONF_ENERGY_LOAD_TODAY),
    ("energy_grid_export_today", "BMS Energy Grid Export Today", "kWh", "mdi:transmission-tower-export", CONF_ENERGY_GRID_EXPORT_TODAY),
    ("energy_grid_import_today", "BMS Energy Grid Import Today", "kWh", "mdi:transmission-tower-import", CONF_ENERGY_GRID_IMPORT_TODAY),
    ("energy_battery_charge_today", "BMS Energy Batt Charge Today", "kWh", "mdi:battery-plus", CONF_ENERGY_BATT_CHARGE_TODAY),
    ("energy_battery_discharge_today", "BMS Energy Batt Discharge Today", "kWh", "mdi:battery-minus", CONF_ENERGY_BATT_DISCHARGE_TODAY),
]

BINARY_SENSORS = [
    ("sprzedaz_aktywna", "BMS Sprzedaż aktywna", "mdi:cash-fast"),
    ("blokada_pv_aktywna", "BMS Blokada ładowania PV", "mdi:battery-off"),
    ("peak_shaving_active", "BMS Peak shaving", "mdi:chart-bell-curve"),
    ("grid_import_legal_blocked", "BMS Limit importu z sieci przekroczony", "mdi:transmission-tower-import"),
    ("self_consumption_ok", "BMS Autokonsumpcja OK", "mdi:home-battery"),
    ("sprzedaz_zablokowana_importem", "BMS Sprzedaż zablokowana importem z sieci", "mdi:transmission-tower-import"),
    ("sprzedaz_zablokowana_arbitraz", "BMS Sprzedaż zablokowana arbitrażem (2 dni)", "mdi:battery-alert"),
    ("ujemna_cena_aktywna", "BMS Niska/ujemna cena RCE", "mdi:cash-remove"),
    ("sprzedaz_nieoplacalna", "BMS Sprzedaż nieopłacalna", "mdi:calculator-variant"),
    ("dzien_swiateczny", "BMS Dzień świąteczny", "mdi:calendar-star"),
]

# (key, nazwa, ikona, domyślny stan gdy brak zapamiętanego)
SWITCHES = [
    ("bateria_sprzedaz_1", "Sprzedaż z baterii (zestaw 1)", "mdi:battery-arrow-down", False),
    ("bateria_sprzedaz_2", "Sprzedaż z baterii (zestaw 2)", "mdi:battery-arrow-down", False),
    ("ladowanie_z_sieci_1", "Ładowanie z sieci (zestaw 1)", "mdi:power-plug", False),
    ("ladowanie_z_sieci_2", "Ładowanie z sieci (zestaw 2)", "mdi:power-plug", False),
    ("force_charge_battery", "Wymuś ładowanie z sieci", "mdi:flash", False),
    # --- harmonogram: dni tygodnia + święta (funkcja 7)
    ("recurring_schedule", "Harmonogram cykliczny (codziennie)", "mdi:calendar-sync", False),
    ("holidays_as_sunday", "Święta traktuj jak niedzielę", "mdi:calendar-star", True),
    ("dzien_pn", "Harmonogram aktywny: poniedziałek", "mdi:calendar-today", True),
    ("dzien_wt", "Harmonogram aktywny: wtorek", "mdi:calendar-today", True),
    ("dzien_sr", "Harmonogram aktywny: środa", "mdi:calendar-today", True),
    ("dzien_cz", "Harmonogram aktywny: czwartek", "mdi:calendar-today", True),
    ("dzien_pt", "Harmonogram aktywny: piątek", "mdi:calendar-today", True),
    ("dzien_so", "Harmonogram aktywny: sobota", "mdi:calendar-today", True),
    ("dzien_nd", "Harmonogram aktywny: niedziela", "mdi:calendar-today", True),
    # --- funkcje automatyczne (domyślnie wyłączone)
    ("negative_price_reaction", "Reakcja na niskie/ujemne ceny RCE", "mdi:cash-remove", False),
    ("profit_check", "Sprawdzaj opłacalność sprzedaży", "mdi:calculator-variant", False),
    ("dynamic_reserve", "Dynamiczna rezerwa SOC", "mdi:battery-heart-variant", False),
    ("auto_apply", "Automatyczne stosowanie propozycji", "mdi:robot", False),
    ("readback_verify", "Weryfikuj wykonanie komend (odczyt zwrotny)", "mdi:check-network", True),
    # --- powiadomienia, tryby specjalne, test na sucho
    ("notifications_enabled", "Powiadomienia BMS", "mdi:bell-ring", True),
    ("storm_mode", "Tryb burzowy (rezerwa 100%, bez sprzedaży)", "mdi:weather-lightning", False),
    ("vacation_mode", "Tryb urlopowy (minimalne zużycie)", "mdi:palm-tree", False),
    ("auto_apply_dry_run", "Auto-stosowanie: tylko podgląd (bez zapisu)", "mdi:eye-check", False),
]

WEEKDAY_SWITCH_KEYS = ["dzien_pn", "dzien_wt", "dzien_sr", "dzien_cz", "dzien_pt", "dzien_so", "dzien_nd"]

BUTTONS = [
    ("sprzedaz_6000w", "Sprzedaż 6000W", "mdi:upload"),
    ("nadwyzka_9700w", "Nadwyżka 9700W", "mdi:flash"),
    ("eksport_pv_blokada", "Eksport PV + blokada", "mdi:solar-power"),
    ("przywroc_ladowanie", "Przywróć ładowanie", "mdi:battery-charging"),
    ("zablokuj_ladowanie", "Zablokuj ładowanie PV", "mdi:battery-off"),
    ("odblokuj_ladowanie", "Odblokuj ładowanie PV", "mdi:battery-check"),
    ("wlacz_ladowanie_siec", "Włącz ładowanie z sieci", "mdi:power-plug"),
    ("wylacz_ladowanie_siec", "Wyłącz ładowanie z sieci", "mdi:power-plug-off"),
]

TIMES = [
    ("pv_export_start", "PV Eksport Start"),
    ("pv_export_stop", "PV Eksport Stop"),
    ("bateria_sprzedaz_start", "Bateria Sprzedaż Start"),
    ("bateria_sprzedaz_stop", "Bateria Sprzedaż Stop"),
    ("bateria_sprzedaz_start_2", "Bateria Sprzedaż Start 2"),
    ("bateria_sprzedaz_stop_2", "Bateria Sprzedaż Stop 2"),
    ("start_grid_charge", "Ładowanie Sieć Start"),
    ("stop_grid_charge", "Ładowanie Sieć Stop"),
    ("start_grid_charge_2", "Ładowanie Sieć Start 2"),
    ("stop_grid_charge_2", "Ładowanie Sieć Stop 2"),
]

NUMBERS = [
    ("minimalny_soc_dla_wylaczenia_sprzedazy", "Min SOC do przejścia w auto", 0, 100, 1, "%"),
    ("min_soc_for_sell", "Min SOC do sprzedaży 6000W", 0, 100, 1, "%"),
    ("min_soc_for_pv_export", "Min SOC do eksportu PV", 0, 100, 1, "%"),
    ("min_soc_for_pv_export_stop", "Min SOC do stopu eksportu PV", 0, 100, 1, "%"),
    ("load_forecast_override", "Prognoza zużycia — override (0 = auto)", 0, 100, 0.1, "kWh"),
    ("grid_import_daily_limit", "Dzienny limit importu z sieci", 0, 100, 0.1, "kWh"),
    ("grid_import_sell_block_w", "Blokada sprzedaży — próg importu (0 = wył.)", 0, 50000, 100, "W"),
    ("grid_arbitrage_block_kwh", "Blokada arbitrażu — tolerancja (0 = wył.)", 0, 20, 0.1, "kWh"),
    ("low_price_threshold", "Niska cena RCE — próg reakcji", -5, 5, 0.01, "PLN/kWh"),
    ("min_sell_margin", "Min. marża sprzedaży", 0, 5, 0.01, "PLN/kWh"),
    ("cycle_efficiency", "Sprawność cyklu baterii", 50, 100, 1, "%"),
    ("reserve_floor_soc", "Dynamiczna rezerwa — minimum", 0, 60, 1, "%"),
    ("auto_apply_max_shift_h", "Auto-stosowanie — maks. przesunięcie godzin (0 = bez limitu)", 0, 12, 1, "h"),
    ("inverter_floor_soc", "Próg odcięcia baterii w falowniku (0 = auto z falownika)", 0, 60, 1, "%"),
    ("dawn_margin_soc", "Margines SOC ponad próg odcięcia (plan nocny/dzienny)", 0, 40, 1, "%"),
    ("sell_export_power_w", "Moc sprzedaży (przycisk „Sprzedaż”)", 0, 30000, 100, "W"),
    ("surplus_power_w", "Moc nadwyżki (tryb Zero Export)", 0, 30000, 100, "W"),
    ("normal_charge_current", "Prąd ładowania po odblokowaniu (0 = zapamiętany/auto)", 0, 400, 1, "A"),
    ("battery_charge_sign", "Znak mocy baterii przy ładowaniu (−1 / +1; 0 = auto)", -1, 1, 1, ""),
    ("storm_mode_hours", "Tryb burzowy — czas trwania", 1, 96, 1, "h"),
    ("vacation_load_w", "Tryb urlopowy — stałe zużycie domu", 0, 5000, 10, "W"),
]

NUMBER_DEFAULTS = {
    "minimalny_soc_dla_wylaczenia_sprzedazy": 20,
    "min_soc_for_sell": 50,
    "min_soc_for_pv_export": 20,
    "min_soc_for_pv_export_stop": 5,
    "load_forecast_override": 0,
    "grid_import_daily_limit": 1.0,
    "grid_import_sell_block_w": 2000,
    "grid_arbitrage_block_kwh": 0.5,
    "low_price_threshold": 0.0,
    "min_sell_margin": DEFAULT_MIN_SELL_MARGIN,
    "cycle_efficiency": 90,
    "reserve_floor_soc": 15,
    "auto_apply_max_shift_h": 4,
    "inverter_floor_soc": 0,
    "dawn_margin_soc": 10,
    "sell_export_power_w": 6000,
    "surplus_power_w": 9700,
    "normal_charge_current": 0,
    "battery_charge_sign": 0,
    "storm_mode_hours": 24,
    "vacation_load_w": 250,
}

# Encje falownika sterowane przyciskami (Deye / Solarman)
WORK_MODE_EID = "select.inverter_work_mode"
EXPORT_SURPLUS_EID = "number.inverter_export_surplus_power"
CHARGE_CURRENT_EID = "number.inverter_battery_max_charging_current"
TOU_EID = "select.inverter_time_of_use"
NORMAL_CHARGE_CURRENT = 170
MODE_EXPORT = "Export First"
MODE_ZERO = "Zero Export To Load"

# Sensory runtime (wartości liczone przez BmsRuntime): key, nazwa, jednostka, ikona
RUNTIME_SENSORS = [
    ("decision_log", "BMS Dziennik decyzji", None, "mdi:clipboard-text-clock"),
    ("profit_today", "BMS Bilans dziś", "PLN", "mdi:cash"),
    ("profit_month", "BMS Bilans miesiąc", "PLN", "mdi:cash-multiple"),
    ("profit_total", "BMS Bilans łącznie", "PLN", "mdi:cash-register"),
    ("reserve_soc", "BMS Rezerwa SOC", "%", "mdi:battery-heart-variant"),
    ("plan_curve", "BMS Plan 24 h", None, "mdi:chart-areaspline"),
    ("battery_health", "BMS Sprawność baterii", "%", "mdi:battery-heart"),
    ("monthly_report", "BMS Raport miesięczny", "PLN", "mdi:file-chart"),
    ("monitor_status", "BMS Stan monitoringu", None, "mdi:shield-check"),
    ("devices", "BMS Urządzenia", None, "mdi:power-plug"),
]

PLATFORMS = ["sensor", "binary_sensor", "switch", "button", "number", "time"]