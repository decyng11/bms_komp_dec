"""0.8.4: wyszukiwanie urządzeń z licznikiem kWh (discover.py)."""
import asyncio, sys, types
from common import *   # noqa
import common
from custom_components.bms_komp_dec import discover as D, devices as DV


def E(eid, unit, *, dev="", plat="shelly", name=None, sc="total_increasing", dc=None, state="1.5", area="", disabled=False):
    return {"eid": eid, "name": name or eid, "platform": plat, "device_id": dev, "area_id": area, "unit": unit,
            "device_class": dc or ("energy" if unit in ("wh", "kwh", "mwh") else "power"), "state_class": sc,
            "state": state, "disabled": disabled}


def build(ents, **kw):
    args = dict(exclude_eids=set(), exclude_devices=set(), energy_devices={}, existing=[], areas={"kuchnia": "Kuchnia"},
                device_names={}, device_areas={})
    args.update(kw)
    return D.build_candidates(ents, **args)


async def main():
    # ---------- kategorie z nazwy
    for name, cat in (("Pralka Bosch", "washer"), ("Suszarka", "dryer"), ("Pompa ciepła", "heat_pump"), ("Pompa ciepła CWU", "heat_pump_dhw"),
                      ("Bojler", "boiler"), ("Wallbox garaż", "ev"), ("Zmywarka", "dishwasher"), ("Lodówka", "fridge"),
                      ("Zamrażarka", "freezer"), ("Washing machine", "washer"), ("Heat pump", "heat_pump"), ("Gniazdko 3", "other"),
                      ("Oświetlenie ogród", "light_out"), ("Lampa salon", "light_in"), ("Serwer NAS", "server"), ("Klimatyzacja", "ac")):
        check(f"kategoria „{name}” → {cat}", D.guess_category(name) == cat, D.guess_category(name))
    check("każda zgadywana kategoria istnieje", all(c in DV.CATEGORIES for _, c in D._GUESS))

    # ---------- grupowanie po urządzeniu, dobór mocy i licznika całkowitego
    ents = [E("sensor.pralka_energy", "kwh", dev="d1"), E("sensor.pralka_energy_today", "kwh", dev="d1", sc="total"),
            E("sensor.pralka_power", "w", dev="d1", state="512"), E("sensor.pralka_power_max", "w", dev="d1", state="2000"),
            E("sensor.pralka_voltage", "v", dev="d1")]
    r = build(ents, device_names={"d1": "Pralka"}, device_areas={"d1": "kuchnia"})
    c = r["candidates"]
    check("jedno urządzenie z dwóch liczników", len(c) == 1, c)
    c = c[0]
    check("licznik całkowity zamiast dziennego", c["energy_eid"] == "sensor.pralka_energy", c["energy_eid"])
    check("dobrana moc (nie „max”)", c["power_eid"] == "sensor.pralka_power" and c["power_w"] == 512.0, (c["power_eid"], c["power_w"]))
    check("nazwa z urządzenia, pomieszczenie z obszaru, kategoria", c["name"] == "Pralka" and c["room"] == "Kuchnia" and c["category"] == "washer", c)
    check("opcje: 2 liczniki, 2 moce", len(c["energy_options"]) == 2 and len(c["power_options"]) == 2)
    check("wolne miejsca", r["free_slots"] == DV.MAX_DEVICES)

    r = build([E("sensor.pr_today", "kwh", dev="q"), E("sensor.pralka_energy_total", "kwh", dev="q")])
    check("licznik „dziś” przegrywa z całkowitym", r["candidates"][0]["energy_eid"] == "sensor.pralka_energy_total", r["candidates"][0]["energy_eid"])
    r = build([E("sensor.a_e", "kwh", dev="q", sc=""), E("sensor.a_energy_sum", "kwh", dev="q")])
    check("licznik ze state_class wygrywa", r["candidates"][0]["energy_eid"] == "sensor.a_energy_sum", r["candidates"][0]["energy_eid"])
    r = build([E("sensor.q_e", "kwh", dev="q"), E("sensor.q_p", "w", dev="q")], exclude_eids={"sensor.q_p"})
    check("encja mocy z wykluczeń nie jest proponowana", r["candidates"][0]["power_eid"] == "", r["candidates"][0]["power_eid"])

    # kW przeliczane na W
    r = build([E("sensor.ev_e", "kwh", dev="d2"), E("sensor.ev_p", "kw", dev="d2", state="7.2")], device_names={"d2": "Wallbox"})
    check("moc w kW → W", r["candidates"][0]["power_w"] == 7200.0, r["candidates"][0]["power_w"])

    # ---------- wykluczenia
    ents = [E("sensor.grid_import", "kwh", dev="meter"), E("sensor.meter_l1_energy", "kwh", dev="meter"),
            E("sensor.um_daily", "kwh", plat="utility_meter"), E("sensor.fs_today", "kwh", plat="forecast_solar"),
            E("sensor.bms_x", "kwh", plat="bms_komp_dec"), E("sensor.inv_total", "kwh", plat="solarman"),
            E("sensor.cfg_load", "kwh", dev="loaddev"), E("sensor.pralka_e", "kwh", dev="p1"), E("sensor.pralka_p", "w", dev="p1"),
            E("sensor.off_e", "kwh", dev="o1", disabled=True), E("sensor.bojler_e", "kwh", dev="b1")]
    r = build(ents, exclude_eids={"sensor.grid_import", "sensor.cfg_load"}, exclude_devices={"meter", "loaddev"},
              existing=[{"energy_eid": "sensor.pralka_e", "power_eid": ""}], device_names={"b1": "Bojler"})
    keys = [c["energy_eid"] for c in r["candidates"]]
    check("zostaje tylko bojler", keys == ["sensor.bojler_e"], keys)
    sk = r["skipped"]
    check("liczniki pominięć", sk["home"] == 3 and sk["helper"] == 2 and sk["bms"] == 2 and sk["added"] == 1, sk)
    check("wolne miejsca po dodanych", r["free_slots"] == DV.MAX_DEVICES - 1)

    # moc już używana nie jest proponowana
    r = build([E("sensor.a_e", "kwh", dev="a"), E("sensor.a_p", "w", dev="a")], existing=[{"energy_eid": "", "power_eid": "sensor.a_p"}])
    check("urządzenie, którego moc jest już dodana → pominięte", not r["candidates"] and r["skipped"]["added"] == 1, r)

    # ---------- panel Energia: urządzenie oznaczone, jego encja mocy wybrana, na początku listy
    ents = [E("sensor.zz_e", "kwh", dev="z"), E("sensor.aa_e", "kwh", dev="a"), E("sensor.aa_p1", "w", dev="a"), E("sensor.aa_moc", "w", dev="a")]
    r = build(ents, energy_devices={"sensor.aa_e": "sensor.aa_moc"}, device_names={"a": "Pompa ciepła", "z": "Zzz"})
    c0 = r["candidates"][0]
    check("panel Energia na początku i oznaczone", c0["energy_eid"] == "sensor.aa_e" and c0["energy_dashboard"], c0)
    check("moc z panelu Energia ma pierwszeństwo", c0["power_eid"] == "sensor.aa_moc", c0["power_eid"])

    # ---------- encja bez urządzenia: para po nazwie
    r = build([E("sensor.grzejnik_energy", "kwh"), E("sensor.grzejnik_power", "w", state="1500")])
    c = r["candidates"][0]
    check("bez urządzenia: moc po nazwie", c["power_eid"] == "sensor.grzejnik_power" and c["category"] == "heater", c)

    # bez state_class → brak historii; niedostępne
    r = build([E("sensor.t_e", "kwh", dev="t", sc="", state="unavailable")])
    c = r["candidates"][0]
    check("bez statystyk i niedostępne oznaczone", c["stats"] is False and c["unavailable"] is True, c)

    # ---------- ustawienia panelu Energia
    prefs = {"energy_sources": [{"type": "grid", "flow_from": [{"stat_energy_from": "sensor.imp"}], "flow_to": [{"stat_energy_to": "sensor.exp"}]},
                                {"type": "solar", "stat_energy_from": "sensor.pv", "stat_rate": "sensor.pv_w"},
                                {"type": "grid", "stat_energy_from": "sensor.imp2", "power_config": {"stat_rate_from": "sensor.gw"}}],
             "device_consumption": [{"stat_consumption": "sensor.ev_e", "stat_rate": "sensor.ev_w"}, {"stat_consumption": "sensor.x_e"}]}
    src, devs = D.energy_prefs_split(prefs)
    check("źródła z panelu Energia (stare i nowe formaty)", src == {"sensor.imp", "sensor.exp", "sensor.pv", "sensor.pv_w", "sensor.imp2", "sensor.gw"}, src)
    check("urządzenia z panelu Energia", devs == {"sensor.ev_e": "sensor.ev_w", "sensor.x_e": ""}, devs)
    check("brak ustawień → puste", D.energy_prefs_split(None) == (set(), {}))

    # ---------- async_discover na atrapach rejestrów HA
    hass = stubs.FakeHass()
    def st(eid, v, unit, **a):
        hass.states.set(eid, v, dict({"unit_of_measurement": unit, "friendly_name": a.pop("fn", eid)}, **a))
    st("sensor.grid_in", "100", "kWh", state_class="total_increasing")
    st("sensor.meter_l2", "50", "kWh", state_class="total_increasing")
    st("sensor.pralka_e", "12.5", "kWh", state_class="total_increasing")
    st("sensor.pralka_p", "300", "W")
    st("sensor.ev_e", "40000", "Wh", state_class="total_increasing")
    st("sensor.soc", "50", "%")
    st("sensor.bms_cfg_meter", "5", "kWh", state_class="total")
    reg = {"sensor.grid_in": ("shelly", "meter"), "sensor.meter_l2": ("shelly", "meter"), "sensor.pralka_e": ("shelly", "dp"), "sensor.pralka_p": ("shelly", "dp"),
           "sensor.ev_e": ("easee", "dev"), "sensor.bms_cfg_meter": ("tuya", "cfgdev")}
    ent = lambda eid: types.SimpleNamespace(platform=reg[eid][0], device_id=reg[eid][1], area_id=None, disabled_by=None) if eid in reg else None
    devices = {"dp": types.SimpleNamespace(name="Pralka", name_by_user=None, area_id="lazienka"),
               "dev": types.SimpleNamespace(name="Easee", name_by_user="Wallbox", area_id=None),
               "meter": types.SimpleNamespace(name="Licznik", name_by_user=None, area_id=None),
               "cfgdev": types.SimpleNamespace(name="Gniazdko", name_by_user=None, area_id=None)}
    mods = {
        "homeassistant.helpers.entity_registry": types.SimpleNamespace(async_get=lambda h: types.SimpleNamespace(async_get=ent)),
        "homeassistant.helpers.device_registry": types.SimpleNamespace(async_get=lambda h: types.SimpleNamespace(async_get=lambda i: devices.get(i))),
        "homeassistant.helpers.area_registry": types.SimpleNamespace(async_get=lambda h: types.SimpleNamespace(
            async_list_areas=lambda: [types.SimpleNamespace(id="lazienka", name="Łazienka")])),
    }
    class Mgr:
        data = {"energy_sources": [{"type": "grid", "flow_from": [{"stat_energy_from": "sensor.grid_in"}]}],
                "device_consumption": [{"stat_consumption": "sensor.ev_e"}]}
    async def agm(h): return Mgr()
    energy_mod = types.ModuleType("homeassistant.components.energy"); data_mod = types.ModuleType("homeassistant.components.energy.data")
    data_mod.async_get_manager = agm
    saved = {k: sys.modules.get(k) for k in list(mods) + ["homeassistant.components.energy", "homeassistant.components.energy.data", "homeassistant.helpers"]}
    helpers = sys.modules["homeassistant.helpers"]
    old_attrs = {a: getattr(helpers, a, None) for a in ("entity_registry", "device_registry", "area_registry")}
    for k, m in mods.items():
        sys.modules[k] = m; setattr(helpers, k.rsplit(".", 1)[1], m)
    sys.modules["homeassistant.components.energy"] = energy_mod; sys.modules["homeassistant.components.energy.data"] = data_mod
    if not hasattr(hass.states, "async_all"):
        hass.states.async_all = lambda dom=None: [s for e, s in hass.states._s.items() if dom is None or e.startswith(dom + ".")]  # noqa: SLF001
    try:
        res = await D.async_discover(hass, {"load_meter": "sensor.bms_cfg_meter", "nested": {"x": ["sensor.soc"]}}, [])
    finally:
        for k, v in saved.items():
            if v is None: sys.modules.pop(k, None)
            else: sys.modules[k] = v
        for a, v in old_attrs.items():
            if v is None:
                try: delattr(helpers, a)
                except AttributeError: pass
            else: setattr(helpers, a, v)
    names = {c["energy_eid"]: c for c in res["candidates"]}
    check("discover: pralka i wallbox; bez licznika sieci i encji z konfiguracji", set(names) == {"sensor.pralka_e", "sensor.ev_e"}, list(names))
    check("discover: wallbox z panelu Energia, nazwa użytkownika", names["sensor.ev_e"]["energy_dashboard"] and names["sensor.ev_e"]["name"] == "Wallbox"
          and names["sensor.ev_e"]["category"] == "ev", names.get("sensor.ev_e"))
    check("discover: pralka z mocą i pomieszczeniem", names["sensor.pralka_e"]["power_eid"] == "sensor.pralka_p" and names["sensor.pralka_e"]["room"] == "Łazienka",
          names.get("sensor.pralka_e"))
    check("discover: panel Energia wykryty", res["energy_dashboard"] is True)
    check("discover: wynik przechodzi przez sanitize_device", all(DV.sanitize_device({"name": c["name"], "category": c["category"],
          "energy_eid": c["energy_eid"], "power_eid": c["power_eid"]}) for c in res["candidates"]))

    print(f"DISCOVER PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
