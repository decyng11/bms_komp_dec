"""Kreator „wszystko w jednym” (0.8.1): wybór połączenia → dodanie falownika → czekanie na encje → dopasowanie z walidacją →
wpis planera; fazy L1–L3; rozstrzyganie remisów 1-/3-fazowych; wyładowanie wpisu bez hass.data."""
import asyncio, importlib, sys, types
src = open("test_direct_presets.py").read()
exec(compile(src.split("for f, brand in")[0], "head", "exec"))        # Ent, Reg, run(), descriptions(), check(), pr, C, slug, stubs…
cfgmod = sys.modules["homeassistant.config_entries"]
cfgmod.SOURCE_IMPORT = "import"
class CF:
    context = {}
    entries = []
    def __init_subclass__(cls, domain=None, **kw): pass
    def __init__(self): pass
    def _async_current_entries(self): return list(CF.entries)
    def async_show_form(self, **kw): return {"type": "form", **kw}
    def async_show_menu(self, **kw): return {"type": "menu", **kw}
    def async_create_entry(self, **kw): return {"type": "create_entry", **kw}
    def async_abort(self, **kw): return {"type": "abort", **kw}
    def add_suggested_values_to_schema(self, schema, suggested):
        for k in schema:
            if hasattr(k, "key") and suggested and k.key in suggested: k.description = {"suggested_value": suggested[k.key]}
        return schema
class OF(CF): pass
cfgmod.ConfigFlow = CF; cfgmod.OptionsFlow = OF
sys.modules["homeassistant.helpers"].selector = sys.modules["homeassistant.helpers.selector"]
cf = importlib.import_module(PKG + ".config_flow")
disc = importlib.import_module(PKG + ".direct.discovery")
async def fake_discover(h, address=None):
    async def gen():
        yield {"ip": "192.168.1.50", "mac": "AA", "hostname": "x", "serial": 1}
    return gen()
disc.discover = fake_discover
cf.WIZARD_POLL = 0.005; cf.WIZARD_WAIT = 0.6; cf.WIZARD_ENTITIES_WAIT = 0.1; cf.WIZARD_DATA_WAIT = 0.1; cf.WIZARD_DATA_RETRY = 0.1
def arun(c): return asyncio.run(c)

PROFILE = "deye_p3.yaml"
DESCS = arun(descriptions(PROFILE))

class WEntry:
    """Wpis falownika: „załaduje się” po N odczytach stanu; wtedy pojawiają się jego encje."""
    def __init__(self, hass, title, options, load_after, final="loaded"):
        self.hass = hass; self.title = title; self.options = options; self.data = {"kind": "inverter"}; self.entry_id = "inv-new"
        self._reads = 0; self._load_after = load_after; self._final = final; self._registered = False
    @property
    def state(self):
        self._reads += 1
        if self._reads <= self._load_after: return types.SimpleNamespace(value="setup_retry")
        if self._final == "loaded": self._register()
        return types.SimpleNamespace(value=self._final)
    def _register(self):
        if self._registered: return
        self._registered = True
        for d in DESCS:
            eid = f"{d['platform']}.inverter_{slug(d['name'])}"
            ENV.ents.append(Ent(eid, "bms_komp_dec", self.entry_id, d["name"], d.get("translation_key") or slug(d["name"])))
            unit = d.get("uom") or d.get("unit_of_measurement")
            self.hass.states.set(eid, ENV.state_val, {"unit_of_measurement": unit} if unit else {})

class ENV:                       # stan „świata” między krokami
    ents = []
    created = []; removed = []
    load_after = 2; final = "loaded"; abort_reason = None; state_val = "0"

class CfgEntries:
    def __init__(self, hass): self.hass = hass; self.flow = self; self.items = {}
    def async_entries(self, domain=None): return list(self.items.values())
    def async_get_entry(self, eid): return self.items.get(eid)
    async def async_remove(self, eid): ENV.removed.append(eid); self.items.pop(eid, None); CF.entries = list(self.items.values())
    async def async_init(self, domain, context=None, data=None):
        ENV.created.append((domain, context, data))
        if ENV.abort_reason: return {"type": "abort", "reason": ENV.abort_reason}
        f = cf.BmsConfigFlow(); f.hass = self.hass
        res = await f.async_step_import(data)
        if res["type"] != "create_entry": return res
        e = WEntry(self.hass, res["title"], res["options"], ENV.load_after, ENV.final)
        self.items[e.entry_id] = e; CF.entries = list(self.items.values())
        return {"type": "create_entry", "result": e, **res}

