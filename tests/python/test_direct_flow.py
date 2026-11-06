REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""Kreator: menu BMS/falownik, dodanie falownika (walidacja, duplikaty, zapis opcji), opcje falownika, wybór klasy opcji."""
import asyncio, importlib, sys, types
sys.path.insert(0, "."); import direct_env; direct_env.install()
import stubs
cfg = sys.modules["homeassistant.config_entries"]
class CF:
    context = {}
    entries = []
    def __init_subclass__(cls, domain=None, **kw): pass
    def __init__(self): pass
    def _async_current_entries(self): return list(CF.entries)
    def async_show_form(self, **kw): return {"type": "form", **kw}
    def async_show_menu(self, **kw): return {"type": "menu", **kw}
    def async_create_entry(self, **kw): return {"type": "create", **kw}
    def async_abort(self, **kw): return {"type": "abort", **kw}
    def add_suggested_values_to_schema(self, schema, suggested):
        for k in schema:
            if hasattr(k, "key") and suggested and k.key in suggested: k.description = {"suggested_value": suggested[k.key]}
        return schema
class OF(CF): pass
cfg.ConfigFlow = CF; cfg.OptionsFlow = OF
sys.modules["homeassistant.helpers"].selector = sys.modules["homeassistant.helpers.selector"]
sys.path.insert(0, REPO + "")
PKG = "custom_components.bms_komp_dec"
cf = importlib.import_module(PKG + ".config_flow")
disc = importlib.import_module(PKG + ".direct.discovery")
PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1; print("FAIL:", name, extra)
run = asyncio.run
class Entry:
    def __init__(self, title, data, options=None, eid="x"): self.title = title; self.data = data; self.options = options or {}; self.entry_id = eid
hass = stubs.FakeHass(); hass.config = types.SimpleNamespace(path=lambda p: "/nonexistent/" + p)
FOUND = []
async def fake_discover(h, address=None):
    async def gen():
        for f in FOUND: yield f
    return gen()
disc.discover = fake_discover
def new_flow():
    f = cf.BmsConfigFlow(); f.hass = hass; return f

# menu: brak wpisów → wybór; wpis BMS już jest → od razu falownik
CF.entries = []
r = run(new_flow().async_step_user())
check("pierwsze dodanie: menu z kreatorem i dwiema opcjami", r["type"] == "menu" and r["menu_options"] == ["wizard", "bms", "inverter"], r)
CF.entries = [Entry("BMS komp-dec", {"soc": "sensor.x"})]
r = run(new_flow().async_step_user())
check("BMS już jest: od razu formularz falownika", r["type"] == "form" and r["step_id"] == "inverter", r.get("type"))
r = run(new_flow().async_step_bms())
check("drugi BMS jest odrzucany (single_instance_allowed)", r["type"] == "abort" and r["reason"] == "single_instance_allowed", r)

# formularz: pola, podpowiedź adresu z wykrywania, domyślna nazwa
FOUND[:] = [{"ip": "192.168.1.50", "mac": "AA", "hostname": "x", "serial": 1}]
r = run(new_flow().async_step_inverter())
keys = {k.key: k for k in r["data_schema"]}
check("formularz falownika ma pola host/port/transport/profil/zapis/dodatkowe", {"name", "host", "port", "transport", "lookup_file", "allow_write", "additional_options"} <= set(keys), list(keys))
check("podpowiedź adresu z wykrywania UDP", keys["host"].description["suggested_value"] == "192.168.1.50", keys["host"].description)
check("domyślna nazwa", keys["name"].description["suggested_value"] == "Inverter", keys["name"].description)
check("zapis domyślnie wyłączony", keys["allow_write"].default is False, keys["allow_write"].default)

# zapis wpisu: do opcji trafiają tylko wartości inne niż domyślne; data niesie kind
r = run(new_flow().async_step_inverter({"name": "Dom", "host": "192.168.1.50", "port": 8899, "transport": "tcp", "lookup_file": "Auto", "allow_write": False, "additional_options": {"mod": 0, "mppt": 4}}))
check("utworzono wpis falownika", r["type"] == "create" and r["title"] == "Dom" and r["data"] == {"kind": "inverter"}, r)
check("opcje zawierają tylko różnice od domyślnych", r["options"] == {"host": "192.168.1.50"}, r.get("options"))
r = run(new_flow().async_step_inverter({"name": "Dom", "host": "192.168.1.50", "port": 1502, "transport": "modbus_tcp", "lookup_file": "deye_hybrid.yaml", "allow_write": True, "additional_options": {"mppt": 2, "mb_slave_id": 3}}))
check("opcje: port, transport, profil, zapis, dodatkowe", r["options"] == {"host": "192.168.1.50", "port": 1502, "transport": "modbus_tcp", "lookup_file": "deye_hybrid.yaml", "allow_write": True, "additional_options": {"mppt": 2, "mb_slave_id": 3}}, r.get("options"))

# duplikaty
CF.entries = [Entry("BMS komp-dec", {"soc": "sensor.x"}), Entry("Dom", {"kind": "inverter"}, {"host": "192.168.1.50"})]
r = run(new_flow().async_step_inverter({"name": "Inny", "host": "192.168.1.50", "additional_options": {}}))
check("ten sam adres drugi raz → already_configured_device", r["type"] == "form" and r["errors"] == {"base": "already_configured_device"}, r.get("errors"))
r = run(new_flow().async_step_inverter({"name": "Dom", "host": "192.168.1.51", "additional_options": {}}))
check("ta sama nazwa → name_in_use", r["type"] == "form" and r["errors"] == {"base": "name_in_use"}, r.get("errors"))
r = run(new_flow().async_step_inverter({"name": "Drugi", "host": "192.168.1.51", "additional_options": {}}))
check("drugi falownik z innym adresem i nazwą jest dodawany", r["type"] == "create" and r["title"] == "Drugi", r)
r = run(new_flow().async_step_inverter())
keys = {k.key: k for k in r["data_schema"]}
check("domyślna nazwa kolejnego falownika nie koliduje", keys["name"].description["suggested_value"] == "Inverter", keys["name"].description)
CF.entries = [Entry("Inverter", {"kind": "inverter"}, {"host": "1.1.1.1"})]
r = run(new_flow().async_step_inverter())
keys = {k.key: k for k in r["data_schema"]}
check("zajęta nazwa → „Inverter 2”", keys["name"].description["suggested_value"] == "Inverter 2", keys["name"].description)
FOUND[:] = [{"ip": "1.1.1.1", "mac": "AA", "hostname": "x", "serial": 1}]
r = run(new_flow().async_step_inverter())
keys = {k.key: k for k in r["data_schema"]}
check("adres już użyty nie jest podpowiadany", keys["host"].description.get("suggested_value") in (None, ""), keys["host"].description)
FOUND[:] = [{"ip": "1.1.1.1", "mac": "AA", "hostname": "x", "serial": 1}, {"ip": "1.1.1.2", "mac": "BB", "hostname": "y", "serial": 2}]
r = run(new_flow().async_step_inverter())
keys = {k.key: k for k in r["data_schema"]}
check("podpowiadany jest pierwszy NIEUŻYTY adres", keys["host"].description["suggested_value"] == "1.1.1.2", keys["host"].description)

# wybór klasy opcji
inv = Entry("Dom", {"kind": "inverter"}, {"host": "192.168.1.50", "allow_write": True})
bms = Entry("BMS komp-dec", {"soc": "sensor.x"})
check("opcje: falownik → InverterOptionsFlow", type(cf.BmsConfigFlow.async_get_options_flow(inv)).__name__ == "InverterOptionsFlow")
check("opcje: BMS → BmsOptionsFlow", type(cf.BmsConfigFlow.async_get_options_flow(bms)).__name__ == "BmsOptionsFlow")
of = cf.BmsConfigFlow.async_get_options_flow(inv); of.hass = hass
r = run(of.async_step_init())
keys = {k.key: k for k in r["data_schema"]}
check("opcje falownika: osobny step_id „inverter”", r["type"] == "form" and r["step_id"] == "inverter", r.get("step_id"))
check("opcje falownika: aktualne wartości jako podpowiedzi", keys["host"].description["suggested_value"] == "192.168.1.50" and keys["allow_write"].description["suggested_value"] is True, (keys["host"].description, keys["allow_write"].description))
r = run(of.async_step_inverter({"host": "192.168.1.60", "allow_write": False, "additional_options": {}}))
check("opcje falownika: zapis zmiany adresu i wyłączenie zapisu", r["type"] == "create" and r["data"] == {"host": "192.168.1.60"}, r)
print(f"DIRECT-FLOW PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
