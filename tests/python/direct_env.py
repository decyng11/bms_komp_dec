"""Atrapy dodatkowych modułów HA/pip potrzebne do zaimportowania warstwy trybu bezpośredniego (bez prawdziwego HA)."""
import functools, re, sys, types
sys.path.insert(0, ".")
import stubs

_done = False


def _slugify(text, separator="_"):
    text = re.sub(r"[^a-z0-9]+", separator, str(text).lower())
    return text.strip(separator)


def install():
    global _done
    if _done:
        return
    stubs.install()
    M = stubs.mod
    # propcache / voluptuous: tylko to, czego używa kod
    pc = types.ModuleType("propcache"); pc.cached_property = functools.cached_property; sys.modules["propcache"] = pc
    vol = types.ModuleType("voluptuous")
    class _Marker:
        def __init__(self, key, default=None, description=None): self.key = key; self.default = default; self.description = description
        def __hash__(self): return hash(self.key)
        def __eq__(self, o): return self.key == (o.key if isinstance(o, _Marker) else o)
    vol.Required = lambda k, default=None, description=None: _Marker(k, default, description)
    vol.Optional = vol.Required
    vol.Schema = lambda d: d
    vol.All = lambda *a: a
    vol.Coerce = lambda t: t
    vol.Range = lambda **k: k
    vol.In = lambda x: x
    vol.Invalid = type("Invalid", (Exception,), {})
    sys.modules["voluptuous"] = vol
    core = sys.modules["homeassistant.core"]; core.callback = lambda f: f; core.split_entity_id = lambda e: e.split(".", 1)
    sys.modules["homeassistant.util"].slugify = _slugify
    dr = M("homeassistant.helpers.device_registry", CONNECTION_NETWORK_MAC="mac", DeviceInfo=dict, format_mac=lambda m: str(m).lower())
    M("homeassistant.helpers.entity_platform")
    M("homeassistant.helpers.singleton", singleton=lambda key: (lambda f: f))
    M("homeassistant.helpers.typing", UNDEFINED=object(), StateType=object, UndefinedType=object)
    M("homeassistant.helpers.config_validation", port=int, positive_float=float, positive_int=int,
      config_entry_only_config_schema=lambda d: (lambda c: c))
    sys.modules["homeassistant.helpers"].config_validation = sys.modules["homeassistant.helpers.config_validation"]
    M("homeassistant.data_entry_flow", section=lambda schema, opts=None: ("section", schema))
    M("homeassistant.components.network")
    M("homeassistant.const", EntityCategory=type("EC", (), {"CONFIG": "config", "DIAGNOSTIC": "diagnostic"}),
      STATE_UNKNOWN="unknown", CONF_FRIENDLY_NAME="friendly_name", MAJOR_VERSION=2026, MINOR_VERSION=10,
      EVENT_HOMEASSISTANT_STARTED="homeassistant_started")
    class CoordinatorEntity:
        def __class_getitem__(cls, item): return cls
        def __init__(self, coordinator, context=None): self.coordinator = coordinator
        @property
        def device_entry(self): return None
        @property
        def name(self): return getattr(self, "_attr_name", None)
        @property
        def has_entity_name(self): return True
        use_device_name = False
        def async_write_ha_state(self): self.written = getattr(self, "written", 0) + 1
    class DUC:
        def __class_getitem__(cls, item): return cls
        def __init__(self, hass, logger, config_entry=None, name=None, update_interval=None, always_update=True):
            self.hass = hass; self.config_entry = config_entry; self.data = None; self.last_update_success = True
            self.update_interval = update_interval          # jak w HA: przechodzi przez setter (u nas nadpisany w Coordinator)
        @property
        def update_interval(self): return self._update_interval
        @update_interval.setter
        def update_interval(self, v):
            self._update_interval = v
            self._update_interval_seconds = v.total_seconds() if v else None
        def async_add_listener(self, cb): return lambda: None
        async def async_shutdown(self): pass
        def _async_refresh_finished(self): pass
        async def _async_setup(self): pass
        async def async_config_entry_first_refresh(self):
            await self._async_setup(); self.data = await self._async_update_data()
    uc = sys.modules["homeassistant.helpers.update_coordinator"]
    uc.CoordinatorEntity = CoordinatorEntity; uc.DataUpdateCoordinator = DUC; uc.UpdateFailed = type("UpdateFailed", (Exception,), {})
    # klasy bazowe encji: zwykłe puste klasy (generowane przez _Permissive mają metaklasę, która przeszkadza w dziedziczeniu)
    for modname, names in {
        "homeassistant.components.sensor": ("SensorEntity", "RestoreSensor"),
        "homeassistant.components.number": ("NumberEntity",), "homeassistant.components.select": ("SelectEntity",),
        "homeassistant.components.switch": ("SwitchEntity",), "homeassistant.components.time": ("TimeEntity",),
        "homeassistant.components.datetime": ("DateTimeEntity",), "homeassistant.components.button": ("ButtonEntity",),
        "homeassistant.components.binary_sensor": ("BinarySensorEntity",),
    }.items():
        m = sys.modules.get(modname) or M(modname)
        for n in names:
            setattr(m, n, type(n, (), {}))
    sw = sys.modules["homeassistant.components.switch"]; sw.SwitchDeviceClass = type("SDC", (), {"SWITCH": "switch"})
    bs = sys.modules["homeassistant.components.binary_sensor"]; bs.BinarySensorDeviceClass = type("BDC", (), {"CONNECTIVITY": "connectivity"})
    _done = True