def fresh(load_after=2, final="loaded", abort_reason=None, bms_entry=False, extra_states=None):
    ENV.state_val = "0"; ENV.ents = []; ENV.created = []; ENV.removed = []; ENV.load_after = load_after; ENV.final = final; ENV.abort_reason = abort_reason
    hass = stubs.FakeHass(); hass.config_entries = CfgEntries(hass)
    hass.config = types.SimpleNamespace(path=lambda p: "/nonexistent/" + p)
    ereg = types.SimpleNamespace(entities={})
    class Live:                                                    # rejestr widzi encje, które dodał kreator
        @property
        def entities(self): return {e.entity_id: e for e in ENV.ents}
    sys.modules["homeassistant.helpers.entity_registry"].async_get = lambda h: Live()
    CF.entries = []
    if bms_entry:
        b = types.SimpleNamespace(title="BMS komp-dec", data={"soc": "sensor.x"}, options={}, entry_id="bms1"); hass.config_entries.items["bms1"] = b; CF.entries = [b]
    for k, v in (extra_states or {}).items(): hass.states.set(k, v[0], v[1])
    return hass
def flow(hass):
    f = cf.BmsConfigFlow(); f.hass = hass; return f
INV_INPUT = {"name": "Inverter", "host": "192.168.1.50", "port": 8899, "transport": "tcp", "lookup_file": "auto", "allow_write": False,
             "additional_options": {"mod": 0, "mppt": 4, "phase": 3, "pack": 1}}
def keys(form):
    sch = getattr(form["data_schema"], "schema", form["data_schema"]); return {k.key: k for k in sch if hasattr(k, "key")}
def _all_keys(form):
    out = dict(keys(form))
    for k, v in (getattr(form["data_schema"], "schema", form["data_schema"])).items():
        if getattr(k, "key", None) == "details":
            sch = v[1]; out.update({kk.key: kk for kk in getattr(sch, "schema", sch) if hasattr(kk, "key")})
    return out
def suggested(form, key):
    k = _all_keys(form).get(key); return None if k is None else (getattr(k, "description", None) or {}).get("suggested_value")

# ---- 1. menu i pierwszy krok
hass = fresh(); f = flow(hass)
r = arun(f.async_step_user())
check("menu: kreator, planer i falownik", r["type"] == "menu" and r["menu_options"] == ["wizard", "bms", "inverter"], r)
r = arun(f.async_step_wizard())
check("krok 1: formularz wyboru połączenia", r["type"] == "form" and r["step_id"] == "wizard" and "connection" in keys(r), r)
hass = fresh(bms_entry=True)
r = arun(flow(hass).async_step_wizard())
check("kreator przy istniejącym planerze: odmowa", r["type"] == "abort" and r["reason"] == "single_instance_allowed", r)

# ---- 2. ścieżka bezpośrednia: falownik → czekanie → dopasowanie
hass = fresh(load_after=3)
f = flow(hass)
r = arun(f.async_step_wizard({"connection": "direct"}))
check("krok 2: formularz falownika (wizard_inverter) z podpowiedzią IP", r["type"] == "form" and r["step_id"] == "wizard_inverter" and suggested(r, "host") == "192.168.1.50", r.get("step_id"))
r = arun(f.async_step_wizard_inverter(dict(INV_INPUT)))
check("po dodaniu falownika kreator przechodzi do dopasowania", r["type"] == "form" and r["step_id"] == "wizard_match", (r["type"], r.get("step_id"), r.get("errors")))
check("falownik dodany jednym wpisem importu", len(ENV.created) == 1 and ENV.created[0][1] == {"source": "import"} and ENV.created[0][2]["options"]["host"] == "192.168.1.50", ENV.created)
check("zapis do falownika zostaje wyłączony", ENV.created[0][2]["options"].get("allow_write") in (None, False), ENV.created[0][2]["options"])
# podpowiedzi: trzy fazy, każda rola wskazuje istniejącą encję
for k in ("soc", "pv_power", "grid_power", "grid_voltage_l3", "grid_current_l3", "load_current_l2", "grid_power_l1"):
    v = suggested(r, k); check(f"dopasowanie podpowiada {k}", bool(v) and hass.states.get(v) is not None, v)
