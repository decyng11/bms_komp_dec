"""Atrapy modułów Home Assistant — tylko tyle, by uruchomić logikę integracji bez prawdziwego HA."""
import sys, types, asyncio
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
CLOCK = {"now": datetime(2026, 10, 28, 17, 0, 0, tzinfo=TZ)}   # środa
SUN = {"rise": None, "set": None}   # godziny lokalne (float); None -> brak danych słońca


def _get_astral_event_date(hass, event, date=None):
    h = SUN["rise"] if event == "sunrise" else SUN["set"]
    if h is None:
        return None
    base = datetime(date.year, date.month, date.day, tzinfo=TZ)
    return (base + timedelta(hours=h)).astimezone(timezone.utc)


class _Permissive(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        meta = type("EnumLikeMeta", (type,), {"__getattr__": lambda cls, n: n if not n.startswith("__") else (_ for _ in ()).throw(AttributeError(n))})
        cls = meta(name, (), {"__init__": lambda self, *a, **k: None})
        setattr(self, name, cls)
        return cls


def mod(name, **attrs):
    m = _Permissive(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    parent, _, child = name.rpartition(".")
    if parent:
        setattr(sys.modules[parent], child, m)
    return m


class HomeAssistantError(Exception):
    pass


class Unauthorized(Exception):
    def __init__(self, *a, **kw):
        super().__init__("unauthorized"); self.kw = kw


class Entity:
    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
    async def async_added_to_hass(self): pass
    def async_write_ha_state(self): pass
    def async_on_remove(self, fn): pass
    async def async_get_last_state(self): return None


class Store:
    saves = []
    def __init__(self, hass, version, key): self.key = key; self.func = None; self.delay_calls = 0
    async def async_load(self): return None
    def async_delay_save(self, func, delay=0):
        self.func = func; self.delay_calls += 1
    async def async_save(self, data): self.saved = data


class DataUpdateCoordinator:
    def __init__(self, hass, logger, config_entry=None, name=None, update_interval=None):
        self.hass = hass; self.data = None
    def __class_getitem__(cls, item): return cls
    def async_add_listener(self, cb): return lambda: None


class dt_util:
    @staticmethod
    def now(): return CLOCK["now"]
    @staticmethod
    def as_local(d): return d.astimezone(TZ) if d.tzinfo else d.replace(tzinfo=TZ)
    @staticmethod
    def as_utc(d): return d.astimezone(timezone.utc)
    @staticmethod
    def parse_datetime(s):
        try: return datetime.fromisoformat(str(s))
        except ValueError: return None


class _Resp:
    def __init__(self, **kw): self.__dict__.update(kw)


def _install_aiohttp_stub():
    try:
        import aiohttp  # noqa: F401
        return
    except ImportError:
        pass
    aio = types.ModuleType("aiohttp"); web = types.ModuleType("aiohttp.web")
    web.middleware = lambda f: f; web.Request = object; web.Response = _Resp
    aio.web = web
    sys.modules["aiohttp"] = aio; sys.modules["aiohttp.web"] = web


def install():
    _install_aiohttp_stub()
    for name in [
        "homeassistant", "homeassistant.core", "homeassistant.exceptions", "homeassistant.util",
        "homeassistant.helpers", "homeassistant.components", "homeassistant.const",
        "homeassistant.config_entries", "homeassistant.components.frontend", "homeassistant.components.http",
        "homeassistant.components.sensor", "homeassistant.components.binary_sensor",
        "homeassistant.components.button", "homeassistant.components.switch", "homeassistant.components.number",
        "homeassistant.components.time", "homeassistant.helpers.entity_registry", "homeassistant.helpers.storage",
        "homeassistant.helpers.event", "homeassistant.helpers.update_coordinator",
        "homeassistant.helpers.restore_state", "homeassistant.helpers.entity", "homeassistant.helpers.selector", "homeassistant.data_entry_flow",
        "homeassistant.helpers.sun", "homeassistant.helpers.config_validation",
    ]:
        mod(name)
    sys.modules["homeassistant.core"].SupportsResponse = type("SupportsResponse", (), {"OPTIONAL": 1, "ONLY": 2})
    sys.modules["homeassistant.exceptions"].HomeAssistantError = HomeAssistantError
    sys.modules["homeassistant.exceptions"].Unauthorized = Unauthorized
    sys.modules["homeassistant.util"].dt = dt_util
    sys.modules["homeassistant.helpers.storage"].Store = Store
    sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = DataUpdateCoordinator
    sys.modules["homeassistant.helpers.entity"].Entity = Entity
    sys.modules["homeassistant.helpers.config_validation"].config_entry_only_config_schema = lambda d: (lambda c: c)
    sys.modules["homeassistant.helpers"].config_validation = sys.modules["homeassistant.helpers.config_validation"]
    sys.modules["homeassistant.helpers.sun"].get_astral_event_date = _get_astral_event_date
    irm = types.ModuleType("homeassistant.helpers.issue_registry")
    irm.ISSUES = {}
    irm.IssueSeverity = types.SimpleNamespace(ERROR="error", WARNING="warning", CRITICAL="critical")
    def _create(hass, domain, issue_id, **kw): irm.ISSUES[(domain, issue_id)] = kw
    def _delete(hass, domain, issue_id): irm.ISSUES.pop((domain, issue_id), None)
    irm.async_create_issue = _create; irm.async_delete_issue = _delete
    sys.modules["homeassistant.helpers.issue_registry"] = irm
    sys.modules["homeassistant.helpers"].issue_registry = irm
    sys.modules["homeassistant.helpers.restore_state"].RestoreEntity = type("RestoreEntity", (Entity,), {})
    for dom in ("sensor", "binary_sensor", "button", "switch", "number", "time"):
        m = sys.modules[f"homeassistant.components.{dom}"]
        setattr(m, f"{dom.title().replace('_','')}Entity", type(f"{dom}Entity", (), {}))
    sys.modules["homeassistant.components.binary_sensor"].BinarySensorEntity = type("BinarySensorEntity", (), {})
    sys.modules["homeassistant.const"].EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
    sys.modules["homeassistant.helpers.entity_registry"].async_get = lambda hass: types.SimpleNamespace(
        async_get_entity_id=lambda d, dom, uid: None, entities={})


class State:
    def __init__(self, state, attributes=None):
        self.state = str(state); self.attributes = attributes or {}


class FakeServices:
    def __init__(self, hass): self.hass = hass; self.calls = []; self.ignore = set(); self.known = set(); self.handlers = {}
    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, dict(data)))
        eid = data.get("entity_id")
        if eid in self.ignore:
            return
        if (domain, service) == ("select", "select_option"): self.hass.states.set(eid, data["option"])
        elif (domain, service) == ("number", "set_value"):
            self.hass.states.set(eid, data["value"], self.hass.states.attrs_of(eid))
        elif (domain, service) == ("switch", "turn_off"): self.hass.states.set(eid, "off")
        elif (domain, service) == ("switch", "toggle"):
            self.hass.states.set(eid, "off" if self.hass.states.get(eid).state == "on" else "on")
        elif (domain, service) == ("time", "set_value"): self.hass.states.set(eid, data["time"])
    def has_service(self, d, s): return (d, s) in self.known or (d, s) in self.handlers
    def async_register(self, domain, name, handler, supports_response=None): self.handlers[(domain, name)] = (handler, supports_response)
    def async_remove(self, domain, name): self.handlers.pop((domain, name), None)


class FakeStates:
    def __init__(self): self._s = {}
    def get(self, eid): return self._s.get(eid)
    def set(self, eid, state, attrs=None):
        self._s[eid] = State(state, attrs if attrs is not None else (self._s[eid].attributes if eid in self._s else {}))
    def attrs_of(self, eid): return self._s[eid].attributes if eid in self._s else {}
    def async_all(self, domain=None):
        out = []
        for e, st in self._s.items():
            if domain is None or e.startswith(domain + "."):
                st.entity_id = e; out.append(st)
        return out
    def async_entity_ids(self, domain=None):
        return [e for e in self._s if domain is None or e.startswith(domain + ".")]


class FakeHass:
    def __init__(self):
        self.states = FakeStates(); self.services = FakeServices(self); self.data = {}
        self.tasks = []
    def async_create_task(self, coro):
        t = asyncio.ensure_future(coro); self.tasks.append(t); return t
    async def async_add_executor_job(self, fn, *a): return fn(*a)
