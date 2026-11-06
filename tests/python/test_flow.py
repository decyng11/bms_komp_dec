REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
import sys, types, asyncio, importlib
sys.path.insert(0, "."); import stubs; stubs.install()
# voluptuous + selector + ConfigFlow stuby
class Marker:
    def __init__(self, key, default=None, description=None): self.key=key; self.default=default; self.description=description
vol = types.ModuleType("voluptuous"); vol.Optional = lambda k, default=None, description=None: Marker(k, default, description); vol.Schema = lambda d: d
sys.modules["voluptuous"] = vol
class CF:
    context = {"entry_id": "e1"}
    def __init_subclass__(cls, domain=None, **kw): pass
    def __init__(self): pass
    def _async_current_entries(self): return []
    def async_show_form(self, **kw): return {"type": "form", **kw}
    def async_create_entry(self, **kw): return {"type": "create", **kw}
    def async_abort(self, **kw): return {"type": "abort", **kw}
class OF:
    def async_show_form(self, **kw): return {"type": "form", **kw}
    def async_create_entry(self, **kw): return {"type": "create", **kw}
sys.modules["homeassistant.config_entries"].ConfigFlow = CF
sys.modules["homeassistant.config_entries"].OptionsFlow = OF
sel = sys.modules["homeassistant.helpers.selector"]
sys.modules["homeassistant.helpers"].selector = sel
sys.path.insert(0, REPO + "")
cf = importlib.import_module("custom_components.bms_komp_dec.config_flow")
hass = stubs.FakeHass()
for eid in ("sensor.inverter_battery", "sensor.inverter_pv_power", "sensor.inverter_battery_power"): hass.states.set(eid, 1)
flow = cf.BmsConfigFlow(); flow.hass = hass
form = asyncio.run(flow.async_step_bms())
keys = list(form["data_schema"].keys())
no_empty_default = all(not (isinstance(k.default, str) and k.default == "") for k in keys)
print("pola formularza:", len(keys), "| puste default:", not no_empty_default)
assert no_empty_default and len(keys) > 20
sugg = {k.key: k.description for k in keys if k.description}
assert sugg["soc"]["suggested_value"] == "sensor.inverter_battery", sugg.get("soc")
res = asyncio.run(flow.async_step_bms({"soc": "sensor.inverter_battery", "pv_power": ""}))
assert res["type"] == "create" and res["data"] == {"soc": "sensor.inverter_battery"}, res
print("config_flow OK")

# ---- opcje i rekonfiguracja
class Entry:
    entry_id = "e1"; data = {"soc": "sensor.a", "battery_capacity_kwh": 12}; options = {}
entry = Entry()
class Reg:
    def __init__(self): self.reloaded = []
    def async_get_entry(self, i): return entry
    def async_update_entry(self, e, data=None, options=None):
        if data is not None: e.data = data
        if options is not None: e.options = options
    async def async_reload(self, i): self.reloaded.append(i)
hass.config_entries = Reg()
of = cf.BmsConfigFlow.async_get_options_flow(entry)
of.hass = hass
form = asyncio.run(of.async_step_init())
sg = {k.key: k.description for k in form["data_schema"].keys() if k.description}
assert sg["soc"]["suggested_value"] == "sensor.a", sg.get("soc")
cap = [k for k in form["data_schema"].keys() if k.key == "battery_capacity_kwh"][0]
assert cap.default == 12, cap.default
res = asyncio.run(of.async_step_init({"soc": "sensor.b", "battery_capacity_kwh": 15, "pv_power": ""}))
assert res["type"] == "create" and res["data"] == {"soc": "sensor.b", "battery_capacity_kwh": 15}, res
entry.options = res["data"]
assert cf.entry_settings(entry) == res["data"]
rc = cf.BmsConfigFlow(); rc.hass = hass
form = asyncio.run(rc.async_step_reconfigure())
assert form["step_id"] == "reconfigure"
res = asyncio.run(rc.async_step_reconfigure({"soc": "sensor.c"}))
assert res["type"] == "abort" and res["reason"] == "reconfigure_successful" and entry.data == {"soc": "sensor.c"} and entry.options == {}, (res, entry.data)
print("options + reconfigure OK")

# ---- ponowne wykrywanie w opcjach
hass2 = stubs.FakeHass()
for eid in ("sensor.inverter_battery", "sensor.inverter_pv_power", "sensor.inverter_load_power", "sensor.inverter_grid_power", "sensor.inverter_battery_power", "select.inverter_work_mode"):
    hass2.states.set(eid, 1)
out = cf.apply_detection(hass2, {"soc": "sensor.zle", "auto_detect": True, "battery_capacity_kwh": 10})
assert out["soc"] == "sensor.inverter_battery" and out["work_mode"] == "select.inverter_work_mode" and "auto_detect" not in out, out
out = cf.apply_detection(hass2, {"soc": "sensor.zle", "auto_detect": False})
assert out == {"soc": "sensor.zle"}, out
print("apply_detection OK")