check("podpowiedź prądu sieci L1 to External CT1", suggested(r, "grid_current_l1") == "sensor.inverter_external_ct1_current", suggested(r, "grid_current_l1"))
check("podsumowanie mówi o 3 fazach", "fazy: 3" in r["description_placeholders"]["summary"], r["description_placeholders"])
missing_sugg = [k for k, kk in _all_keys(r).items() if suggested(r, k) and hass.states.get(suggested(r, k)) is None]
check("żadna podpowiedź nie wskazuje nieistniejącej encji", not missing_sugg, missing_sugg)
check("wspólny schemat zawiera sekcję szczegółów", "details" in keys(r))

# ---- 3. zatwierdzenie dopasowania
def match_input(form):
    top = {k: suggested(form, k) for k in keys(form) if k != "details" and suggested(form, k)}
    det_sch = [v for k, v in (getattr(form["data_schema"], "schema", form["data_schema"])).items() if getattr(k, "key", None) == "details"][0][1]
    det_keys = {k.key: k for k in getattr(det_sch, "schema", det_sch) if hasattr(k, "key")}
    det = {k: (getattr(kk, "description", None) or {}).get("suggested_value") for k, kk in det_keys.items() if (getattr(kk, "description", None) or {}).get("suggested_value")}
    return {**top, "battery_capacity_kwh": 10.0, "tariff_mode": "auto", "details": det}
inp = match_input(r)
res = arun(f.async_step_wizard_match(inp))
check("poprawne dopasowanie tworzy wpis planera", res["type"] == "create_entry" and res["title"] == "BMS komp-dec", {k: res.get(k) for k in ("type", "errors")})
d = res.get("data", {})
check("wpis ma główne encje i fazy L1–L3", d.get("soc") == "sensor.inverter_battery" and d.get("grid_voltage_l3") and d.get("load_power_l2"), d)
check("wpis ma ustawienia domyślne planera", d.get("max_charge_power_w") and d.get("tariff_peaks") and d.get("tariff_mode") == "auto" and d.get("battery_capacity_kwh") == 10.0, d)
check("w danych nie ma sekcji „details”", "details" not in d)

# ---- 4. walidacja dopasowania
def bad(patch_top=None, patch_det=None, remove=()):
    i = match_input(r); i = {**i, **(patch_top or {})}; i["details"] = {**i["details"], **(patch_det or {})}
    for k in remove: i.pop(k, None)
    return arun(flow(hass).async_step_wizard_match(i))
x = bad({"grid_power": "sensor.nie_ma_takiej"})
check("nieistniejąca encja: błąd entities_missing", x["type"] == "form" and x["errors"] == {"base": "entities_missing"} and "nie_ma_takiej" in x["description_placeholders"]["problems"], x.get("errors"))
x = bad(remove=("soc",))
check("brak głównej encji: core_missing", x["errors"] == {"base": "core_missing"} and "soc" in x["description_placeholders"]["problems"], x.get("errors"))
x = bad(patch_det={"grid_current_l1": "sensor.inverter_grid_l1_voltage"})
check("napięcie w polu prądu: wrong_type (jednostka V ≠ A)", x["errors"] == {"base": "wrong_type"} and "grid_current_l1" in x["description_placeholders"]["problems"], (x.get("errors"), x.get("description_placeholders")))
x = bad({"soc": "sensor.inverter_pv_power"})
check("moc w polu SOC: wrong_type (W ≠ %)", x["errors"] == {"base": "wrong_type"}, x.get("errors"))
x = bad(patch_det={"work_mode": "sensor.inverter_pv_power"})
check("czujnik w polu select: wrong_type (domena)", x["errors"] == {"base": "wrong_type"} and "oczekiwano select" in x["description_placeholders"]["problems"], x.get("description_placeholders"))
x = bad({"notify_service": "źle zapisane"})
check("zły numer usługi powiadomień nadal blokuje (validate_input)", x["type"] == "form" and x["errors"], x.get("errors"))
check("po błędzie formularz zachowuje wybór użytkownika", suggested(bad({"grid_power": "sensor.nie_ma_takiej"}), "grid_power") == "sensor.nie_ma_takiej")

