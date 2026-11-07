"""Wyszukiwanie urządzeń z licznikiem energii (kWh) w Home Assistant — propozycje dla zakładki „Urządzenia”.

Szukamy encji `sensor` z jednostką Wh/kWh/MWh, grupujemy je po urządzeniu HA i do każdego dobieramy encję mocy
(W/kW) tego samego urządzenia. Pomijamy: encje EMS i falownika, liczniki domu z panelu Energia (sieć, PV,
bateria — razem z ich urządzeniami), encje z konfiguracji EMS, prognozy PV, kopie liczników z Utility Meter
oraz urządzenia już dodane. Nic tu nie jest zapisywane — karta pokazuje listę, a zapis idzie przez devices_set.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any, Iterable

from .devices import CATEGORIES, MAX_DEVICES

_LOGGER = logging.getLogger(__name__)

ENERGY_UNITS = {"wh", "kwh", "mwh"}
POWER_UNITS = {"w", "kw"}
MAX_CANDIDATES = 120

# integracje, których liczniki energii nie są „urządzeniami domu” (falowniki, prognozy, pomocnicze)
SKIP_PLATFORMS = {
    "utility_meter", "forecast_solar", "solcast_solar", "statistics", "filter", "energy",
    "solarman", "deye", "deye_cloud", "sunsynk", "solis", "solax", "goodwe", "growatt_server", "huawei_solar",
    "solaredge", "solaredge_modbus", "fronius", "sma", "enphase_envoy", "victron", "foxess", "sofar",
    "fusion_solar", "tibber", "pstryk", "rce_pse",
}
# nazwy liczników okresowych (dzienny / miesięczny …) — gorszy wybór niż licznik całkowity
_PERIOD_RE = re.compile(r"(today|dzis|dziś|daily|dzienn|week|tydz|month|miesi|year|rok|roczn|yesterday|wczoraj|last|ostatni)",
                        re.IGNORECASE)

# (wzorzec w nazwie, kategoria) — kolejność ma znaczenie (pierwsze dopasowanie wygrywa)
_GUESS: list[tuple[str, str]] = [
    (r"cwu|c\.w\.u|dhw|ciep[łl]a woda|hot ?water", "heat_pump_dhw"),
    (r"pomp[ay]? ciep|heat ?pump|heatpump|panasonic aquarea|daikin altherma", "heat_pump"),
    (r"bojler|grza[łl]k|boiler|water ?heater|termy", "boiler"),
    (r"pod[łl]og|floor", "floor_heating"),
    (r"grzejnik|promiennik|heater|radiator|konwektor", "heater"),
    (r"obiegow|cyrkul|circulat|kocio[łl]|sterownik pieca", "circ_pump"),
    (r"klima|air ?con|\bac\b|split", "ac"),
    (r"rekuper|wentyl|vent|hrv|mvhr", "ventilation"),
    (r"osusz|dehumid", "dehumidifier"),
    (r"[łl]adowar|wallbox|\bev\b|charger|tesla|easee|zappi|go-?e|samoch|\bauto\b", "ev"),
    (r"rower|e-?bike|hulaj|scooter", "ebike"),
    (r"zamra[żz]|freezer", "freezer"),
    (r"lod[óo]w|fridge|refrig|ch[łl]odziark", "fridge"),
    (r"indukc|induction|p[łl]yt[ay]? |\bhob\b|kuchenk", "induction"),
    (r"piekar|oven", "oven"),
    (r"zmywar|dish ?wash", "dishwasher"),
    (r"czajn|kettle", "kettle"),
    (r"ekspres|kaw[ay]|coffee", "coffee"),
    (r"mikrofal|microwave", "microwave"),
    (r"susz|dryer", "dryer"),
    (r"pralk|wash", "washer"),
    (r"hydrofor|pomp[ay]? wod|water ?pump|studni", "water_pump"),
    (r"oczyszcz|przepomp|szamb|septic", "septic"),
    (r"podgrzew.*basen|basen.*grza|pool ?heat|spa|jacuzzi|wanna", "pool_heat"),
    (r"basen|pool", "pool_pump"),
    (r"nawadn|podlew|irrigat|sprinkl", "irrigation"),
    (r"serwer|server|komputer|\bpc\b|\bnas\b|desktop|workstation", "server"),
    (r"router|modem|sie[ćc]|network|\bups\b|access ?point|switch poe", "network"),
    (r"\btv\b|telewiz|rtv|audio|kino|soundbar|konsol|playstation|xbox", "tv"),
    (r"zewn|ogr[óo]d|garden|outdoor|elewac|taras", "light_out"),
    (r"[śs]wiat[łl]|o[śs]wietl|lamp|light|led", "light_in"),
    (r"spr[ęe][żz]ark|compressor", "compressor"),
    (r"kosiark|mower|robot kosz", "mower"),
    (r"narz[ęe]dz|tool|warsztat|workshop|pi[łl]a|spawark", "tools"),
]
_GUESS_RE = [(re.compile(p, re.IGNORECASE), c) for p, c in _GUESS]


def guess_category(*names: str | None) -> str:
    text = " ".join(n for n in names if n)
    for rx, cat in _GUESS_RE:
        if rx.search(text):
            return cat if cat in CATEGORIES else "other"
    return "other"


def _unit(attrs: dict) -> str:
    return str((attrs or {}).get("unit_of_measurement") or "").strip().lower()


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _collect_stats(obj: Any, out: set[str]) -> None:
    """Wszystkie identyfikatory 'stat_*' z konfiguracji panelu Energia (dowolnie zagnieżdżone)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and str(k).startswith("stat_"):
                out.add(v)
            else:
                _collect_stats(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_stats(v, out)


def energy_prefs_split(prefs: Any) -> tuple[set[str], dict[str, str]]:
    """(liczniki domu ze źródeł energii, {licznik urządzenia: encja mocy lub ''}) z ustawień panelu Energia."""
    sources: set[str] = set()
    devices: dict[str, str] = {}
    if not isinstance(prefs, dict):
        return sources, devices
    _collect_stats(prefs.get("energy_sources") or [], sources)
    for dc in prefs.get("device_consumption") or []:
        if isinstance(dc, dict) and isinstance(dc.get("stat_consumption"), str):
            devices[dc["stat_consumption"]] = dc.get("stat_rate") if isinstance(dc.get("stat_rate"), str) else ""
    return sources, devices


def _energy_rank(e: dict) -> tuple:
    """Lepszy licznik urządzenia: całkowity (total_increasing / total), bez „dziś / miesiąc” w nazwie, w kWh."""
    return (0 if e["state_class"] in ("total_increasing", "total") else 1,
            1 if _PERIOD_RE.search(f'{e["eid"]} {e["name"]}') else 0,
            0 if e["unit"] == "kwh" else 1,
            len(e["eid"]))


def _power_rank(p: dict) -> tuple:
    bad = re.search(r"(max|min|avg|średn|sredn|peak|limit|setpoint|zadan)", f'{p["eid"]} {p["name"]}', re.IGNORECASE)
    return (0 if p["device_class"] == "power" else 1, 1 if bad else 0, len(p["eid"]))


def build_candidates(entities: Iterable[dict], *, exclude_eids: set[str], exclude_devices: set[str],
                     energy_devices: dict[str, str], existing: list[dict], areas: dict[str, str],
                     device_names: dict[str, str], device_areas: dict[str, str]) -> dict[str, Any]:
    """Czysta logika (testowalna bez HA).

    entities: [{"eid", "name", "platform", "device_id", "area_id", "unit", "device_class", "state_class",
                "state", "disabled", "hidden"}] — tylko encje sensor.
    """
    used = {d.get("energy_eid") for d in existing} | {d.get("power_eid") for d in existing}
    used.discard("")
    used.discard(None)
    used_devices: set[str] = set()
    skipped = {"bms": 0, "home": 0, "helper": 0, "added": 0}

    ents = [e for e in entities if not e.get("disabled")]
    by_eid = {e["eid"]: e for e in ents}
    for eid in used:
        dev = (by_eid.get(eid) or {}).get("device_id")
        if dev:
            used_devices.add(dev)

    energy: list[dict] = []
    power: list[dict] = []
    for e in ents:
        unit = e.get("unit") or ""
        if unit in ENERGY_UNITS:
            energy.append(e)
        elif unit in POWER_UNITS:
            power.append(e)

    groups: dict[str, dict[str, Any]] = {}
    for e in energy:
        eid, dev, plat = e["eid"], e.get("device_id") or "", e.get("platform") or ""
        if plat in SKIP_PLATFORMS or plat == "bms_komp_dec":
            skipped["bms" if plat in ("bms_komp_dec", "solarman") else "helper"] += 1
            continue
        if eid in exclude_eids or (dev and dev in exclude_devices):
            skipped["home"] += 1
            continue
        if eid in used or (dev and dev in used_devices):
            skipped["added"] += 1
            continue
        key = dev or eid
        g = groups.setdefault(key, {"key": key, "device_id": dev, "energy": [], "power": []})
        g["energy"].append(e)

    for p in power:
        dev = p.get("device_id") or ""
        if p["eid"] in exclude_eids or p["eid"] in used:
            continue
        if dev and dev in groups:
            groups[dev]["power"].append(p)

    out: list[dict[str, Any]] = []
    for key, g in groups.items():
        g["energy"].sort(key=_energy_rank)
        best = g["energy"][0]
        pw = sorted(g["power"], key=_power_rank)
        if not pw and not g["device_id"]:
            # encja bez urządzenia: para po nazwie (sensor.x_energy → sensor.x_power)
            stem = re.sub(r"_(energy|energia|kwh|consumption|zuzycie|total|licznik)(_total)?$", "", best["eid"])
            for suf in ("_power", "_moc", "_w", "_current_power", "_active_power"):
                cand = by_eid.get(stem + suf)
                if cand and (cand.get("unit") or "") in POWER_UNITS and cand["eid"] not in used:
                    pw = [cand]
                    break
        ed = next((e["eid"] for e in g["energy"] if e["eid"] in energy_devices), None)
        if ed:
            best = next(e for e in g["energy"] if e["eid"] == ed)
            rate = energy_devices.get(ed) or ""
            rp = by_eid.get(rate)
            if rp and (rp.get("unit") or "") in POWER_UNITS and rate not in used:
                pw = [rp] + [p for p in pw if p["eid"] != rate]
        dev = g["device_id"]
        name = (device_names.get(dev) if dev else None) or best.get("name") or best["eid"]
        area_id = best.get("area_id") or (device_areas.get(dev) if dev else None) or ""
        pw_best = pw[0] if pw else None
        power_w = None
        if pw_best:
            v = _num(pw_best.get("state"))
            if v is not None:
                power_w = v * (1000.0 if pw_best.get("unit") == "kw" else 1.0)
        out.append({
            "key": key, "name": str(name)[:40], "room": areas.get(area_id, "")[:30],
            "category": guess_category(name, best.get("name"), best["eid"]),
            "energy_eid": best["eid"], "power_eid": pw_best["eid"] if pw_best else "",
            "energy_options": [{"eid": e["eid"], "name": e.get("name") or e["eid"], "unit": e.get("unit"),
                                "value": _num(e.get("state")), "stats": e.get("state_class") in ("total_increasing", "total")}
                               for e in g["energy"]],
            "power_options": [{"eid": p["eid"], "name": p.get("name") or p["eid"], "unit": p.get("unit"),
                               "value": _num(p.get("state"))} for p in pw],
            "power_w": None if power_w is None else round(power_w, 1),
            "stats": best.get("state_class") in ("total_increasing", "total"),
            "energy_dashboard": bool(ed),
            "integration": best.get("platform") or "",
            "unavailable": str(best.get("state")) in ("unavailable", "unknown", "None", ""),
        })
    out.sort(key=lambda c: (not c["energy_dashboard"], c["unavailable"], -(c["power_w"] or 0.0), c["name"].lower()))
    return {"candidates": out[:MAX_CANDIDATES], "total": len(out), "skipped": skipped,
            "free_slots": max(0, MAX_DEVICES - len(existing))}


def _cfg_entities(cfg: Any, out: set[str]) -> None:
    if isinstance(cfg, dict):
        for v in cfg.values():
            _cfg_entities(v, out)
    elif isinstance(cfg, (list, tuple)):
        for v in cfg:
            _cfg_entities(v, out)
    elif isinstance(cfg, str) and re.match(r"^sensor\.[a-z0-9_]+$", cfg):
        out.add(cfg)


async def async_discover(hass, cfg: dict, existing: list[dict]) -> dict[str, Any]:
    """Zbiera dane z rejestrów HA i panelu Energia, zwraca propozycje (build_candidates)."""
    from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    prefs = None
    try:
        from homeassistant.components.energy.data import async_get_manager
        prefs = (await async_get_manager(hass)).data
    except Exception as err:  # noqa: BLE001 — panel Energia nieskonfigurowany / brak komponentu
        _LOGGER.debug("EMS: panel Energia niedostępny: %s", err)
    sources, energy_devices = energy_prefs_split(prefs)

    cfg_eids: set[str] = set()
    _cfg_entities(cfg, cfg_eids)
    exclude_eids = set(sources) | cfg_eids

    entities: list[dict] = []
    device_names: dict[str, str] = {}
    device_areas: dict[str, str] = {}
    for st in hass.states.async_all("sensor"):
        attrs = st.attributes or {}
        unit = _unit(attrs)
        if unit not in ENERGY_UNITS and unit not in POWER_UNITS:
            continue
        ent = ent_reg.async_get(st.entity_id)
        dev_id = getattr(ent, "device_id", None) or ""
        if dev_id and dev_id not in device_names:
            dev = dev_reg.async_get(dev_id)
            if dev is not None:
                device_names[dev_id] = getattr(dev, "name_by_user", None) or getattr(dev, "name", None) or ""
                device_areas[dev_id] = getattr(dev, "area_id", None) or ""
        entities.append({
            "eid": st.entity_id, "name": attrs.get("friendly_name") or st.entity_id,
            "platform": getattr(ent, "platform", "") or "", "device_id": dev_id,
            "area_id": getattr(ent, "area_id", None) or "", "unit": unit,
            "device_class": attrs.get("device_class") or "", "state_class": attrs.get("state_class") or "",
            "state": st.state, "disabled": bool(getattr(ent, "disabled_by", None)),
        })

    # urządzenia, do których należą liczniki domu (sieć / PV / bateria) i encje z konfiguracji EMS
    exclude_devices: set[str] = set()
    for e in entities:
        if e["eid"] in exclude_eids and e["device_id"]:
            exclude_devices.add(e["device_id"])

    areas: dict[str, str] = {}
    try:
        areas = {a.id: a.name for a in area_reg.async_list_areas()}
    except Exception:  # noqa: BLE001
        pass

    res = build_candidates(entities, exclude_eids=exclude_eids, exclude_devices=exclude_devices,
                           energy_devices=energy_devices, existing=existing, areas=areas,
                           device_names=device_names, device_areas=device_areas)
    res["energy_dashboard"] = prefs is not None
    return res
