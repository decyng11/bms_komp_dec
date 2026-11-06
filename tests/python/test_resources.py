"""Rejestracja zasobu karty w dashboardach: aktualizacja adresu przy nowej wersji, ostrzeżenia w logu
(nieudana aktualizacja, drugi/stary egzemplarz karty, duplikat), tryb YAML, rejestracja po starcie HA."""
import asyncio, logging, sys, types
sys.path.insert(0, ".")
from common import *   # noqa
import common

JS = pkg._JS_URL
NEW = f"{JS}?v=0.6.8.1700000000"

class Res:
    """Atrapa kolekcji zasobów Lovelace (tryb storage)."""
    def __init__(self, items=(), loaded=True, fail_update=False, fail_create=False, fail_load=False):
        self.items = [dict(i) for i in items]; self.loaded = loaded
        self.fail_update, self.fail_create, self.fail_load = fail_update, fail_create, fail_load
        self.calls = []
    async def async_load(self):
        self.calls.append("load")
        if self.fail_load: raise RuntimeError("load boom")
        self.loaded = True
    def async_items(self): return list(self.items)
    async def async_create_item(self, data):
        self.calls.append(("create", dict(data)))
        if self.fail_create: raise RuntimeError("create boom")
        self.items.append({"id": f"id{len(self.items)+1}", "type": data["res_type"], "url": data["url"]})
    async def async_update_item(self, item_id, data):
        self.calls.append(("update", item_id, dict(data)))
        if self.fail_update: raise RuntimeError("update boom")
        for it in self.items:
            if it["id"] == item_id: it["url"] = data["url"]; it["type"] = data["res_type"]

class Cap(logging.Handler):
    def __init__(self): super().__init__(); self.recs = []
    def emit(self, r): self.recs.append(r)

def run(items=(), *, ll="obj", **kw):
    hass = stubs.FakeHass()
    res = Res(items, **kw)
    if ll == "obj": hass.data["lovelace"] = types.SimpleNamespace(resources=res)
    elif ll == "dict": hass.data["lovelace"] = {"resources": res}
    elif ll == "yaml": hass.data["lovelace"] = types.SimpleNamespace(resources=types.SimpleNamespace(async_items=lambda: []))
    elif ll == "none": pass
    cap = Cap(); lg = logging.getLogger(pkg.__name__)
    old = lg.level; lg.setLevel(logging.DEBUG); lg.addHandler(cap)
    try:
        asyncio.run(pkg._async_ensure_lovelace_resource(hass, NEW))
    finally:
        lg.removeHandler(cap); lg.setLevel(old)
    return res, cap.recs

def lv(recs, level): return [r for r in recs if r.levelno == level]
def txt(r): return r.getMessage()

# --- A. brak wpisu → dodaje
res, recs = run([])
check("A: brak wpisu → utworzony zasób typu module z nowym adresem", ("create", {"res_type": "module", "url": NEW}) in res.calls and res.items[-1]["url"] == NEW, res.calls)
check("A: bez ostrzeżeń", not lv(recs, logging.WARNING) and not lv(recs, logging.ERROR), [txt(r) for r in recs])
check("A: info „dodano zasób”", any("dodano zasób" in txt(r) for r in lv(recs, logging.INFO)))

# --- B. stary adres (0.6.1) → aktualizacja do nowego
OLD = f"{JS}?v=0.6.1.1240428288"
res, recs = run([{"id": "r1", "type": "module", "url": OLD}])
check("B: stary adres ?v=0.6.1 → aktualizacja do nowego", res.items[0]["url"] == NEW and res.calls == [("update", "r1", {"res_type": "module", "url": NEW})], res.calls)
check("B: info zawiera stary i nowy adres", any(OLD in txt(r) and NEW in txt(r) for r in lv(recs, logging.INFO)), [txt(r) for r in recs])
check("B: brak ostrzeżeń", not lv(recs, logging.WARNING), [txt(r) for r in recs])