# ---- 5. porażki dodawania falownika
hass = fresh(load_after=10**6)             # nigdy się nie ładuje
f = flow(hass); arun(f.async_step_wizard({"connection": "direct"}))
r2 = arun(f.async_step_wizard_inverter(dict(INV_INPUT)))
check("falownik się nie ładuje: formularz z błędem setup_failed", r2["type"] == "form" and r2["step_id"] == "wizard_inverter" and r2["errors"] == {"base": "setup_failed"}, r2.get("errors"))
check("nieudany wpis jest usuwany", ENV.removed == ["inv-new"] and not hass.config_entries.items, ENV.removed)
check("po porażce formularz ma wpisane dane użytkownika", suggested(r2, "host") == "192.168.1.50", suggested(r2, "host"))
hass = fresh(load_after=0, final="setup_error")
f = flow(hass); r2 = arun(f.async_step_wizard_inverter(dict(INV_INPUT)))
check("błąd ładowania (setup_error): od razu setup_failed", r2["errors"] == {"base": "setup_failed"} and ENV.removed == ["inv-new"], r2.get("errors"))
hass = fresh(abort_reason="already_configured_device")
r2 = arun(flow(hass).async_step_wizard_inverter(dict(INV_INPUT)))
check("odmowa importu: błąd przy formularzu, bez wpisu", r2["errors"] == {"base": "already_configured_device"}, r2.get("errors"))
hass = fresh(abort_reason="coś_dziwnego")
r2 = arun(flow(hass).async_step_wizard_inverter(dict(INV_INPUT)))
check("nieznany powód odmowy: błąd unknown", r2["errors"] == {"base": "unknown"}, r2.get("errors"))
# zduplikowany adres — jak w zwykłym formularzu
hass = fresh(); dup = types.SimpleNamespace(title="Inverter", data={"kind": "inverter"}, options={"host": "192.168.1.50"}, entry_id="old")
hass.config_entries.items["old"] = dup; CF.entries = [dup]
r2 = arun(flow(hass).async_step_wizard_inverter(dict(INV_INPUT)))
check("duplikat adresu: błąd formularza", r2["errors"].get("base") == "already_configured_device" and not ENV.created, r2.get("errors"))
# wyjątek przy usuwaniu nie przerywa kreatora
hass = fresh(load_after=10**6)
async def boom(eid): raise RuntimeError("x")
hass.config_entries.async_remove = boom
r2 = arun(flow(hass).async_step_wizard_inverter(dict(INV_INPUT)))
check("błąd usuwania wpisu nie wywala kreatora", r2["errors"] == {"base": "setup_failed"}, r2.get("errors"))

# ---- 6. ścieżka „mam ha-solarman”: bez dodawania falownika
hass = fresh()
for d_ in DESCS:
    eid = f"{d_['platform']}.inverter_{slug(d_['name'])}"; unit = d_.get("uom") or d_.get("unit_of_measurement")
    ENV.ents.append(Ent(eid, "solarman", "sm1", d_["name"], d_.get("translation_key") or slug(d_["name"]))); hass.states.set(eid, "0", {"unit_of_measurement": unit} if unit else {})
f = flow(hass); r3 = arun(f.async_step_wizard({"connection": "solarman"}))
check("ha-solarman: od razu dopasowanie, bez dodawania falownika", r3["type"] == "form" and r3["step_id"] == "wizard_match" and not ENV.created, (r3.get("step_id"), ENV.created))
check("ha-solarman: wykryte 3 fazy i brak podpowiedzi nieistniejących encji", "fazy: 3" in r3["description_placeholders"]["summary"] and not [k for k in _all_keys(r3) if suggested(r3, k) and hass.states.get(suggested(r3, k)) is None])
# bez żadnych encji: pusty formularz zamiast „nieznanych encji”, komunikat w podsumowaniu
hass = fresh(); r4 = arun(flow(hass).async_step_wizard({"connection": "solarman"}))
check("brak encji: żadnych podpowiedzi domyślnych (nic z „sensor.inverter_*”)", not [k for k in _all_keys(r4) if suggested(r4, k)], [(k, suggested(r4, k)) for k in _all_keys(r4) if suggested(r4, k)])
check("brak encji: podsumowanie to mówi", "nie znaleziono" in r4["description_placeholders"]["summary"], r4["description_placeholders"])
# zatwierdzenie pustego formularza → core_missing, nie zapis
x = arun(flow(hass).async_step_wizard_match({"battery_capacity_kwh": 10.0, "tariff_mode": "auto", "details": {}}))
check("pusty formularz nie tworzy wpisu", x["type"] == "form" and x["errors"] == {"base": "core_missing"}, x.get("errors"))
# kreator nie tworzy drugiego planera
hass = fresh(bms_entry=True)
check("dopasowanie przy istniejącym planerze: odmowa", arun(flow(hass).async_step_wizard_match())["type"] == "abort")

