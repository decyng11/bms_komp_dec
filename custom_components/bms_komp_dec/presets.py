"""Presety falowników — wzorce encji do auto-detekcji."""
from __future__ import annotations

PRESETS: dict[str, dict[str, list[str]]] = {
    "deye_solarman": {
        "soc": ["inverter_battery", "battery_soc", "bateria_soc"],
        "battery_power": ["inverter_battery_power", "battery_power"],
        "pv_power": ["inverter_pv_power", "pv_power", "inverter_pv"],
        "load_power": ["inverter_load_power", "load_power", "inverter_load"],
        "grid_power": ["inverter_grid_power", "grid_power"],
        "pv_production_today": ["inverter_today_production", "pv_production_today"],
        "battery_charge_today": ["inverter_today_battery_charge"],
        "battery_discharge_today": ["inverter_today_battery_discharge"],
        "grid_export_today": ["inverter_today_energy_export"],
        "grid_import_today": ["inverter_today_energy_import"],
        "load_consumption_today": ["inverter_today_load_consumption"],
        "work_mode": ["inverter_work_mode", "work_mode"],
        "grid_charging": ["inverter_battery_grid_charging", "grid_charging"],
        "export_surplus": ["inverter_energy_export", "export_surplus"],
        "charge_current": ["inverter_battery_max_charging_current", "max_charging"],
        "discharge_current": ["inverter_battery_max_discharging_current", "max_discharging"],
        "battery_voltage": ["inverter_battery_voltage"],
        "battery_current": ["inverter_battery_current"],
        "battery_temperature": ["inverter_battery_temperature"],
        "inverter_temperature": ["inverter_temperature"],
        "tou_select": ["inverter_time_of_use"],
        "force_tou": ["inverter_force_time_use"],
    },
    "growatt": {
        "soc": ["growatt_battery_soc", "battery_soc"],
        "pv_power": ["growatt_pv_power", "pv_power"],
        "load_power": ["growatt_load_power", "growatt_output_power"],
        "grid_power": ["growatt_grid_power"],
        "work_mode": ["growatt_work_mode", "work_mode"],
        "charge_current": ["growatt_max_charge_current"],
        "discharge_current": ["growatt_max_discharge_current"],
    },
    "victron": {
        "soc": ["victron_battery_soc", "battery_soc", "vebus_soc"],
        "pv_power": ["victron_pv_power", "solar_charger"],
        "load_power": ["victron_load", "vebus_ac_consumption"],
        "grid_power": ["victron_grid", "vebus_ac_input"],
    },
}

# Domeny encji docelowych dla poszczególnych kluczy presetów
_DOMAIN_MAP = {
    "soc": "sensor", "battery_power": "sensor", "pv_power": "sensor",
    "load_power": "sensor", "grid_power": "sensor", "pv_production_today": "sensor",
    "battery_charge_today": "sensor", "battery_discharge_today": "sensor",
    "grid_export_today": "sensor", "grid_import_today": "sensor",
    "load_consumption_today": "sensor", "work_mode": "select",
    "grid_charging": "switch", "export_surplus": "number", "charge_current": "number",
    "discharge_current": "number", "battery_voltage": "sensor", "battery_current": "sensor",
    "battery_temperature": "sensor", "inverter_temperature": "sensor",
    "tou_select": "select", "force_tou": "switch",
}


def find_entity(hass_states, domain: str, patterns: list[str]) -> str | None:
    """Znajdź entity_id po wzorcach. Priorytet: exact match > contains (kolejność wzorców)."""
    if not patterns:
        return None
    matches: list[tuple[int, str]] = []
    prefix = f"{domain}."
    for eid in hass_states:
        if not eid.startswith(prefix):
            continue
        eid_lower = eid.lower()
        for i, pattern in enumerate(patterns):
            p_lower = pattern.lower()
            if eid_lower == prefix + p_lower:
                matches.append((0, eid))
                break
            if p_lower in eid_lower:
                matches.append((i + 1, eid))
                break
    if not matches:
        return None
    matches.sort(key=lambda m: (m[0], len(m[1])))
    return matches[0][1]


def detect_entities(hass_states, preset: str) -> dict[str, str]:
    """Wykryj encje dla presetu. Zwraca {preset_key: entity_id}."""
    result: dict[str, str] = {}
    patterns = PRESETS.get(preset, {})
    if not patterns:
        return result
    for field, pats in patterns.items():
        dom = _DOMAIN_MAP.get(field, "sensor")
        eid = find_entity(hass_states, dom, pats)
        if eid:
            result[field] = eid
    return result


