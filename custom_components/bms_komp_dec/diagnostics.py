"""Plik diagnostyczny (Ustawienia → Urządzenia i usługi → BMS komp-dec → ⋮ → Pobierz diagnostykę).

Konfiguracja, stan działania, plan, wynik sprawdzenia i ostatnie wpisy dziennika — do wysłania przy zgłaszaniu
problemu. Adres i numer seryjny falownika, usługa powiadomień, hasła i dane lokalizacji są ukryte."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

TO_REDACT = {
    "host", "inverter_host", "serial", "inverter_serial", "sn", "logger_serial", "password", "username", "token",
    "api_key", "notify_service", "latitude", "longitude", "mac", "email", "diag_password", "ip",
}
_STATE_KEYS = ("today_date", "low_soc_active", "storm_until", "vacation_since", "report_sent", "grid_outage",
               "price_reaction", "last_applied", "battery_sign_votes", "dev_ctl")


def _redact(obj: Any) -> Any:
    try:
        from homeassistant.components.diagnostics import async_redact_data
        return async_redact_data(obj, TO_REDACT)
    except Exception:  # noqa: BLE001 — bez komponentu diagnostics: własna, prosta wersja
        if isinstance(obj, dict):
            return {k: ("**REDACTED**" if k in TO_REDACT else _redact(v)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_redact(v) for v in obj]
        return obj


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as err:  # noqa: BLE001
        return {"error": str(err)} if default is None else default


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    out: dict[str, Any] = {
        "integration_version": VERSION,
        "entry": {"title": entry.title, "version": getattr(entry, "version", None), "domain": entry.domain,
                  "data": _redact(dict(entry.data)), "options": _redact(dict(entry.options))},
    }
    obj = (hass.data.get(DOMAIN) or {}).get(entry.entry_id)
    rt = getattr(obj, "runtime", None)
    if rt is None:
        out["runtime"] = None
        return out
    from .health import health_check
    lf = getattr(rt.coordinator, "load_forecast", None)
    plan = rt.plan() or {}
    out["runtime"] = {
        "state": _redact({k: rt.state.get(k) for k in _STATE_KEYS}),
        "notify_settings": _redact(_safe(lambda: rt.monitor.notifier.cfg())),
        "plan": {"generated_at": plan.get("generated_at"), "mode": plan.get("mode"), "error": plan.get("error"),
                 "assumptions": plan.get("assumptions"), "proposals": plan.get("proposals")},
        "health": _safe(lambda: health_check(rt)),
        "repairs": _safe(lambda: rt.repairs.status()),
        "log": _safe(lambda: rt.log.last(80), []),
        "devices": _safe(lambda: [{k: d.get(k) for k in ("id", "name", "category", "power_eid", "energy_eid", "switch_eid", "ctl_mode")}
                                  for d in rt.devices.devices], []),
        "device_control": _safe(lambda: rt.dev_ctl.status()),
        "savings": _safe(lambda: {k: v for k, v in rt.insights.savings().items() if k not in ("daily", "months")}),
        "accuracy": _safe(lambda: {k: v for k, v in rt.insights.accuracy(lf).items() if k != "days"}),
        "load_forecast": _safe(lambda: {k: (lf.as_dict() or {}).get(k) for k in ("tomorrow_forecast", "mape_14d", "forecast_bias", "history_days")}
                               if lf else None),
        "coordinator_data": _safe(lambda: {k: v for k, v in (rt.coordinator.data or {}).items() if k != "load_forecast"}),
    }
    return out
