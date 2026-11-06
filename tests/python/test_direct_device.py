REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""Urządzenie trybu bezpośredniego kontra symulator: odczyt przez WSZYSTKIE 30 profili, autodetekcja Deye,
zapis (blokada, zakres, odczyt kontrolny, odrzucenie przez falownik)."""
import asyncio, sys, types
from datetime import time as dtime
sys.path.insert(0, ".")
import direct_env; direct_env.install()
import stubs
sys.path.insert(0, REPO + "")
from logger_sim import LoggerSim
PKG = "custom_components.bms_komp_dec.direct"
import importlib
C = importlib.import_module(PKG + ".const")
prov = importlib.import_module(PKG + ".provider")
dev_mod = importlib.import_module(PKG + ".device")
ent = importlib.import_module(PKG + ".entity")
pn = importlib.import_module(PKG + ".p_number"); ps = importlib.import_module(PKG + ".p_select")
pt = importlib.import_module(PKG + ".p_time"); psw = importlib.import_module(PKG + ".p_switch")
pb = importlib.import_module(PKG + ".p_button")
from custom_components.bms_komp_dec.direct.parser import ParameterParser
HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError
PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1; print("FAIL:", name, extra)

DEYE_TYPE = {"deye_hybrid.yaml": 0x0003, "deye_string.yaml": 0x0002, "deye_micro.yaml": 0x0004, "deye_p3.yaml": 0x0005}
ROOT = REPO + "/custom_components/bms_komp_dec/direct/inverter_definitions/"
class Entry:
    def __init__(self, port, **opts):
        self.title = "Inverter"; self.entry_id = "e1"; self.data = {"kind": "inverter"}
        self.options = {"host": "127.0.0.1", "port": port, **opts}
class FakeHass(stubs.FakeHass):
    def __init__(self):
        super().__init__(); self.config = types.SimpleNamespace(path=lambda p: p, time_zone="Europe/Warsaw")

DISCOVERED = {"serial": None}
async def fake_discover(hass, address=None):
    async def gen():
        if DISCOVERED["serial"]:
            yield {"ip": address or "127.0.0.1", "mac": "AA:BB:CC:DD:EE:FF", "hostname": str(DISCOVERED["serial"]), "serial": DISCOVERED["serial"]}
    return gen()
prov.discover = fake_discover

def make_device(sim, **opts):
    hass = FakeHass()
    entry = Entry(sim.port, **opts)
    return dev_mod.Device(prov.ConfigurationProvider(hass, entry)), hass, entry

class Coord:
    def __init__(self, dev, hass, entry):
        self.device = dev; self.hass = hass; self.config_entry = entry; self.data = {}; self.last_update_success = True

async def read_profile_test():
    """Dla każdego z 30 profili: wartości proste (1 rejestr, bez lookup/walidacji) muszą wyjść = surowa × skala."""
    files = sorted(__import__("pathlib").Path(ROOT).glob("*.yaml"))
    total_checked = 0; problems = []
    for f in files:
        sim = await LoggerSim().start()
        if f.name in DEYE_TYPE: sim.regs[0] = DEYE_TYPE[f.name]
        dev, hass, entry = make_device(sim, lookup_file=f.name)
        try:
            await dev.setup()
            items = dev.profile.parser._items
            keycount = {}
            for it in items: keycount[it["key"]] = keycount.get(it["key"], 0) + 1
            usage = {}
            for it in items:
                for r in it.get("registers") or []:
                    usage[(C.get_code(it, "read", 3) if hasattr(C, "get_code") else 3, r)] = usage.get((3, r), 0) + 1
            simple = []
            for it in items:
                regs = it.get("registers")
                if (it.get("rule") in (1, 3) and regs and len(regs) == 1 and it.get("platform") in ("sensor", "number")
                        and not any(k in it for k in ("lookup", "validation", "range", "mask", "bit", "bitmask", "offset", "divide", "sensors", "attributes", "enabled_lookup", "name_lookup", "multiply", "uint"))
                        and usage.get((3, regs[0])) == 1 and keycount[it["key"]] == 1 and regs[0] != 0 and not it.get("update_interval", 0) > 60):
                    simple.append(it)
            for k, it in enumerate(simple):
                sim.regs[it["registers"][0]] = 1000 + k
            result = await dev.get(0)
            for k, it in enumerate(simple):
                exp = (1000 + k) * (it.get("scale") or 1)
                got = result.get(it["key"])
                total_checked += 1
                if got is None or abs(float(got[0]) - exp) > 1e-3 * max(1, abs(exp)):
                    problems.append((f.name, it["name"], it["registers"], exp, got))
        except Exception as e:
            problems.append((f.name, "wyjątek", repr(e)))
        finally:
            await dev.shutdown(); await sim.stop()
    return total_checked, problems

async def main():
    total, problems = await read_profile_test()
    check("odczyt: wartości proste ze wszystkich 30 profili zgodne z surową × skalą", not problems and total > 300, (total, problems[:6]))
    print(f"  (sprawdzono {total} wartości)")

    # --- Deye autodetekcja typu (rejestr 0x0000)
    cases = {0x0003: "deye_hybrid.yaml", 0x0300: "deye_hybrid.yaml", 0x0002: "deye_string.yaml", 0x0004: "deye_micro.yaml", 0x0005: "deye_p3.yaml", 0x0006: "deye_p3.yaml"}
    for dtype, fname in cases.items():
        sim = await LoggerSim().start(); sim.regs[0] = dtype
        dev, hass, entry = make_device(sim)           # lookup_file domyślnie „Auto”
        try:
            await dev.setup()
            check(f"autodetekcja: typ 0x{dtype:04X} → {fname}", dev.profile.parser is not None and dev.profile.parser.info.get("filename") == fname, dev.profile.parser and dev.profile.parser.info)
        except Exception as e:
            check(f"autodetekcja 0x{dtype:04X}", False, repr(e))
        finally:
            await dev.shutdown(); await sim.stop()
    sim = await LoggerSim().start(); sim.regs[0] = 0x7777
    dev, hass, entry = make_device(sim)
    try:
        await dev.setup(); ok = False
    except Exception as e:
        ok = True
    check("autodetekcja: nieznany typ → czytelny błąd, nie zgadywanie profilu", ok)
    await dev.shutdown(); await sim.stop()

    # --- numer seryjny: z wykrywania UDP albo z odpowiedzi
    DISCOVERED["serial"] = 2799999999
    sim = await LoggerSim(serial=2799999999).start(); sim.regs[0] = 3
    dev, hass, entry = make_device(sim, lookup_file="deye_hybrid.yaml")
    await dev.setup()
    check("serial z wykrywania UDP trafia do klienta", dev.modbus.serial == 2799999999 and dev.endpoint.mac == "AA:BB:CC:DD:EE:FF", (dev.modbus.serial, dev.endpoint.mac))
    await dev.shutdown(); await sim.stop(); DISCOVERED["serial"] = None

    # --- ZAPIS (Deye hybrydowy)
    async def write_env(allow):
        sim = await LoggerSim().start()
        sim.regs.update({0: 3, 0x00D2: 50, 0x00F4: 0, 0x00FA: 0})
        dev, hass, entry = make_device(sim, lookup_file="deye_hybrid.yaml", **({"allow_write": True} if allow else {}))
        await dev.setup()
        coord = Coord(dev, hass, entry); coord.data = await dev.get(0)
        d = {(x["platform"], x["name"]): x for x in dev.profile.parser.get_entity_descriptions()}
        return sim, dev, coord, d

    # blokada
    sim, dev, coord, d = await write_env(False)
    e = pn.SolarmanNumberEntity(coord, d[("number", "Battery Max Charging Current")]).init()
    try:
        await e.async_set_native_value(100); err = None
    except HomeAssistantError as ex:
        err = str(ex)
    check("zapis wyłączony → błąd z podpowiedzią, rejestr bez zmian", err and "wyłączony" in err and sim.regs[0x00D2] == 50, (err, sim.regs.get(0x00D2)))
    check("zapis wyłączony → żadna ramka zapisu nie wyszła do loggera", not [l for l in sim.log if l[0] in (5, 6, 15, 16)], sim.log)
    await dev.shutdown(); await sim.stop()

    # włączony
    sim, dev, coord, d = await write_env(True)
    e = pn.SolarmanNumberEntity(coord, d[("number", "Battery Max Charging Current")]).init()
    sim.log.clear()
    await e.async_set_native_value(100)
    check("zapis włączony: rejestr 0x00D2 = 100", sim.regs[0x00D2] == 100, sim.regs.get(0x00D2))
    check("zapis: odczyt kontrolny po zapisie", [l[0] for l in sim.log][-1] == 3 and any(l[0] in (6, 16) for l in sim.log), sim.log)
    check("zapis: stan encji uaktualniony", e._attr_native_value == 100, e._attr_native_value)
    sim.log.clear()
    await e.async_set_native_value(100)
    check("ta sama wartość → bez zapisu", not [l for l in sim.log if l[0] in (6, 16)], sim.log)
    # odrzucenie przez falownik
    sim.rejected.add(0x00D2); sim.regs[0x00D2] = 100
    try:
        await e.async_set_native_value(60); err = None
    except HomeAssistantError as ex:
        err = str(ex)
    check("falownik ignoruje zapis → błąd z odczytaną i oczekiwaną wartością", err and "nie przyjął" in err and "[100]" in err and "[60]" in err, err)
    check("po odrzuconym zapisie stan encji NIE jest nadpisany", e._attr_native_value == 100, e._attr_native_value)
    sim.rejected.clear()
    # select
    sel = ps.SolarmanSelectEntity(coord, d[("select", "Work Mode")]).init()
    await sel.async_select_option("Zero Export To Load")
    check("select Work Mode → rejestr 0x00F4 = 1", sim.regs[0x00F4] == 1, sim.regs.get(0x00F4))
    await sel.async_select_option("Export First")
    check("select Work Mode → rejestr 0x00F4 = 0", sim.regs[0x00F4] == 0, sim.regs.get(0x00F4))
    # time
    te = pt.SolarmanTimeEntity(coord, d[("time", "Program 1 Time")]).init()
    await te.async_set_value(dtime(6, 30))
    check("time Program 1 → rejestr 0x00FA = 630", sim.regs[0x00FA] == 630, sim.regs.get(0x00FA))
    # odczyt: wartości z symulatora w encjach
    sim.regs.update({184: 77, 0x00FA: 1745})
    coord.data = await dev.get(0)
    soc = [x for k, x in d.items() if k == ("sensor", "Battery")][0]
    check("odczyt SOC=77 z rejestru 184", coord.data[soc["key"]][0] == 77, coord.data.get(soc["key"]))
    await dev.shutdown(); await sim.stop()

    # --- utrata odpowiedzi: pierwszy odczyt po zerwaniu dostaje ponowienie
    sim = await LoggerSim().start(); sim.regs[0] = 3; sim.regs[184] = 55
    dev, hass, entry = make_device(sim, lookup_file="deye_hybrid.yaml")
    await dev.setup()
    sim.drop_next = 1
    try:
        res = await asyncio.wait_for(dev.get(0), 40)
        okk = res.get([x for x in dev.profile.parser.get_entity_descriptions("sensor") if x["name"] == "Battery"][0]["key"], (None,))[0] == 55
    except Exception as e:
        okk = repr(e)
    check("zgubiona odpowiedź → ponowienie i poprawny odczyt", okk is True, okk)
    await dev.shutdown(); await sim.stop()

    # --- 0.8.0: wartość czytana kodem 4 (rejestr wejściowy) → zapis BEZ odczytu kontrolnego (bez fałszywego „nie przyjął”)
    sim = await LoggerSim().start(); sim.regs.update({3078: 50})
    dev, hass, entry = make_device(sim, lookup_file="kstar_hybrid.yaml", allow_write=True)
    await dev.setup()
    coord = Coord(dev, hass, entry); coord.data = await dev.get(0)
    dd = {(x["platform"], x["name"]): x for x in dev.profile.parser.get_entity_descriptions()}
    desc = dd[("number", "Battery Discharging Power")]
    e = pn.SolarmanNumberEntity(coord, desc).init()
    sim.rejected.add(3078); sim.log.clear()
    rng = desc.get("range") or {}
    val = 30
    try:
        await e.async_set_native_value(val); err = None
    except HomeAssistantError as ex:
        err = str(ex)
    wr = [i for i, l in enumerate(sim.log) if l[0] in (6, 16)]
    check("kod 4: zapis wysłany", bool(wr), sim.log)
    check("kod 4: brak odczytu kontrolnego po zapisie i brak fałszywego błędu", err is None and wr and all(l[0] in (6, 16) for l in sim.log[wr[-1]:]), (err, sim.log))
    await dev.shutdown(); await sim.stop()

    # --- 0.8.0: niebezpieczne przyciski domyślnie wyłączone w rejestrze encji, zwykłe — włączone
    for prof_file, name, enabled in (("afore_hybrid.yaml", "Factory reset", False), ("afore_hybrid.yaml", "Clear records", False),
                                     ("afore_hybrid.yaml", "Restart", False), ("kstar_hybrid.yaml", "Restart", False),
                                     ("sofar_g3hyd.yaml", "Timed Set Program", True)):
        sim = await LoggerSim().start()
        dev, hass, entry = make_device(sim, lookup_file=prof_file)
        await dev.setup()
        coord = Coord(dev, hass, entry); coord.data = await dev.get(0)
        bd = [x for x in dev.profile.parser.get_entity_descriptions("button") if x["name"] == name]
        if not bd:
            check(f"przycisk {prof_file}/{name} istnieje w profilu", False); await dev.shutdown(); await sim.stop(); continue
        b = pb.SolarmanButtonEntity(coord, bd[0]).init()
        check(f"przycisk {prof_file}/{name}: domyślnie {'włączony' if enabled else 'WYŁĄCZONY'}", b._attr_entity_registry_enabled_default is enabled, b._attr_entity_registry_enabled_default)
        await dev.shutdown(); await sim.stop()
    print(f"DIRECT-DEVICE PASS={PASS} FAIL={FAIL}")
asyncio.run(main())