def detect_inverter_brand(hass_states) -> str:
    """Wykryj markę inwertera po entity_id."""
    ids = " ".join(hass_states).lower()
    if "solarman" in ids or "deye" in ids or "inverter_battery_power" in ids:
        return "deye_solarman"
    if "growatt" in ids:
        return "growatt"
    if "victron" in ids:
        return "victron"
    return "custom"

# ---------------------------------------------------------------- ha-solarman
import re as _re

from .solarman_defs import SOLARMAN_DEFS

_ROLE_DOMAIN = {
    **_DOMAIN_MAP,
}
_CORE_ROLES = ("soc", "battery_power", "pv_power", "load_power", "grid_power")
_MIN_CORE_MATCHES = 2


def _slug(text: str | None) -> str:
    return _re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


def _direct_inverter_entry_ids(hass) -> set[str]:
    """Identyfikatory wpisów falownika dodanych bezpośrednio (tryb bez ha-solarman)."""
    try:
        from .const import DOMAIN
        return {e.entry_id for e in hass.config_entries.async_entries(DOMAIN)
                if (e.data or {}).get("kind") == "inverter"}
    except Exception:  # noqa: BLE001
        return set()


def _state_unit(hass, eid: str) -> str | None:
    """Jednostka z aktualnego stanu encji (None, gdy stanu albo jednostki nie ma)."""
    try:
        st = hass.states.get(eid)
        unit = (st.attributes or {}).get("unit_of_measurement") if st is not None else None
        return str(unit) if unit else None
    except Exception:  # noqa: BLE001
        return None


def collect_records(hass) -> list[dict]:
    """Encje z rejestru (platforma, translation_key, nazwa, urządzenie) — niezależnie od języka HA."""
    records: list[dict] = []
    direct_ids = _direct_inverter_entry_ids(hass)
    try:
        from homeassistant.helpers import entity_registry as er
        reg = er.async_get(hass)
        for ent in reg.entities.values():
            records.append({
                "entity_id": ent.entity_id,
                # falownik dodany bezpośrednio w tej integracji to dla planera to samo co ha-solarman
                "platform": "solarman" if getattr(ent, "config_entry_id", None) in direct_ids else ent.platform,
                "translation_key": getattr(ent, "translation_key", None),
                "name": getattr(ent, "original_name", None) or getattr(ent, "name", None),
                "device_id": getattr(ent, "device_id", None),
                "unit": _state_unit(hass, ent.entity_id),
            })
    except Exception:  # noqa: BLE001
        pass
    known = {r["entity_id"] for r in records}
    for eid in hass.states.async_entity_ids():          # encje bez wpisu w rejestrze (np. YAML)
        if eid not in known:
            records.append({"entity_id": eid, "platform": None, "translation_key": None,
                            "name": None, "device_id": None, "unit": _state_unit(hass, eid)})
    return records


def _match_role(records: list[dict], role: str, slugs: list[str]) -> str | None:
    dom = _ROLE_DOMAIN.get(role, "sensor")
    cands = [r for r in records if r["entity_id"].startswith(dom + ".")]
    for slug in slugs:                                   # kolejność = priorytet nazw
        for pred in (
            lambda r: r["translation_key"] == slug,
            lambda r: _slug(r["name"]) == slug,
            lambda r: r["entity_id"].split(".", 1)[1] == slug,
            lambda r: r["entity_id"].split(".", 1)[1].endswith("_" + slug),
        ):
            hits = sorted((r["entity_id"] for r in cands if pred(r)), key=lambda e: (len(e), e))
            if hits:
                return hits[0]
    return None


_THREE_PHASE_RE = _re.compile(r"(?:^|[_-])(?:p3|3p|3ph|r-3h|d3)(?:$|[_-])|3-faz", _re.I)


def detect_solarman(records: list[dict]) -> dict | None:
    """Dobiera definicję ha-solarman i encje.

    Zwraca {'brand','label','entities':{rola: entity_id},'matched':int} albo None."""
    solarman = [r for r in records if r["platform"] == "solarman"]
    pool = solarman or records
    groups: dict[str, list[dict]] = {}
    if solarman:
        for r in solarman:
            groups.setdefault(r["device_id"] or "_", []).append(r)
    else:
        groups["_"] = pool
    best = None
    for gid, recs in groups.items():
        n_ph = phase_count(detect_phase_roles(recs))      # liczba faz urządzenia — rozstrzyga remisy między definicjami 1- i 3-fazowymi
        for brand, spec in SOLARMAN_DEFS.items():
            found: dict[str, str] = {}
            for role, slugs in spec["roles"].items():
                eid = _match_role(recs, role, slugs)
                if eid:
                    found[role] = eid
            core = sum(1 for c in _CORE_ROLES if c in found)
            if core < _MIN_CORE_MATCHES:
                continue
            three = bool(_THREE_PHASE_RE.search(brand) or _THREE_PHASE_RE.search(spec["label"]))
            fits = 1 if (three == (n_ph >= 3)) else 0       # remis wyniku: wygrywa definicja zgodna z liczbą faz
            score = (core * 3 + len(found), fits, len(found))
            if best is None or score > best["score"]:
                best = {"score": score, "brand": brand, "label": spec["label"],
                        "entities": found, "matched": len(found), "device": gid,
                        "_recs": recs}
    if best is not None:
        # fazy L1–L3 dobieramy osobno (po wyborze marki), żeby nie zmieniały wyboru definicji
        phases = detect_phase_roles(best.pop("_recs"))
        best["entities"].update(phases)
        best["phases"] = phase_count(phases)
    return best