# --- C. adres już aktualny → nic nie robi, nic nie loguje na poziomie warning
res, recs = run([{"id": "r1", "type": "module", "url": NEW}])
check("C: aktualny adres → brak wywołań create/update", not [c for c in res.calls if isinstance(c, tuple)], res.calls)
check("C: aktualny adres → cisza w logu (warning)", not lv(recs, logging.WARNING))

# --- D. nieudana aktualizacja → OSTRZEŻENIE z wyjątkiem (nie debug), z obydwoma adresami
res, recs = run([{"id": "r1", "type": "module", "url": OLD}], fail_update=True)
w = lv(recs, logging.WARNING)
check("D: nieudana aktualizacja → warning", len(w) == 1, [txt(r) for r in recs])
check("D: warning zawiera nowy adres, obecny adres i przyczynę", w and NEW in txt(w[0]) and OLD in txt(w[0]) and "update boom" in txt(w[0]), [txt(r) for r in w])
check("D: warning ma dołączony ślad wyjątku (exc_info)", w and w[0].exc_info is not None)

# --- E. nieudane utworzenie → warning
res, recs = run([], fail_create=True)
w = lv(recs, logging.WARNING)
check("E: nieudane utworzenie → warning z przyczyną", len(w) == 1 and "create boom" in txt(w[0]) and "brak wpisu" in txt(w[0]), [txt(r) for r in recs])

# --- F. nieudane wczytanie kolekcji → warning, bez prób zapisu
res, recs = run([], loaded=False, fail_load=True)
w = lv(recs, logging.WARNING)
check("F: nieudane wczytanie zasobów → warning ze śladem wyjątku", len(w) == 1 and "load boom" in txt(w[0]) and w[0].exc_info is not None, [txt(r) for r in recs])
check("F: bez prób zapisu po nieudanym wczytaniu", not [c for c in res.calls if isinstance(c, tuple)], res.calls)

# --- G. niewczytana kolekcja → najpierw async_load
res, recs = run([{"id": "r1", "type": "module", "url": OLD}], loaded=False)
check("G: kolekcja niewczytana → async_load przed odczytem, potem aktualizacja", res.calls[0] == "load" and res.items[0]["url"] == NEW, res.calls)

# --- H. druga, stara kopia karty (/local/bms-panel-final.js) → warning o drugim egzemplarzu
STALE = "/local/bms-panel-final.js"
res, recs = run([{"id": "r1", "type": "module", "url": OLD}, {"id": "r2", "type": "module", "url": STALE}])
w = lv(recs, logging.WARNING)
check("H: druga kopia karty → dokładnie jedno ostrzeżenie", len(w) == 1 and STALE in txt(w[0]), [txt(r) for r in recs])
check("H: ostrzeżenie mówi, co zrobić (Zasoby) i że pierwszy wygrywa", w and "Zasoby" in txt(w[0]) and "pierwszy" in txt(w[0]))
check("H: stara kopia NIE jest ruszana automatycznie (nie usuwamy cudzych wpisów)", res.items[1]["url"] == STALE and len(res.items) == 2)
check("H: nasz wpis i tak jest zaktualizowany", res.items[0]["url"] == NEW)
for u in ("/local/bms-panel.js?v=3", "/local/community/bms_panel/card.js", "/local/BMS-Panel-final.js?v=2", "/hacsfiles/BMS-PANEL/x.js"):
    res, recs = run([{"id": "r1", "type": "module", "url": NEW}, {"id": "r2", "type": "module", "url": u}])
    check(f"H: {u} rozpoznany jako druga kopia karty", len(lv(recs, logging.WARNING)) == 1, [txt(r) for r in recs])
# cudze zasoby nie wywołują ostrzeżenia
res, recs = run([{"id": "r1", "type": "module", "url": NEW}, {"id": "r2", "type": "module", "url": "/hacsfiles/button-card/button-card.js"},
                 {"id": "r3", "type": "css", "url": "/local/theme.css"}])
check("H: obce karty (button-card, css) → brak ostrzeżeń", not lv(recs, logging.WARNING), [txt(r) for r in recs])