# ---- 7. wykrywanie faz i jednostek
def det(fname, with_units=True):
    d_ = arun(descriptions(fname)); ents = []; units = {}
    hs = stubs.FakeHass()
    for x_ in d_:
        eid = f"{x_['platform']}.inverter_{slug(x_['name'])}"; ents.append(Ent(eid, "bms_komp_dec", "inv1", x_["name"], x_.get("translation_key") or slug(x_["name"])))
        u = x_.get("uom") or x_.get("unit_of_measurement")
        hs.states.set(eid, "0", {"unit_of_measurement": u} if (u and with_units) else {})
    sys.modules["homeassistant.helpers.entity_registry"].async_get = lambda h: Reg(ents)
    hs.config_entries = Cfg([Entry("inv1", "inverter")])
    return pr.detect_solarman(pr.collect_records(hs))
for fname, label, phases in (("deye_p3.yaml", "deye_p3", 3), ("deye_hybrid.yaml", "deye_hybrid", 2)):
    r_ = det(fname)
    check(f"{fname}: definicja {label}", r_ and r_["brand"] == label, r_ and r_["brand"])
    check(f"{fname}: liczba faz {phases}", r_ and r_["phases"] == phases, r_ and r_.get("phases"))
r_ = det("deye_p3.yaml")
check("P3: komplet 18 ról fazowych", sum(1 for k in r_["entities"] if k.endswith(("_l1", "_l2", "_l3"))) == 18, sorted(k for k in r_["entities"] if k.endswith(("_l1", "_l2", "_l3"))))
check("P3: prąd sieci z External CT, prąd domu z Output", r_["entities"]["grid_current_l2"] == "sensor.inverter_external_ct2_current" and r_["entities"]["load_current_l3"] == "sensor.inverter_output_l3_current", r_["entities"])
check("P3: napięcie sieci L3 i moc domu L2", r_["entities"]["grid_voltage_l3"] == "sensor.inverter_grid_l3_voltage" and r_["entities"]["load_power_l2"] == "sensor.inverter_load_l2_power")
r_nu = det("deye_p3.yaml", with_units=False)
check("bez jednostek (brak stanów) wykrywanie nadal działa", r_nu and r_nu["phases"] == 3)
# encja o złej jednostce odpada z roli fazowej
recs = [{"entity_id": "sensor.x_grid_l1_current", "platform": "solarman", "translation_key": None, "name": "Grid L1 Current", "device_id": "d", "unit": "V"}]
check("moc/napięcie/prąd: zła jednostka odrzucona w wykrywaniu", pr.detect_phase_roles(recs) == {}, pr.detect_phase_roles(recs))
recs[0]["unit"] = "A"
check("właściwa jednostka przechodzi", pr.detect_phase_roles(recs) == {"grid_current_l1": "sensor.x_grid_l1_current"})
check("unit_ok: brak jednostki nie dyskwalifikuje", pr.unit_ok("grid_power_l2", None) and pr.unit_ok("grid_power_l2", "kW") and not pr.unit_ok("grid_power_l2", "V") and pr.unit_ok("soc", "V"))
check("phase_count", pr.phase_count({"grid_power_l2": "x", "soc": "y"}) == 2 and pr.phase_count({}) == 0)

# ---- 8. wyładowanie wpisu, który się nie uruchomił
init = importlib.import_module(PKG)
async def ok_unload(entry, platforms): return True
hass = stubs.FakeHass(); hass.config_entries = types.SimpleNamespace(async_unload_platforms=ok_unload)
entry = types.SimpleNamespace(entry_id="e1", data={}, title="Inverter")
hass.data = {}                                                        # brak hass.data[DOMAIN] — wpis nie zdążył się uruchomić
try:
    res = arun(init.async_unload_entry(hass, entry)); check("wyładowanie bez hass.data nie rzuca KeyError", res is True, res)
except KeyError as e:
    check("wyładowanie bez hass.data nie rzuca KeyError", False, repr(e))
hass.data = {"bms_komp_dec": {"e1": object(), "e1_optimizer": object(), "e2": object()}}
arun(init.async_unload_entry(hass, entry))
check("wyładowanie sprząta tylko własne dane wpisu", set(hass.data["bms_komp_dec"]) == {"e2"}, hass.data)