# ---------------------------------------------------------------- fazy L1–L3
# Role fazowe: nazwa roli = klucz konfiguracji. Slugi nazw encji z definicji Solarman (Deye hybrid/P3/string i in.),
# w kolejności priorytetu. Każda rola ma wymaganą jednostkę — encja o innym typie (np. napięcie zamiast prądu) odpada.
_PHASE_UNITS = {"voltage": ("V",), "current": ("A",), "power": ("W", "kW")}
_PHASE_SLUGS: dict[str, list[str]] = {}
for _n in (1, 2, 3):
    _PHASE_SLUGS[f"grid_voltage_l{_n}"] = [f"grid_l{_n}_voltage"] + (["grid_voltage"] if _n == 1 else [])
    _PHASE_SLUGS[f"grid_current_l{_n}"] = [f"grid_l{_n}_current", f"external_ct{_n}_current"] + (["grid_current"] if _n == 1 else [])
    _PHASE_SLUGS[f"grid_power_l{_n}"] = [f"grid_l{_n}_power", f"external_ct{_n}_power"]
    _PHASE_SLUGS[f"load_voltage_l{_n}"] = [f"load_l{_n}_voltage", f"output_l{_n}_voltage"] + (["load_voltage", "output_voltage"] if _n == 1 else [])
    _PHASE_SLUGS[f"load_current_l{_n}"] = [f"load_l{_n}_current", f"output_l{_n}_current"] + (["load_current"] if _n == 1 else [])
    _PHASE_SLUGS[f"load_power_l{_n}"] = [f"load_l{_n}_power", f"output_l{_n}_power"]


_PHASE_ROLE_RE = _re.compile(r"^(?:grid|load)_(voltage|current|power)_l[123]$")


def unit_ok(role: str, unit: str | None) -> bool:
    """Czy jednostka pasuje do roli fazowej. Brak jednostki (encja bez stanu) nie dyskwalifikuje."""
    if not unit:
        return True
    m = _PHASE_ROLE_RE.match(role)
    return unit in _PHASE_UNITS[m.group(1)] if m else True


def detect_phase_roles(records: list[dict]) -> dict[str, str]:
    """{rola fazowa: entity_id} dla napięć, prądów i mocy sieci i domu (L1–L3), tylko encje o właściwej jednostce."""
    out: dict[str, str] = {}
    for role, slugs in _PHASE_SLUGS.items():
        ok = [r for r in records if unit_ok(role, r.get("unit"))]
        eid = _match_role(ok, role, slugs)
        if eid:
            out[role] = eid
    return out


def phase_count(entities: dict[str, str]) -> int:
    """Ile faz ma falownik wg znalezionych encji (1–3): najwyższa faza, dla której jest jakakolwiek rola."""
    n = 0
    for k in entities:
        if k.endswith(("_l1", "_l2", "_l3")):
            n = max(n, int(k[-1]))
    return n


# ---------------------------------------------------------------- źródła cen
# Znane encje cen (sprawdzane po kolei). Encja ZAKUPU ma podawać bieżącą cenę zakupu w stanie; listy cen godzinowych
# (taryfa dynamiczna) planer czyta z niej albo z jej „rodzeństwa” tej samej integracji (np. sensor.pstryk_json_buy).
PRICE_SELL_CANDIDATES = (
    "sensor.rce_pse_cena", "sensor.rce_pse_price", "sensor.rce_price", "sensor.rce_pse_cena_za_kwh",
    "sensor.pstryk_current_sell_price", "sensor.pstryk_sell_price", "sensor.pstryk_json_sell",
)
PRICE_BUY_CANDIDATES = (
    "sensor.energy_hub_aktualna_cena_g12w",
    "sensor.pstryk_current_buy_price", "sensor.pstryk_buy_price", "sensor.pstryk_json_buy",
    "sensor.pstryk_current_price",          # pstryk-ha-next (domena pstryk_energy): cena zakupu + listy today/tomorrow_prices
)


