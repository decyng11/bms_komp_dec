REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""Encje falownika dodanego bezpośrednio muszą być rozpoznawane przez planera jak encje ha-solarman:
nazwy z naszych profili → entity_id → collect_records (platforma „solarman”) → detect_solarman."""
import asyncio, importlib, pathlib, sys, types
sys.path.insert(0, "."); import direct_env; direct_env.install()
import stubs
sys.path.insert(0, REPO + "")
PKG = "custom_components.bms_komp_dec"
pr = importlib.import_module(PKG + ".presets")
fl = importlib.import_module(PKG + ".inverter_floor")
C = importlib.import_module(PKG + ".direct.const")
from custom_components.bms_komp_dec.direct.parser import ParameterParser
ROOT = pathlib.Path(REPO + "/custom_components/bms_komp_dec/direct/inverter_definitions")
PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1; print("FAIL:", name, extra)
slug = direct_env._slugify

class Ent:
    def __init__(self, eid, platform, entry_id, name, tk):
        self.entity_id = eid; self.platform = platform; self.config_entry_id = entry_id
        self.original_name = name; self.translation_key = tk; self.device_id = "dev-" + str(entry_id)
class Reg:
    def __init__(self, ents): self.entities = {e.entity_id: e for e in ents}
class Entry:
    def __init__(self, i, kind=None): self.entry_id = i; self.data = {"kind": kind} if kind else {}
class Cfg:
    def __init__(self, entries): self._e = entries
    def async_entries(self, domain): return self._e if domain == "bms_komp_dec" else []

async def descriptions(fname):
    params = {C.PARAM_[C.CONF_MOD]: 0, C.PARAM_[C.CONF_MPPT]: 4, C.PARAM_[C.CONF_PHASE]: 3, C.PARAM_[C.CONF_PACK]: 1}
    p = await ParameterParser().init(str(ROOT) + "/", fname, params)
    return p.get_entity_descriptions()

def run(fname, device_name="Inverter", with_bms=True):
    descs = asyncio.run(descriptions(fname))
    ents = [Ent(f"{d['platform']}.{slug(device_name)}_{slug(d['name'])}", "bms_komp_dec", "inv1", d["name"], d.get("translation_key") or slug(d["name"])) for d in descs]
    if with_bms:    # własne encje BMS (ta sama platforma, inny wpis) nie mogą być brane za falownik
        ents += [Ent("sensor.bms_battery", "bms_komp_dec", "bms1", "Battery", "battery"), Ent("sensor.bms_pv_power", "bms_komp_dec", "bms1", "PV Power", "pv_power")]
    ereg = Reg(ents)
    er = sys.modules["homeassistant.helpers.entity_registry"]; er.async_get = lambda hass: ereg
    hass = stubs.FakeHass(); hass.config_entries = Cfg([Entry("inv1", "inverter"), Entry("bms1")])
    return hass, ents

for f, brand in (("deye_hybrid.yaml", "deye_hybrid"), ("deye_p3.yaml", "deye_p3"), ("solis_hybrid.yaml", "solis_hybrid"), ("sofar_hybrid.yaml", "sofar_hybrid"), ("afore_hybrid.yaml", "afore_hybrid"), ("kstar_hybrid.yaml", "kstar_hybrid")):
    hass, ents = run(f)
    recs = pr.collect_records(hass)
    byid = {r["entity_id"]: r for r in recs}
    check(f"{f}: encje falownika mają platformę „solarman”", all(byid[e.entity_id]["platform"] == "solarman" for e in ents if e.config_entry_id == "inv1"))
    check(f"{f}: encje BMS zostają przy swojej platformie", byid["sensor.bms_battery"]["platform"] == "bms_komp_dec")
    r = pr.detect_solarman(recs)
    # odniesienie: te same encje zgłoszone natively jako ha-solarman (zachowanie planera sprzed trybu bezpośredniego)
    native = [dict(x, platform="solarman") if x["entity_id"].startswith(("sensor.inverter_", "number.inverter_", "select.inverter_", "switch.inverter_", "time.inverter_", "binary_sensor.inverter_", "button.inverter_", "datetime.inverter_")) else x for x in recs]
    rn = pr.detect_solarman(native)
    check(f"{f}: wynik planera identyczny jak dla ha-solarman", r == rn and r is not None, (r and r["brand"], rn and rn["brand"]))
    check(f"{f}: role SOC i PV znalezione", r is not None and r["entities"].get("soc", "").startswith("sensor.inverter_") and r["entities"].get("pv_power", "").startswith("sensor.inverter_"), r and r["entities"])
    if f == "deye_hybrid.yaml":
        e = r["entities"]
        check("deye hybrid: sterowanie (tryb pracy, prąd ładowania, TOU) znalezione", e.get("work_mode") == "select.inverter_work_mode" and e.get("charge_current") == "number.inverter_battery_max_charging_current" and e.get("tou_select") == "select.inverter_time_of_use", e)

# bez mapowania wpisów (np. brak config_entries) kolekcja nadal działa
hass, ents = run("deye_hybrid.yaml"); hass.config_entries = None
recs = pr.collect_records(hass)
check("brak config_entries nie wywala zbierania encji", len(recs) >= len(ents))

# próg odcięcia: prefiks wykrywany także dla platformy naszej integracji
hass, ents = run("deye_hybrid.yaml", device_name="Falownik Dom")
check("inverter_floor._prefix: platforma integracji", fl._prefix(hass) == "falownik_dom", fl._prefix(hass))

# sprzątanie starych encji BMS nie może kasować encji falownika dodanego bezpośrednio (ta sama platforma)
init = importlib.import_module(PKG)
UID = importlib.import_module(PKG + ".helpers").UID_PREFIX
class RegRm(Reg):
    def __init__(self, ents): super().__init__(ents); self.removed = []
    def async_remove(self, eid): self.removed.append(eid); self.entities.pop(eid)
inv_e = Ent("sensor.inverter_battery", "bms_komp_dec", "inv1", "Battery", "battery"); inv_e.unique_id = "inv1_battery"
bms_e = Ent("sensor.bms_soc", "bms_komp_dec", "bms1", "SOC", "soc"); bms_e.unique_id = UID + "soc"
old_e = Ent("sensor.bms_old", "bms_komp_dec", "bms1", "Old", "old"); old_e.unique_id = "staryformat123"
foreign = Ent("sensor.inne", "inna_platforma", "zzz", "X", "x"); foreign.unique_id = "abc"
rr = RegRm([inv_e, bms_e, old_e, foreign])
er = sys.modules["homeassistant.helpers.entity_registry"]; er.async_get = lambda hass: rr
init.er = er
hass = stubs.FakeHass(); hass.config_entries = Cfg([Entry("inv1", "inverter"), Entry("bms1")])
init._cleanup_legacy_entities(hass)
check("sprzątanie: usuwa tylko stare encje BMS", rr.removed == ["sensor.bms_old"], rr.removed)
check("sprzątanie: encje falownika bezpośredniego zostają", "sensor.inverter_battery" in rr.entities)
print(f"DIRECT-PRESETS PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