# ---- 9. zapasowe liczenie mocy z faz
coord_mod = importlib.import_module(PKG + ".coordinator")
C_ = object.__new__(coord_mod.BmsCoordinator)
vals = {"grid_power_l1": 100.0, "grid_power_l2": -40.0, "grid_power_l3": 15.5}
C_.get_float_opt = lambda k: vals.get(k)
check("suma mocy trzech faz", C_._phase_sum(("grid_power_l1", "grid_power_l2", "grid_power_l3")) == 75.5)
vals2 = {"grid_power_l1": 10.0}; C_.get_float_opt = lambda k: vals2.get(k)
check("suma przy jednej dostępnej fazie", C_._phase_sum(("grid_power_l1", "grid_power_l2", "grid_power_l3")) == 10.0)
C_.get_float_opt = lambda k: None
check("brak encji faz → None (zostaje stare liczenie V×I)", C_._phase_sum(("grid_power_l1", "grid_power_l2")) is None)

# ---- 10. falownik jeszcze nie odpowiada: ekran „wizard_wait”, bez drugiego wpisu
hass = fresh(load_after=1); ENV.state_val = "unavailable"
f = flow(hass)
r = arun(f.async_step_wizard_inverter(dict(INV_INPUT)))
check("falownik bez odczytów: kreator staje na ekranie oczekiwania", r["type"] == "form" and r["step_id"] == "wizard_wait" and not r.get("errors"), (r.get("step_id"), r.get("errors")))
check("wpis falownika zostaje (nie jest usuwany)", len(ENV.created) == 1 and not ENV.removed, (ENV.created, ENV.removed))
r = arun(f.async_step_wizard_wait({}))
check("nadal bez odczytów: ten sam ekran z błędem no_data", r["step_id"] == "wizard_wait" and r["errors"] == {"base": "no_data"}, (r.get("step_id"), r.get("errors")))
check("ponowna próba nie dodaje drugiego falownika", len(ENV.created) == 1, ENV.created)
for e_ in ENV.ents: hass.states.set(e_.entity_id, "5", dict(hass.states.get(e_.entity_id).attributes))
r = arun(f.async_step_wizard_wait({}))
check("odczyty pojawiły się: przejście do dopasowania", r["type"] == "form" and r["step_id"] == "wizard_match", (r.get("step_id"), r.get("errors")))
hass = fresh(load_after=1); ENV.state_val = "unknown"
r = arun(flow(hass).async_step_wizard_inverter(dict(INV_INPUT)))
check("stan „unknown” też nie liczy się jako odczyt", r["step_id"] == "wizard_wait", r.get("step_id"))
hass = fresh(load_after=1)
r = arun(flow(hass).async_step_wizard_inverter(dict(INV_INPUT)))
check("odczyty od razu: bez ekranu oczekiwania", r["step_id"] == "wizard_match", r.get("step_id"))

# ---- 11. pojemność baterii z falownika
def cap_hass(patch):
    hs = stubs.FakeHass(); ents = []
    for d_ in DESCS:
        eid = f"{d_['platform']}.inverter_{slug(d_['name'])}"; unit = d_.get("uom") or d_.get("unit_of_measurement")
        ents.append(Ent(eid, "bms_komp_dec", "inv1", d_["name"], d_.get("translation_key") or slug(d_["name"])))
        hs.states.set(eid, "0", {"unit_of_measurement": unit} if unit else {})
    for eid, v in patch.items(): hs.states.set(eid, v, dict(hs.states.get(eid).attributes))
    sys.modules["homeassistant.helpers.entity_registry"].async_get = lambda h: Reg(ents)
    hs.config_entries = Cfg([Entry("inv1", "inverter")])
    return hs