_FORECAST_DEFAULTS = ("sensor.solcast_pv_forecast_forecast_today", "sensor.solcast_pv_forecast_forecast_tomorrow")
_FORECAST_RE = {"pv_forecast_today": _re.compile(r"energy_production_today(_\d+)?$"),
                "pv_forecast_tomorrow": _re.compile(r"energy_production_tomorrow(_\d+)?$")}


def detect_forecast_entities(hass) -> dict[str, str]:
    """{'pv_forecast_today': ..., 'pv_forecast_tomorrow': ...}: Solcast, a gdy go nie ma — Forecast.Solar.

    Forecast.Solar rozpoznajemy po integracji (platforma „forecast_solar”) i kluczu tłumaczenia, nie po nazwie,
    bo identyfikator encji zależy od języka HA. Zwraca tylko te strony, dla których coś znaleziono."""
    out: dict[str, str] = {}
    try:
        for key, eid in zip(("pv_forecast_today", "pv_forecast_tomorrow"), _FORECAST_DEFAULTS):
            if hass.states.get(eid) is not None:
                out[key] = eid
        if len(out) == 2:
            return out
        recs = [r for r in collect_records(hass) if r.get("platform") == "forecast_solar" and r["entity_id"].startswith("sensor.")
                and hass.states.get(r["entity_id"]) is not None and r.get("unit") in (None, "kWh")]
        for key, rx in _FORECAST_RE.items():
            if key in out:
                continue
            hits = sorted(r["entity_id"] for r in recs
                          if r.get("translation_key") == key.replace("pv_forecast", "energy_production")
                          or rx.search(r["entity_id"]))
            if hits:
                out[key] = hits[0]
    except Exception:  # noqa: BLE001
        pass
    return out


def _num_state(hass, eid: str | None) -> float | None:
    try:
        st = hass.states.get(eid) if eid else None
        if st is None or st.state in ("unavailable", "unknown", "", "none"):
            return None
        return float(str(st.state).replace(",", "."))
    except (TypeError, ValueError):
        return None


def detect_battery_capacity(hass, records: list[dict] | None = None) -> tuple[float, str] | None:
    """Pojemność baterii z falownika: (kWh, źródło) albo None.

    1) encja „Battery Capacity” w kWh (wyliczona przez falownik) — działa tak samo dla LV i HV;
    2) „Battery Capacity” w Ah × napięcie baterii — tylko przybliżenie (źródło „ah_v”), nigdy nie jest pewne;
    brak wiarygodnej wartości (poza 1–100 kWh) = None."""
    try:
        recs = records if records is not None else collect_records(hass)
        cap = [r for r in recs if r.get("platform") == "solarman" and "capacity" in str(r.get("name") or "").lower()
               and "corrected" not in str(r.get("name") or "").lower() and not _re.search(r"battery_\d", r["entity_id"])]
        for r in cap:
            if r.get("unit") == "kWh":
                v = _num_state(hass, r["entity_id"])
                if v is not None and 1.0 <= v <= 100.0:
                    return round(v, 2), "kwh"
        volt = [r for r in recs if r.get("platform") == "solarman" and r["entity_id"].startswith("sensor.")
                and str(r.get("name") or "").strip().lower() == "battery voltage" and r.get("unit") == "V"]
        for r in cap:
            if r.get("unit") == "Ah":
                ah = _num_state(hass, r["entity_id"])
                for vr in volt:
                    volts = _num_state(hass, vr["entity_id"])
                    if ah and volts and ah > 0 and volts > 0:
                        kwh = ah * volts / 1000.0
                        if 1.0 <= kwh <= 100.0:
                            return round(kwh, 1), "ah_v"
    except Exception:  # noqa: BLE001
        pass
    return None


def detect_price_entities(hass) -> dict[str, str]:
    """{'price_sell_entity': ..., 'price_buy_entity': ...} — pierwsza istniejąca znana encja dla każdej strony.

    Strony nigdy się nie mieszają: kandydaci sprzedaży i zakupu to rozłączne listy."""
    out: dict[str, str] = {}
    try:
        for key, cands in (("price_sell_entity", PRICE_SELL_CANDIDATES), ("price_buy_entity", PRICE_BUY_CANDIDATES)):
            for eid in cands:
                if hass.states.get(eid) is not None:
                    out[key] = eid
                    break
    except Exception:  # noqa: BLE001
        pass
    return out
