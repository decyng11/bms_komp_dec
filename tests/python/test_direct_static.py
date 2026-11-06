REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
"""Warstwa trybu bezpośredniego: import wszystkich modułów, brak nieistniejących nazw, wczytanie WSZYSTKICH 30 definicji."""
import ast, asyncio, builtins, importlib, pathlib, sys
sys.path.insert(0, ".")
import direct_env; direct_env.install()
sys.path.insert(0, REPO + "")
PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1; print("FAIL:", name, extra)

ROOT = pathlib.Path(REPO + "/custom_components/bms_komp_dec/direct")
PKG = "custom_components.bms_komp_dec.direct"
mods = ["const", "common", "parser", "provider", "device", "coordinator", "entity", "discovery", "flow",
        "p_sensor", "p_number", "p_select", "p_switch", "p_time", "p_datetime", "p_button", "p_binary_sensor",
        "pysolarman", "pysolarman.umodbus.functions", "pysolarman.umodbus.client.tcp", "pysolarman.umodbus.client.serial.rtu"]
loaded = {}
for m in mods:
    try:
        loaded[m] = importlib.import_module(f"{PKG}.{m}")
        check(f"import {m}", True)
    except Exception as e:
        check(f"import {m}", False, repr(e))

# --- nazwy: każda użyta nazwa musi być gdzieś związana albo istnieć w globalach modułu / wbudowanych
def bound_names(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)): out.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): out.add(n.name)
        elif isinstance(n, ast.arg): out.add(n.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names: out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name: out.add(n.name)
        elif isinstance(n, ast.MatchAs) and n.name: out.add(n.name)
        elif isinstance(n, ast.MatchStar) and n.name: out.add(n.name)
    return out
for m, mod in loaded.items():
    path = ROOT / (m.replace(".", "/") + ".py")
    if not path.exists(): path = ROOT / m.replace(".", "/") / "__init__.py"
    tree = ast.parse(path.read_text())
    bound = bound_names(tree)
    undefined = sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                        and n.id not in bound and not hasattr(mod, n.id) and not hasattr(builtins, n.id)})
    check(f"nazwy {m}: brak niezdefiniowanych", not undefined, undefined)

# --- wszystkie definicje: wczytanie parsera dla różnych parametrów (mod / mppt / faza / pack)
from custom_components.bms_komp_dec.direct import const as C
from custom_components.bms_komp_dec.direct.parser import ParameterParser
files = sorted(p.name for p in (ROOT / "inverter_definitions").glob("*.yaml"))
check("30 plików definicji", len(files) == 30, len(files))
async def load_all():
    stats = {}
    for f in files:
        for mod, mppt, phase, pack in ((0, 4, 3, -1), (1, 2, 1, 1), (2, 12, 3, 4)):
            params = {C.PARAM_[C.CONF_MOD]: mod, C.PARAM_[C.CONF_MPPT]: mppt, C.PARAM_[C.CONF_PHASE]: phase, C.PARAM_[C.CONF_PACK]: pack}
            try:
                p = await ParameterParser().init(str(ROOT / "inverter_definitions") + "/", f, params)
                d = p.get_entity_descriptions()
                reqs = p.schedule_requests(0)
                stats.setdefault(f, []).append((len(d), len(reqs) if isinstance(reqs, list) else (1 if reqs else 0)))
            except Exception as e:
                check(f"definicja {f} mod={mod}", False, repr(e))
    return stats
stats = asyncio.run(load_all())
check("wszystkie definicje wczytane (3 zestawy parametrów)", len(stats) == 30 and all(len(v) == 3 for v in stats.values()), {k: len(v) for k, v in stats.items() if len(v) != 3})
check("każda definicja ma encje i zapytania", all(v[0][0] > 0 and v[0][1] > 0 for v in stats.values()), [k for k, v in stats.items() if not (v[0][0] > 0 and v[0][1] > 0)])
print(f"DIRECT-STATIC PASS={PASS} FAIL={FAIL}")
