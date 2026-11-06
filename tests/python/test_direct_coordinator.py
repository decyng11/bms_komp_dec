REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""Koordynator i wszystkie platformy trybu bezpośredniego na symulatorze loggera (profil Deye hybrydowy):
setup wpisu → pierwszy odczyt → encje wszystkich platform → odświeżenie → zapis przez encję → wyłączenie."""
import asyncio, importlib, sys, types
sys.path.insert(0, "."); import direct_env; direct_env.install()
import stubs
sys.path.insert(0, REPO + "")
from logger_sim import LoggerSim
PKG = "custom_components.bms_komp_dec.direct"
prov = importlib.import_module(PKG + ".provider")
HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError
PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1; print("FAIL:", name, extra)
async def no_discover(hass, address=None):
    async def gen():
        return
        yield
    return gen()
prov.discover = no_discover

class Entry:
    def __init__(self, port, **opts):
        self.title = "Falownik"; self.entry_id = "e1"; self.data = {"kind": "inverter"}
        self.options = {"host": "127.0.0.1", "port": port, "lookup_file": "deye_hybrid.yaml", **opts}
        self.runtime_data = None; self.unloads = []
    def async_on_unload(self, f): self.unloads.append(f)
    def add_update_listener(self, f): return lambda: None
class CE:
    def __init__(self): self.forwarded = None
    async def async_forward_entry_setups(self, entry, platforms): self.forwarded = list(platforms)
    async def async_unload_platforms(self, entry, platforms): return True
    async def async_reload(self, eid): pass

async def scenario(allow_write):
    sim = await LoggerSim().start()
    sim.regs.update({0: 3, 184: 64, 0x00D2: 50, 0x00F4: 0, 0x00FA: 0})
    hass = stubs.FakeHass(); hass.config = types.SimpleNamespace(path=lambda p: p, time_zone="Europe/Warsaw")
    hass.config_entries = CE()
    entry = Entry(sim.port, **({"allow_write": True} if allow_write else {}))
    direct = importlib.import_module(PKG)
    ok = await direct.async_setup_inverter_entry(hass, entry)
    return sim, hass, entry, ok

async def main():
    direct = importlib.import_module(PKG)
    sim, hass, entry, ok = await scenario(False)
    check("setup wpisu falownika zwraca True", ok is True)
    check("zgłoszono wszystkie platformy", hass.config_entries.forwarded == direct.DIRECT_PLATFORMS, hass.config_entries.forwarded)
    coord = entry.runtime_data
    check("koordynator ma dane po pierwszym odczycie", bool(coord.data))
    dinfo = coord.device.info.get("e1")
    check("opis urządzenia zbudowany (producent Deye)", dinfo and dinfo.get("manufacturer") == "Deye", dinfo)
    check("wyłączenie zarejestrowane (zamknięcie połączenia przy unload)", len(entry.unloads) >= 2, len(entry.unloads))

    # encje każdej platformy z prawdziwych funkcji setup
    counts = {}
    for pl in direct.DIRECT_PLATFORMS:
        m = importlib.import_module(f"{PKG}.p_{pl}")
        got = []
        await m.async_setup_entry(hass, entry, lambda ents, got=got: got.extend(list(ents)))
        counts[pl] = len(got)
    parser = coord.device.profile.parser
    expected = {pl: len(parser.get_entity_descriptions(pl)) for pl in direct.DIRECT_PLATFORMS}
    expected["sensor"] += 1          # „Update Interval” (diagnostyka współpracy z loggerem)
    expected["binary_sensor"] += 1   # „Connection” (stan połączenia z loggerem)
    check("liczba encji każdej platformy = opisy z profilu (+ Update Interval i Connection)", counts == expected, (counts, expected))
    check("platformy sterujące mają encje (number, select, switch, time)", all(counts[p] > 0 for p in ("number", "select", "switch", "time")), counts)

    # odświeżenie i wartość w encji
    sim.regs[184] = 71
    coord.data = await coord._async_update_data()
    check("odświeżenie przynosi nową wartość SOC", [v for k, v in coord.data.items() if k.endswith("battery_sensor") or k == "battery_sensor"][:1] in ([(71, None)], [(71, 1)]) or any(isinstance(v, tuple) and v[0] == 71 for v in coord.data.values()))

    # zapis przy wyłączonym zapisie: błąd, rejestr nietknięty
    nm = importlib.import_module(f"{PKG}.p_number")
    ents = []
    await nm.async_setup_entry(hass, entry, lambda e: ents.extend(list(e)))
    ent = [e for e in ents if e._attr_name == "Battery Max Charging Current"][0]
    try:
        await ent.async_set_native_value(90); err = None
    except HomeAssistantError as ex:
        err = str(ex)
    check("zapis przez encję zablokowany, gdy opcja wyłączona", err and sim.regs[0x00D2] == 50, (err, sim.regs.get(0x00D2)))
    await entry.unloads[0]() if asyncio.iscoroutinefunction(entry.unloads[0]) else None
    for u in entry.unloads:
        r = u()
        if asyncio.iscoroutine(r): await r
    await sim.stop()

    # ten sam scenariusz z zapisem włączonym
    sim, hass, entry, ok = await scenario(True)
    ents = []
    await nm.async_setup_entry(hass, entry, lambda e: ents.extend(list(e)))
    ent = [e for e in ents if e._attr_name == "Battery Max Charging Current"][0]
    await ent.async_set_native_value(90)
    check("zapis przez encję przy włączonej opcji", sim.regs[0x00D2] == 90, sim.regs.get(0x00D2))
    for u in entry.unloads:
        r = u()
        if asyncio.iscoroutine(r): await r
    await sim.stop()

    # logger nieosiągalny przy starcie: setup nie przechodzi cicho
    sim = await LoggerSim().start(); port = sim.port; await sim.stop()
    hass = stubs.FakeHass(); hass.config = types.SimpleNamespace(path=lambda p: p, time_zone="Europe/Warsaw"); hass.config_entries = CE()
    entry = Entry(port)
    try:
        await asyncio.wait_for(direct.async_setup_inverter_entry(hass, entry), 120); failed = False
    except Exception as e:
        failed = True
    check("logger niedostępny → setup zgłasza błąd (HA ponowi próbę), a nie udaje sukces", failed)
    for u in entry.unloads:
        r = u()
        if asyncio.iscoroutine(r): await r
    print(f"DIRECT-COORD PASS={PASS} FAIL={FAIL}")
asyncio.run(main())
sys.exit(1 if FAIL else 0)
