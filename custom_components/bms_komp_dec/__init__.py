"""EMS komp-dec integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.util import dt as dt_util

from .automation import async_auto_apply, async_daily_suggest, async_enable_sets, async_undo_auto_apply, apply_times
from .const import DOMAIN, PLATFORMS, SCHEDULER_DEFAULTS, VERSION
from .coordinator import BmsCoordinator
from .direct import async_setup_inverter_entry, async_unload_inverter_entry, is_inverter_entry
from .health import health_check
from .helpers import UID_PREFIX, entry_settings, number_value, switch_on
from . import inbox
from . import notify_cfg as ncfg
from . import devices as devmod
from .runtime import SCHEDULE_RULES, BmsRuntime
from .scheduler import ScheduleOptimizer
from .tariff import make_profile, profile_from_config, set_profile

_LOGGER = logging.getLogger(__name__)
_FRONTEND_DIR = Path(__file__).parent / "frontend"
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)  # konfiguracja tylko z interfejsu
_JS_URL = f"/{DOMAIN}/bms-panel.js"
_VENDOR_FILES = ("chart.umd.min.js", "chartjs-adapter-date-fns.bundle.min.js")
# moduły karty ładowane na żądanie przez bms-panel.js (Diagnostyka, dodatki: plan 24 h / raport / kreator)
_MODULE_FILES = ("bms-diag.js", "bms-extras.js", "bms-devices.js")
_SERVICES = (
    "test_schedule", "suggest_schedule", "apply_schedule_times", "undo_auto_apply", "auto_apply_now",
    "watch_write", "watch_status", "watch_clear", "health_check", "monthly_report", "get_plan",
    "diag_store_get_all", "diag_store_set", "diag_store_delete",
    "notify_settings_get", "notify_settings_set", "notify_test", "inbox_action", "devices_get", "devices_set", "devices_discover", "insights_get", "self_test",
    "override_set", "override_clear", "analysis_get", "analysis_set", "control_test",
)
_SUGGEST_HOUR = 16   # RCE na jutro jest publikowane po południu — wcześniej propozycja bazowała na starych danych


# --------------------------------------------------------------- helpers
def _get_coordinator(hass: HomeAssistant) -> BmsCoordinator | None:
    for value in (hass.data.get(DOMAIN) or {}).values():
        if isinstance(value, BmsCoordinator):
            return value
    return None


def _get_runtime(hass: HomeAssistant) -> BmsRuntime | None:
    coordinator = _get_coordinator(hass)
    return getattr(coordinator, "runtime", None) if coordinator else None


def _get_optimizer(hass: HomeAssistant) -> ScheduleOptimizer | None:
    for key, value in (hass.data.get(DOMAIN) or {}).items():
        if isinstance(value, ScheduleOptimizer):
            return value
    return None


def _cleanup_legacy_entities(hass: HomeAssistant) -> None:
    ent_reg = er.async_get(hass)
    removed = 0
    # falowniki dodane bezpośrednio mają tę samą platformę (DOMAIN), ale ich encje nie należą do EMS — nie ruszać
    direct_ids = {e.entry_id for e in hass.config_entries.async_entries(DOMAIN) if is_inverter_entry(e)}
    for entity in list(ent_reg.entities.values()):
        if entity.platform != DOMAIN:
            continue
        if str(entity.unique_id).startswith(UID_PREFIX):
            continue
        if getattr(entity, "config_entry_id", None) in direct_ids:
            continue
        try:
            ent_reg.async_remove(entity.entity_id)
            removed += 1
        except Exception:  # noqa: BLE001
            pass
    if removed:
        _LOGGER.warning("EMS: usunięto %d starych encji", removed)


# --------------------------------------------------------------- frontend
async def _async_register_frontend(hass: HomeAssistant) -> None:
    flag = f"{DOMAIN}_frontend_registered"
    if hass.data.get(flag):
        return
    hass.data[flag] = True   # ustawiane od razu — blokuje podwójną rejestrację przy wyścigu async_setup/entry
    js_path = _FRONTEND_DIR / "bms-panel.js"
    try:
        mtime = int((await hass.async_add_executor_job(js_path.stat)).st_mtime)
    except Exception:  # noqa: BLE001
        _LOGGER.warning("EMS: brak pliku %s", js_path)
        mtime = 0
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_JS_URL, str(js_path), cache_headers=False)]
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("EMS: rejestracja %s nie powiodła się: %s", _JS_URL, err)
    for fname in _MODULE_FILES:
        mpath = _FRONTEND_DIR / fname
        try:
            if not await hass.async_add_executor_job(mpath.is_file):
                _LOGGER.warning("EMS: brak pliku modułu karty %s — odpowiednia zakładka nie będzie działać", fname)
                continue
            await hass.http.async_register_static_paths(
                [StaticPathConfig(f"/{DOMAIN}/{fname}", str(mpath), cache_headers=False)]
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS: rejestracja modułu %s nie powiodła się: %s", fname, err)
    # opcjonalne lokalne kopie Chart.js (frontend/vendor) — panel użyje ich zamiast CDN
    for fname in _VENDOR_FILES:
        vpath = _FRONTEND_DIR / "vendor" / fname
        try:
            if not await hass.async_add_executor_job(vpath.is_file):
                continue
            await hass.http.async_register_static_paths(
                [StaticPathConfig(f"/{DOMAIN}/vendor/{fname}", str(vpath), cache_headers=True)]
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: lokalny plik %s niedostępny: %s", fname, err)
    url = f"{_JS_URL}?v={VERSION}.{mtime}"
    add_extra_js_url(hass, url)
    if hass.is_running:
        await _async_ensure_lovelace_resource(hass, url)
    else:
        async def _on_started(_event) -> None:
            await _async_ensure_lovelace_resource(hass, url)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)


def _is_bms_card_url(url: Any) -> bool:
    """Czy adres wygląda na plik karty EMS (np. stara ręczna kopia /local/bms-panel-final.js)."""
    path = str(url or "").split("?")[0].lower()
    return "bms-panel" in path or "bms_panel" in path


async def _async_ensure_lovelace_resource(hass: HomeAssistant, url: str) -> None:
    """Rejestruje kartę jako zasób dashboardu (typ module), jeśli dashboardy są w trybie storage.

    Zasoby są ładowane PRZED renderem widoków, więc karta nie trafia na moment, gdy
    'bms-panel-card' jeszcze nie jest zdefiniowany (losowy 'Błąd konfiguracji' po starcie).
    W trybie YAML lub przy innej wersji HA zostaje add_extra_js_url.

    Adres zasobu niesie numer wersji — tylko dzięki temu przeglądarka, aplikacja i ewentualny proxy (np. Cloudflare)
    nie podają starej kopii pliku. Dlatego nieudana aktualizacja i drugi, stary egzemplarz karty są zgłaszane
    jako OSTRZEŻENIA w logu (wcześniej błędy były wyciszone)."""
    try:
        ll = hass.data.get("lovelace")
        resources = getattr(ll, "resources", None)
        if resources is None and isinstance(ll, dict):
            resources = ll.get("resources")
        if resources is None or not hasattr(resources, "async_create_item"):
            _LOGGER.info("EMS: zasoby dashboardu nie są w trybie storage (YAML?) — karta ładuje się przez add_extra_js_url; "
                         "jeśli zasób dodałeś ręcznie, ustaw w nim adres %s", url)
            return
        if not getattr(resources, "loaded", True):
            await resources.async_load()
            resources.loaded = True
        items = [it for it in resources.async_items() if isinstance(it, dict)]
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("EMS: nie udało się odczytać zasobów dashboardu: %s", err, exc_info=True)
        return

    ours = [it for it in items if str(it.get("url", "")).split("?")[0] == _JS_URL]
    # drugi, stary egzemplarz karty: kto załaduje się pierwszy, ten definiuje kartę, a reszta jest po cichu ignorowana
    for it in items:
        other = str(it.get("url", ""))
        if other.split("?")[0] != _JS_URL and _is_bms_card_url(other):
            _LOGGER.warning(
                "EMS: na liście zasobów dashboardu jest jeszcze jeden egzemplarz karty: %s. Jeśli to stary plik, może "
                "przesłaniać nową wersję (pierwszy załadowany wygrywa, kolejne są ignorowane). Usuń go: Ustawienia → "
                "Pulpity → ⋮ → Zasoby.", other)
    for dup in ours[1:]:
        _LOGGER.warning("EMS: zasób karty %s występuje na liście więcej niż raz — zostaw jeden wpis.", dup.get("url"))

    try:
        if ours:
            item = ours[0]
            old = item.get("url")
            if old != url:
                await resources.async_update_item(item["id"], {"res_type": "module", "url": url})
                _LOGGER.info("EMS: zaktualizowano zasób dashboardu %s → %s", old, url)
            return
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("EMS: dodano zasób dashboardu %s", url)
    except Exception as err:  # noqa: BLE001
        current = ours[0].get("url") if ours else "(brak wpisu)"
        _LOGGER.warning(
            "EMS: nie udało się ustawić zasobu dashboardu na %s (obecnie: %s): %s. Przeglądarka może dostawać starą kopię "
            "karty — ustaw adres ręcznie: Ustawienia → Pulpity → ⋮ → Zasoby.", url, current, err, exc_info=True)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    await _async_register_frontend(hass)
    return True


# ------------------------------------------------------------------ services
async def _require_admin(hass: HomeAssistant, call: ServiceCall) -> None:
    """Usługi z danymi Diagnostyki / kontroli zapisu: tylko administrator (automatyzacje i skrypty — bez użytkownika — przechodzą)."""
    uid = call.context.user_id
    if uid is None:
        return
    user = await hass.auth.async_get_user(uid)
    if user is None or not user.is_admin:
        raise Unauthorized(context=call.context, permission="admin")


def _year_month(year: Any, month: Any) -> tuple[int | None, int | None]:
    """Rok i miesiąc z wywołania usługi: oba albo żadne; poza 2000–2100 / 1–12 → czytelny błąd zamiast wyjątku z kalendarza."""
    if year in (None, "") and month in (None, ""):
        return None, None
    try:
        y, m = int(year), int(month)
    except (TypeError, ValueError) as err:
        raise HomeAssistantError("rok i miesiąc muszą być liczbami całkowitymi (podaj oba albo żadnego)") from err
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        raise HomeAssistantError("rok musi być z zakresu 2000–2100, a miesiąc 1–12")
    return y, m


def _as_bool(value: Any) -> bool | None:
    """None = nie podano; napisy „false”/„0”/„off”/„nie” to fałsz (samo bool(\"false\") dałoby prawdę)."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "off", "no", "nie", "n")
    return bool(value)


def _need_runtime(hass: HomeAssistant) -> BmsRuntime:
    rt = _get_runtime(hass)
    if rt is None:
        raise HomeAssistantError("EMS komp-dec nie jest jeszcze uruchomiony")
    return rt


def _register_services(hass: HomeAssistant) -> None:
    async def handle_test(call):
        runtime = _get_runtime(hass)
        if runtime is None:
            return {"error": "runtime not ready"}
        return await runtime.process_rules(dt_util.now(), dry_run=True)

    async def handle_suggest(call):
        opt = _get_optimizer(hass)
        if not opt:
            return {"error": "optimizer not ready"}
        return await opt.suggest()

    async def handle_apply(call):
        times = call.data.get("times") or {}
        applied, skipped = await apply_times(hass, times)
        runtime = _get_runtime(hass)
        enabled: list[str] = []
        if runtime and applied:
            runtime.log.add("schedule", f"Ręcznie zastosowano {applied} godzin(y) z propozycji", "ok")
            enabled = await async_enable_sets(runtime, hass, set(times))
        return {"applied": applied, "skipped": skipped, "enabled_sets": enabled}

    async def handle_undo(call):
        runtime = _get_runtime(hass)
        if runtime is None:
            return {"error": "runtime not ready"}
        return await async_undo_auto_apply(runtime, hass)

    async def handle_auto_now(call):
        runtime, opt = _get_runtime(hass), _get_optimizer(hass)
        if runtime is None or opt is None:
            return {"error": "not ready"}
        result = await opt.suggest()
        if result.get("error"):
            return {"error": result["error"]}
        return await async_auto_apply(runtime, hass, result, dry_run=_as_bool(call.data.get("dry_run")))

    # --- kontrola wartości po zapisie (zamiast sprawdzania tylko przy otwartej karcie)
    async def handle_watch_write(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        try:
            item = rt.watch.add(
                call.data.get("entity_id"), call.data.get("expected"), call.data.get("label"),
                call.data.get("tolerance"), call.data.get("previous"), call.data.get("source") or "karta")
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        return {"item": item}

    async def handle_watch_status(call):
        await _require_admin(hass, call)
        return {"items": _need_runtime(hass).watch.list()}

    async def handle_watch_clear(call):
        await _require_admin(hass, call)
        return {"cleared": _need_runtime(hass).watch.clear(call.data.get("id"))}

    async def handle_health(call):
        await _require_admin(hass, call)
        return health_check(_need_runtime(hass))

    async def handle_report(call):
        rt = _need_runtime(hass)
        year, month = _year_month(call.data.get("year"), call.data.get("month"))
        return rt.monthly_report(year, month)

    async def handle_plan(call):
        rt = _need_runtime(hass)
        plan = await rt.refresh_plan(force=bool(call.data.get("force")))
        return {"plan": plan}

    # --- magazyn Diagnostyki w HA (dziennik zmian, kopie, profile) — tylko administrator
    async def handle_diag_get_all(call):
        await _require_admin(hass, call)
        return {"data": _need_runtime(hass).diag_store.get_all()}

    async def handle_diag_set(call):
        await _require_admin(hass, call)
        try:
            return _need_runtime(hass).diag_store.set(str(call.data.get("key") or ""), call.data.get("value"))
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_diag_delete(call):
        await _require_admin(hass, call)
        return {"deleted": _need_runtime(hass).diag_store.delete(str(call.data.get("key") or ""))}

    # --- konfigurator powiadomień (Diagnostyka → Powiadomienia) — tylko administrator
    async def handle_notify_get(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        return {"settings": rt.monitor.notifier.cfg(), "catalog": ncfg.catalog_payload(), "cooldowns": list(ncfg.COOLDOWNS),
                "groups": list(ncfg.GROUPS), "notify_service": rt.cfg.get("notify_service") or None,
                "enabled": switch_on(hass, "notifications_enabled", True)}

    async def handle_notify_set(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        raw = call.data.get("settings")
        if not isinstance(raw, dict):
            raise HomeAssistantError("settings: oczekiwano obiektu z ustawieniami powiadomień")
        eff = ncfg.effective(raw)
        rt.state["notify_cfg"] = eff
        rt._save_state()  # noqa: SLF001
        on = sum(1 for k in eff["kinds"].values() if k.get("on"))
        rt.log.add("notify", f"Zmieniono ustawienia powiadomień (włączone: {on} z {len(eff['kinds'])})", "ok")
        return {"settings": eff}

    async def handle_inbox(call):
        rt = _need_runtime(hass)
        try:
            res = inbox.act(rt.state, str(call.data.get("action") or ""), ident=call.data.get("id"),
                            key=call.data.get("key"), proposed=call.data.get("proposed"))
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        act = call.data.get("action")
        if act == "reject":
            rt.log.add("schedule", f"Odrzucono propozycję {call.data.get('key')} → {call.data.get('proposed')}", "info")
        rt._save_state()  # noqa: SLF001
        return res

    async def handle_notify_test(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        svc = rt.cfg.get("notify_service") or None
        await rt.monitor.notifier.send("test", "✅ EMS: powiadomienie testowe",
                                       "Jeśli to widzisz na telefonie, powiadomienia działają.", key=f"test:{dt_util.now().timestamp()}",
                                       level="info", force=True)
        return {"notify_service": svc, "phone": bool(svc), "enabled": switch_on(hass, "notifications_enabled", True)}

    # --- urządzenia (zakładka „Urządzenia”): odczyt dla każdego, zapis tylko administrator
    async def handle_devices_get(call):
        rt = _need_runtime(hass)
        dm = rt.devices
        lf = getattr(rt.coordinator, "load_forecast", None)
        house = dict(getattr(lf, "days", {}) or {})
        out = {"categories": devmod.category_payload(), "groups": list(devmod.GROUPS), "drivers": list(devmod.DRIVERS),
               "devices": dm.devices, "live": dm.live(), "summary": dm.summary(house),
               "flex_plan": dm.flex_plan((rt.plan() or {}).get("curve")),
               "unknown": dm.unknown_load(getattr(lf, "profiles", {}) or {}, house) if lf else None,
               "forecast_split": ((rt.coordinator.data or {}).get("load_forecast") or {}).get("forecast_split"),
               "house_daily": {k: round(v, 2) for k, v in house.items()},
               "max_devices": devmod.MAX_DEVICES, "control": rt.dev_ctl.status()}
        if _as_bool(call.data.get("history")):
            out["history"] = dm.history()
        return out

    async def handle_devices_set(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        items = call.data.get("devices")
        if not isinstance(items, list):
            raise HomeAssistantError("devices: oczekiwano listy urządzeń")
        saved = rt.devices.set_devices(items)
        rt.devices.state.pop("split_cache", None)
        rt.log.add("devices", f"Zapisano listę urządzeń ({len(saved)})", "ok")
        dropped = len([x for x in items if isinstance(x, dict)]) - len(saved)
        return {"devices": saved, "dropped": max(0, dropped)}

    # --- oszczędności i trafność prognoz (zakładka „Zysk i log”): odczyt dla każdego
    async def handle_insights_get(call):
        rt = _need_runtime(hass)
        lf = getattr(rt.coordinator, "load_forecast", None)
        return {"savings": rt.insights.savings(), "accuracy": rt.insights.accuracy(lf),
                "pv_correction_on": switch_on(hass, "pv_forecast_correction", True),
                "wear_cost": round(float(rt.optimizer.wear_cost()), 4) if hasattr(rt.optimizer, "wear_cost") else 0.0}

    async def handle_self_test(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        from .selftest import run as selftest_run
        return await selftest_run(rt)

    async def handle_override_set(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        kind = str(call.data.get("kind") or "")
        now = dt_util.now()
        try:
            if call.data.get("start") or call.data.get("end"):
                st = dt_util.parse_datetime(str(call.data.get("start"))) if call.data.get("start") else now
                en = dt_util.parse_datetime(str(call.data.get("end")))
                if st is None or en is None:
                    raise ValueError("nieprawidłowy czas (oczekiwano RRRR-MM-DDTGG:MM)")
                st, en = dt_util.as_local(st).timestamp(), dt_util.as_local(en).timestamp()
            else:
                hours = float(call.data.get("hours") or 0)
                if hours <= 0:
                    raise ValueError("podaj liczbę godzin (hours) albo start i end")
                st, en = now.timestamp(), now.timestamp() + hours * 3600
            tgt = call.data.get("target")
            items = rt.override_add(kind, st, en, None if tgt in (None, "") else float(tgt))
        except (ValueError, TypeError) as err:
            raise HomeAssistantError(f"Nadpisanie: {err}") from err
        await rt.override_tick(now)
        return {"overrides": [dict(o, text=rt.override_text(o)) for o in items]}

    async def handle_override_clear(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        items = rt.override_remove(call.data.get("id") or None)
        await rt.override_tick(dt_util.now())
        return {"overrides": items}

    async def handle_analysis_get(call):
        rt = _need_runtime(hass)
        return rt.analysis_payload()

    async def handle_analysis_set(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        data = {k: call.data.get(k) for k in ("g11", "zone", "dyn_markup", "invest_pv", "invest_batt") if k in call.data}
        rt.analysis_set(data)
        return rt.analysis_payload()

    async def handle_control_test(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        from .ctltest import run as ctl_run
        return await ctl_run(rt)

    async def handle_devices_discover(call):
        await _require_admin(hass, call)
        rt = _need_runtime(hass)
        from .discover import async_discover
        return await async_discover(hass, dict(rt.cfg or {}), list(rt.devices.devices))

    for name, handler, resp in (
        ("devices_get", handle_devices_get, SupportsResponse.ONLY),
        ("devices_discover", handle_devices_discover, SupportsResponse.ONLY),
        ("insights_get", handle_insights_get, SupportsResponse.ONLY),
        ("self_test", handle_self_test, SupportsResponse.ONLY),
        ("override_set", handle_override_set, SupportsResponse.OPTIONAL),
        ("override_clear", handle_override_clear, SupportsResponse.OPTIONAL),
        ("analysis_get", handle_analysis_get, SupportsResponse.ONLY),
        ("analysis_set", handle_analysis_set, SupportsResponse.OPTIONAL),
        ("control_test", handle_control_test, SupportsResponse.OPTIONAL),
        ("devices_set", handle_devices_set, SupportsResponse.OPTIONAL),
        ("notify_settings_get", handle_notify_get, SupportsResponse.ONLY),
        ("notify_settings_set", handle_notify_set, SupportsResponse.OPTIONAL),
        ("notify_test", handle_notify_test, SupportsResponse.OPTIONAL),
        ("inbox_action", handle_inbox, SupportsResponse.OPTIONAL),
        ("test_schedule", handle_test, SupportsResponse.OPTIONAL),
        ("suggest_schedule", handle_suggest, SupportsResponse.ONLY),
        ("apply_schedule_times", handle_apply, SupportsResponse.OPTIONAL),
        ("undo_auto_apply", handle_undo, SupportsResponse.OPTIONAL),
        ("auto_apply_now", handle_auto_now, SupportsResponse.OPTIONAL),
        ("watch_write", handle_watch_write, SupportsResponse.OPTIONAL),
        ("watch_status", handle_watch_status, SupportsResponse.ONLY),
        ("watch_clear", handle_watch_clear, SupportsResponse.OPTIONAL),
        ("health_check", handle_health, SupportsResponse.ONLY),
        ("monthly_report", handle_report, SupportsResponse.ONLY),
        ("get_plan", handle_plan, SupportsResponse.ONLY),
        ("diag_store_get_all", handle_diag_get_all, SupportsResponse.ONLY),
        ("diag_store_set", handle_diag_set, SupportsResponse.OPTIONAL),
        ("diag_store_delete", handle_diag_delete, SupportsResponse.OPTIONAL),
    ):
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, supports_response=resp)


# ------------------------------------------------------------------ entry
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if is_inverter_entry(entry):                 # falownik dodany bezpośrednio (bez ha-solarman)
        return await async_setup_inverter_entry(hass, entry)
    _cleanup_legacy_entities(hass)

    coordinator = BmsCoordinator(hass, entry)
    await coordinator.load_forecast.async_load()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    merged_config = entry_settings(entry)
    for k, v in SCHEDULER_DEFAULTS.items():
        merged_config.setdefault(k, v)

    set_profile(profile_from_config(merged_config))      # okna szczytu taryfy (domyślnie G12w)
    optimizer = ScheduleOptimizer(hass, coordinator, merged_config)
    await optimizer.async_load()
    # taryfa dynamiczna (tryb „auto”/„dynamic”): okna szczytu z godzinowych cen zakupu, liczone osobno dla każdego dnia
    set_profile(make_profile(
        merged_config, prices_fn=optimizer.buy_hourly_for,
        eff_fn=lambda: min(1.0, max(0.5, number_value(hass, "cycle_efficiency", 90.0) / 100.0)),
        source=", ".join(optimizer._buy_entities()),  # noqa: SLF001
    ))
    hass.data[DOMAIN][f"{entry.entry_id}_optimizer"] = optimizer

    runtime = BmsRuntime(hass, coordinator, optimizer)
    await runtime.async_load()
    coordinator.runtime = runtime
    entry.async_on_unload(coordinator.async_add_listener(runtime.on_coordinator_update))
    entry.async_on_unload(runtime.async_shutdown)

    await _async_register_frontend(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def tick(now: datetime) -> None:
        await runtime.tick(now)

    entry.async_on_unload(async_track_time_change(hass, tick, second=[0, 30]))

    async def grid_limit_tick(now: datetime) -> None:
        try:
            await runtime.grid_limiter.tick(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS ochrona przyłącza: %s", err, exc_info=True)

    entry.async_on_unload(async_track_time_interval(hass, grid_limit_tick, timedelta(seconds=10)))

    _register_services(hass)

    async def _reload_on_change(hass_: HomeAssistant, changed: ConfigEntry) -> None:
        await hass_.config_entries.async_reload(changed.entry_id)

    entry.async_on_unload(entry.add_update_listener(_reload_on_change))

    async def _daily_suggest(_now: datetime) -> None:
        try:
            await async_daily_suggest(runtime, hass, optimizer)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS auto-suggest: %s", err, exc_info=True)

    entry.async_on_unload(
        async_track_time_change(hass, _daily_suggest, hour=_SUGGEST_HOUR, minute=0, second=0)
    )

    runtime.log.add("system", f"EMS komp-dec {VERSION} uruchomiony ({len(SCHEDULE_RULES)} reguł harmonogramu)")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if is_inverter_entry(entry):
        return await async_unload_inverter_entry(hass, entry)
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # wpis mógł się nie uruchomić (np. błąd przy starcie) — wtedy hass.data[DOMAIN] jeszcze nie istnieje
        store = hass.data.get(DOMAIN) or {}
        store.pop(entry.entry_id, None)
        store.pop(f"{entry.entry_id}_optimizer", None)
        set_profile(None)
        for svc in _SERVICES:
            hass.services.async_remove(DOMAIN, svc)
    return unloaded