# --- I. duplikat NASZEGO zasobu → ostrzeżenie, aktualizacja pierwszego
res, recs = run([{"id": "r1", "type": "module", "url": OLD}, {"id": "r2", "type": "module", "url": f"{JS}?v=0.6.2.1"}])
w = lv(recs, logging.WARNING)
check("I: zasób karty dwa razy → warning o duplikacie", len(w) == 1 and "więcej niż raz" in txt(w[0]), [txt(r) for r in recs])
check("I: aktualizowany jest pierwszy wpis", res.items[0]["url"] == NEW)

# --- J. warianty dostępu do kolekcji i tryb YAML
res, recs = run([], ll="dict")
check("J: lovelace jako dict → zasób dodany", res.items and res.items[0]["url"] == NEW)
res, recs = run([], ll="yaml")
check("J: tryb YAML (brak async_create_item) → info, bez ostrzeżeń i bez wyjątku", not lv(recs, logging.WARNING) and any("YAML" in txt(r) for r in lv(recs, logging.INFO)), [txt(r) for r in recs])
res, recs = run([], ll="none")
check("J: brak lovelace w hass.data → info, bez wyjątku", not lv(recs, logging.WARNING), [txt(r) for r in recs])

# --- K. wyjątek w async_items (np. zmiana API HA) → warning, bez wyjątku na zewnątrz
class BadRes(Res):
    def async_items(self): raise KeyError("items")
hass = stubs.FakeHass(); hass.data["lovelace"] = types.SimpleNamespace(resources=BadRes([]))
cap = Cap(); lg = logging.getLogger(pkg.__name__); lg.addHandler(cap); lg.setLevel(logging.DEBUG)
try:
    asyncio.run(pkg._async_ensure_lovelace_resource(hass, NEW)); raised = False
except Exception as e:
    raised = e
lg.removeHandler(cap)
check("K: wyjątek przy odczycie listy → bez wyjątku na zewnątrz, warning", raised is False and len(lv(cap.recs, logging.WARNING)) == 1 and lv(cap.recs, logging.WARNING)[0].exc_info is not None, (raised, [txt(r) for r in cap.recs]))

# --- L. rejestracja frontendu: hass działa → od razu; hass startuje → po zdarzeniu STARTED
class Http:
    async def async_register_static_paths(self, cfgs): pass
class Bus:
    def __init__(self): self.once = []
    def async_listen_once(self, ev, cb): self.once.append((ev, cb))
def reg(is_running):
    hass = stubs.FakeHass(); hass.http = Http(); hass.bus = Bus(); hass.is_running = is_running
    res = Res([{"id": "r1", "type": "module", "url": OLD}]); hass.data["lovelace"] = types.SimpleNamespace(resources=res)
    extra = []
    saved = (pkg.add_extra_js_url, pkg.StaticPathConfig)
    pkg.add_extra_js_url = lambda h, u: extra.append(u)
    pkg.StaticPathConfig = lambda *a, **k: (a, k)
    try:
        asyncio.run(pkg._async_register_frontend(hass))
        return hass, res, extra
    finally:
        pkg.add_extra_js_url, pkg.StaticPathConfig = saved
hass, res, extra = reg(True)
check("L: HA działa → zasób zaktualizowany od razu do ?v=<VERSION>.<mtime>", res.items[0]["url"].startswith(f"{JS}?v={const.VERSION}."), res.items)
check("L: add_extra_js_url dostaje ten sam adres co zasób", extra == [res.items[0]["url"]], extra)
hass, res, extra = reg(False)
check("L: HA startuje → zasób jeszcze nietknięty, zdarzenie STARTED zarejestrowane", res.items[0]["url"] == OLD and len(hass.bus.once) == 1 and hass.bus.once[0][0] == "homeassistant_started", (res.items, hass.bus.once))
asyncio.run(hass.bus.once[0][1](None))
check("L: po zdarzeniu STARTED → zasób zaktualizowany", res.items[0]["url"] == extra[0] and extra[0].startswith(f"{JS}?v={const.VERSION}."), (res.items, extra))

print(f"RESOURCES PASS={common.PASS} FAIL={common.FAIL}")