KWH, AH, VB = "sensor.inverter_battery_capacity", "number.inverter_battery_capacity", "sensor.inverter_battery_voltage"
check("profil ma obie encje „Battery Capacity” (kWh i Ah) i napięcie baterii", all(cap_hass({}).states.get(x) is not None for x in (KWH, AH, VB)), [x for x in (KWH, AH, VB) if cap_hass({}).states.get(x) is None])
check("pojemność z encji w kWh", pr.detect_battery_capacity(cap_hass({KWH: "12.56"})) == (12.56, "kwh"), pr.detect_battery_capacity(cap_hass({KWH: "12.56"})))
check("kWh ma pierwszeństwo przed Ah × V", pr.detect_battery_capacity(cap_hass({KWH: "12.56", AH: "100", VB: "400"})) == (12.56, "kwh"))
check("Ah × napięcie (przybliżenie, 1 miejsce po przecinku)", pr.detect_battery_capacity(cap_hass({AH: "245", VB: "51.2"})) == (12.5, "ah_v"), pr.detect_battery_capacity(cap_hass({AH: "245", VB: "51.2"})))
check("Ah × napięcie dla baterii HV", pr.detect_battery_capacity(cap_hass({AH: "50", VB: "256"})) == (12.8, "ah_v"), pr.detect_battery_capacity(cap_hass({AH: "50", VB: "256"})))
check("wartość poza 1–100 kWh odrzucona", pr.detect_battery_capacity(cap_hass({KWH: "250"})) is None and pr.detect_battery_capacity(cap_hass({KWH: "0.2"})) is None)
check("Ah × V poza 1–100 kWh odrzucone", pr.detect_battery_capacity(cap_hass({AH: "5", VB: "12"})) is None and pr.detect_battery_capacity(cap_hass({AH: "3000", VB: "400"})) is None)
check("Ah bez napięcia baterii → brak wyniku", pr.detect_battery_capacity(cap_hass({AH: "245", VB: "unavailable"})) is None)
check("niedostępna encja nie daje pojemności", pr.detect_battery_capacity(cap_hass({KWH: "unavailable"})) is None)
check("brak encji pojemności → None", pr.detect_battery_capacity(stubs.FakeHass()) is None)
hass = cap_hass({KWH: "12.56"})
for e_ in list(sys.modules["homeassistant.helpers.entity_registry"].async_get(hass).entities.values()): pass
hass.config_entries = CfgEntries(hass); ENV.ents = []
for d_ in DESCS:
    eid = f"{d_['platform']}.inverter_{slug(d_['name'])}"; ENV.ents.append(Ent(eid, "solarman", "sm1", d_["name"], d_.get("translation_key") or slug(d_["name"])))
class Live2:
    @property
    def entities(self): return {e.entity_id: e for e in ENV.ents}
sys.modules["homeassistant.helpers.entity_registry"].async_get = lambda h: Live2()
CF.entries = []
r = arun(flow(hass).async_step_wizard({"connection": "solarman"}))
cap_def = keys(r)["battery_capacity_kwh"].default
check("kreator wpisuje pojemność z falownika jako wartość wstępną", cap_def == 12.56, cap_def)
check("podsumowanie mówi, skąd pojemność", "12.56 kWh (z falownika)" in r["description_placeholders"]["summary"], r["description_placeholders"]["summary"])
hass.states.set(KWH, "unavailable", {"unit_of_measurement": "kWh"}); hass.states.set(AH, "245", {"unit_of_measurement": "Ah"}); hass.states.set(VB, "51.2", {"unit_of_measurement": "V"})
r = arun(flow(hass).async_step_wizard({"connection": "solarman"}))
check("przybliżenie Ah × V jest wyraźnie oznaczone", "przybliżenie" in r["description_placeholders"]["summary"] and keys(r)["battery_capacity_kwh"].default == 12.5, r["description_placeholders"]["summary"])
hass.states.set(AH, "unavailable", {"unit_of_measurement": "Ah"})
r = arun(flow(hass).async_step_wizard({"connection": "solarman"}))
check("bez pojemności z falownika zostaje wartość domyślna", keys(r)["battery_capacity_kwh"].default == cf.DEFAULT_BATTERY_CAPACITY_KWH, keys(r)["battery_capacity_kwh"].default)
# pole pojemności przyjmuje setne części (12,56), nie tylko połówki
seen_nums = []
_orig_num = cf._num
cf._num = lambda mn, mx, step, unit, mode="box": (seen_nums.append((unit, step)), _orig_num(mn, mx, step, unit, mode))[1]
cf.build_match_schema(dict(cf.DEFAULT_CONFIG)); cf.build_schema(dict(cf.DEFAULT_CONFIG))
cf._num = _orig_num
kwh_steps = [st for u, st in seen_nums if u == "kWh"]
check("krok pola pojemności to 0,01 (kreator i formularz planera)", len(kwh_steps) == 2 and all(x == 0.01 for x in kwh_steps), kwh_steps)

# ---- 12. prognoza PV: Solcast, a gdy go nie ma — Forecast.Solar (po integracji i kluczu tłumaczenia, nie po nazwie)
def fc_hass(ents, states):
    hs = stubs.FakeHass()
    for eid, unit in states.items(): hs.states.set(eid, "5.2", {"unit_of_measurement": unit} if unit else {})
    sys.modules["homeassistant.helpers.entity_registry"].async_get = lambda h: Reg(ents)
    hs.config_entries = Cfg([]); return hs
