REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""Tłumaczenia kreatora: pliki w translations/, te same klucze w en i pl, każdy krok/pole/błąd użyty w kodzie ma etykietę."""
import importlib, json, pathlib, re, sys, types
sys.path.insert(0, "."); import direct_env; direct_env.install()
import stubs
cfg = sys.modules["homeassistant.config_entries"]
cfg.ConfigFlow = type("CF", (), {"__init_subclass__": classmethod(lambda cls, domain=None, **kw: None)}); cfg.OptionsFlow = type("OF", (), {})
sys.modules["homeassistant.helpers"].selector = sys.modules["homeassistant.helpers.selector"]
sys.path.insert(0, REPO + "")
ROOT = pathlib.Path(REPO + "/custom_components/bms_komp_dec")
PKG = "custom_components.bms_komp_dec"
cf = importlib.import_module(PKG + ".config_flow"); dflow = importlib.import_module(PKG + ".direct.flow")
PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1; print("FAIL:", name, extra)
def flat(o, pre=""):
    out = {}
    for k, v in o.items():
        out.update(flat(v, pre + k + ".") if isinstance(v, dict) else {pre + k: v})
    return out
tr = {l: json.load(open(ROOT / "translations" / f"{l}.json")) for l in ("en", "pl")}
check("brak starych plików tłumaczeń poza translations/", not [f for f in ("strings.json", "en.json", "pl.json") if (ROOT / f).exists()])
check("en i pl mają te same klucze", set(flat(tr["en"])) == set(flat(tr["pl"])), set(flat(tr["en"])) ^ set(flat(tr["pl"])))
check("brak pustych tekstów", all(isinstance(v, str) and v.strip() for l in tr.values() for v in flat(l).values()))
src = (ROOT / "config_flow.py").read_text()
steps = set(re.findall(r'step_id="(\w+)"', src)) | {"user"}
for l, t in tr.items():
    check(f"{l}: kroki kreatora użyte w kodzie mają tłumaczenia", {"user", "bms", "inverter", "reconfigure", "wizard", "wizard_inverter", "wizard_match", "wizard_wait"} <= set(t["config"]["step"]), set(t["config"]["step"]))
    check(f"{l}: kroki opcji (BMS „init”, falownik „inverter”)", {"init", "inverter"} <= set(t["options"]["step"]), set(t["options"]["step"]))
    check(f"{l}: menu ma kreator i obie opcje", set(t["config"]["step"]["user"]["menu_options"]) == {"wizard", "bms", "inverter"})
    check(f"{l}: kroki kreatora mają tłumaczenia", {"wizard", "wizard_inverter", "wizard_match", "wizard_wait"} <= set(t["config"]["step"]), set(t["config"]["step"]))
    check(f"{l}: wybór połączenia kreatora przetłumaczony", set(t["selector"]["wizard_connection"]["options"]) == {"direct", "solarman"})
    wm = t["config"]["step"]["wizard_match"]
    msch = cf.build_match_schema(dict(cf.DEFAULT_CONFIG)); msch = getattr(msch, "schema", msch)
    wm_fields = {k.key for k in msch if hasattr(k, "key")} - {"details"}
    det = [v for k, v in msch.items() if getattr(k, "key", None) == "details"][0][1]
    det_fields = {k.key for k in getattr(det, "schema", det)}
    check(f"{l}: kreator, dopasowanie: etykiety pól głównych", wm_fields <= set(wm["data"]), wm_fields - set(wm["data"]))
    check(f"{l}: kreator, dopasowanie: etykiety pól sekcji", det_fields <= set(wm["sections"]["details"]["data"]), det_fields - set(wm["sections"]["details"]["data"]))
    check(f"{l}: kreator, dopasowanie: opis ma {{summary}} i {{problems}}", "{summary}" in wm["description"] and "{problems}" in wm["description"])
    check(f"{l}: opis bez dosłownych \\n", "\\n" not in wm["description"])
    wi = t["config"]["step"]["wizard_inverter"]
    check(f"{l}: kreator, falownik: etykiety jak w kroku falownika", set(t["config"]["step"]["inverter"]["data"]) <= set(wi["data"]))
    for e in ("setup_failed", "core_missing", "entities_missing", "wrong_type"):
        check(f"{l}: błąd {e} ma tekst", e in t["config"]["error"] and e in t["options"]["error"])
    errs = set(re.findall(r'"base": "(\w+)"', src + (ROOT / "direct/flow.py").read_text())) | set(re.findall(r'errors\[[^\]]+\] = "(\w+)"', src)) | {"unknown", "cannot_connect", "invalid_host", "timeout_connect"}
    check(f"{l}: każdy błąd używany w kreatorze ma tekst (config i options)", errs <= set(t["config"]["error"]) and errs <= set(t["options"]["error"]), errs - set(t["config"]["error"]))
    check(f"{l}: opcje transportu przetłumaczone", set(t["selector"]["transport"]["options"]) == {"tcp", "modbus_tcp", "modbus_rtu"})
    # pola formularzy
    inv_keys = {k.key for k in dflow.configuration_schema() if hasattr(k, "key")}
    sec = [v for k, v in dflow.configuration_schema().items() if getattr(k, "key", None) == "additional_options"][0]
    sec_keys = {k.key for k in sec[1]}
    for step_name, block in (("config.step.inverter", t["config"]["step"]["inverter"]), ("options.step.inverter", t["options"]["step"]["inverter"])):
        data = set(block["data"]) | set(block.get("sections", {}).get("additional_options", {}).get("data", {}))
        want = (inv_keys | sec_keys | ({"name"} if step_name.startswith("config") else set())) - {"additional_options"}
        check(f"{l}: {step_name}: etykiety dla wszystkich pól", want <= data, want - data)
    check(f"{l}: sekcja dodatkowych opcji ma nazwę", t["config"]["step"]["inverter"]["sections"]["additional_options"]["name"])
    bms_fields = {k.key for k in cf.build_schema(dict(cf.DEFAULT_CONFIG), redetect=True) if hasattr(k, "key")}
    for blk, extra in ((t["config"]["step"]["bms"], set()), (t["config"]["step"]["reconfigure"], set()), (t["options"]["step"]["init"], set())):
        missing = bms_fields - set(blk["data"]) - {"auto_detect"} if blk is t["config"]["step"]["bms"] else bms_fields - set(blk["data"])
        check(f"{l}: pola planera BMS mają etykiety", not missing, missing)
print(f"TRANSLATIONS PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