fs = [Ent("sensor.estymowana_produkcja_energii_dzisiaj", "forecast_solar", "fs1", "Estimated energy production - today", "energy_production_today"),
      Ent("sensor.estymowana_produkcja_energii_jutro", "forecast_solar", "fs1", "Estimated energy production - tomorrow", "energy_production_tomorrow"),
      Ent("sensor.energy_production_today_remaining", "forecast_solar", "fs1", "Estimated energy production - remaining today", "energy_production_today_remaining")]
st = {"sensor.estymowana_produkcja_energii_dzisiaj": "kWh", "sensor.estymowana_produkcja_energii_jutro": "kWh", "sensor.energy_production_today_remaining": "kWh"}
check("Forecast.Solar rozpoznany po kluczu tłumaczenia (nazwy encji po polsku)", pr.detect_forecast_entities(fc_hass(fs, st)) == {"pv_forecast_today": "sensor.estymowana_produkcja_energii_dzisiaj", "pv_forecast_tomorrow": "sensor.estymowana_produkcja_energii_jutro"}, pr.detect_forecast_entities(fc_hass(fs, st)))
fs2 = [Ent("sensor.energy_production_today", "forecast_solar", "fs1", "x", None), Ent("sensor.energy_production_tomorrow", "forecast_solar", "fs1", "x", None),
       Ent("sensor.energy_production_today_remaining", "forecast_solar", "fs1", "x", None), Ent("sensor.energy_production_today_hour", "forecast_solar", "fs1", "x", None)]
st2_ = {e.entity_id: "kWh" for e in fs2}
check("Forecast.Solar po angielskich identyfikatorach, bez wariantów „remaining” i „hour”", pr.detect_forecast_entities(fc_hass(fs2, st2_)) == {"pv_forecast_today": "sensor.energy_production_today", "pv_forecast_tomorrow": "sensor.energy_production_tomorrow"}, pr.detect_forecast_entities(fc_hass(fs2, st2_)))
sol = {"sensor.solcast_pv_forecast_forecast_today": "kWh", "sensor.solcast_pv_forecast_forecast_tomorrow": "kWh", **st2_}
check("Solcast ma pierwszeństwo przed Forecast.Solar", pr.detect_forecast_entities(fc_hass(fs2, sol)) == {"pv_forecast_today": "sensor.solcast_pv_forecast_forecast_today", "pv_forecast_tomorrow": "sensor.solcast_pv_forecast_forecast_tomorrow"})
check("encja cudzej integracji o tej nazwie nie jest brana", pr.detect_forecast_entities(fc_hass([Ent("sensor.energy_production_today", "template", "t1", "x", None)], {"sensor.energy_production_today": "kWh"})) == {})
check("brak prognoz → pusty wynik", pr.detect_forecast_entities(fc_hass([], {})) == {})
check("encja Forecast.Solar w złej jednostce (W) odrzucona", pr.detect_forecast_entities(fc_hass(fs2, {e.entity_id: "W" for e in fs2})) == {})
# kreator: domyślne prognozy to Forecast.Solar, a nie nieistniejący Solcast
hs = fc_hass(fs2, st2_); hs.config_entries = CfgEntries(hs); CF.entries = []; ENV.ents = []
r = arun(flow(hs).async_step_wizard({"connection": "solarman"}))
check("kreator podpowiada Forecast.Solar zamiast nieistniejącego Solcasta", suggested(r, "pv_forecast_today") == "sensor.energy_production_today" and suggested(r, "pv_forecast_tomorrow") == "sensor.energy_production_tomorrow", (suggested(r, "pv_forecast_today"), suggested(r, "pv_forecast_tomorrow")))
# „Wykryj encje ponownie”: nieistniejąca prognoza zastąpiona, istniejąca zostaje
out = cf.apply_detection(hs, {"auto_detect": True, "pv_forecast_today": "sensor.nie_ma", "pv_forecast_tomorrow": "sensor.energy_production_tomorrow"})
check("ponowne wykrywanie: brakująca prognoza → Forecast.Solar", out["pv_forecast_today"] == "sensor.energy_production_today" and out["pv_forecast_tomorrow"] == "sensor.energy_production_tomorrow", out)
hs.states.set("sensor.moja_prognoza", "9", {"unit_of_measurement": "kWh"})
out = cf.apply_detection(hs, {"auto_detect": True, "pv_forecast_today": "sensor.moja_prognoza"})
check("ponowne wykrywanie nie nadpisuje istniejącej, własnej prognozy", out["pv_forecast_today"] == "sensor.moja_prognoza", out)

print(f"WIZARD PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
