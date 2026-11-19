"""Plik diagnostyczny (Ustawienia → Urządzenia i usługi → EMS komp-dec → ⋮ → Pobierz diagnostykę).

Konfiguracja, stan działania, plan, wynik sprawdzenia i ostatnie wpisy dziennika — do wysłania przy zgłaszaniu
problemu. Adres i numer seryjny falownika, usługa powiadomień, hasła i dane lokalizacji są ukryte."""
from __future__ import annotations

import json
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

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


# ------------------------------------------------------------------ raport „do zgłoszenia” (jeden klik w Autotescie)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_MAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_NOTIFY_RE = re.compile(r"\bnotify\.[A-Za-z0-9_]+")
_SETTING_DOMAINS = ("switch", "number", "time", "select", "text")
_AUTO_STATE_KEYS = ("auto_skip", "auto_hist", "last_applied", "rejected_props", "live_apply", "auto_enabled", "auto_disabled")
REPORT_LOG_LINES = 100


def scrub_text(txt: str, secrets: list[str] | None = None) -> str:
    """Ostatnia siatka bezpieczeństwa na gotowym tekście: adresy IP, e-maile, usługi notify.* oraz literalne wartości
    z konfiguracji (adres, numer seryjny…) — gdyby jakaś trafiła do dziennika albo opisu poza kluczami z TO_REDACT."""
    for sec in sorted({x for x in (secrets or []) if x}, key=len, reverse=True):
        txt = txt.replace(sec, "***")
    keep = "\x00VER\x00"                    # numer wersji (np. 0.9.5.5) wygląda jak adres IPv4 — chronimy go przed zamazaniem
    txt = _IP_RE.sub("x.x.x.x", txt.replace(VERSION, keep)).replace(keep, VERSION)
    txt = _MAIL_RE.sub("***@***", txt)
    return _NOTIFY_RE.sub("notify.***", txt)


def _secret_values(cfg: dict[str, Any]) -> list[str]:
    out = []
    for k, v in (cfg or {}).items():
        if str(k).lower() in TO_REDACT and isinstance(v, (str, int)) and not isinstance(v, bool) and len(str(v)) >= 4:
            out.append(str(v))
    return out


def _proposals(plan: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, p in (plan.get("proposals") or {}).items():
        if isinstance(p, dict):
            out[k] = {f: p.get(f) for f in ("current", "proposed", "skip", "required", "confidence", "reason") if f in p}
    return out


def _price_sources(rt) -> dict[str, Any]:
    """Co czytniki cen widzą w encjach: lista encji, ich atrybuty z listami cen i które źródło poszło do planu (dziś / jutro)."""
    opt = rt.optimizer
    out: dict[str, Any] = {}
    for key, fn in (("zakup", "buy_report"), ("sprzedaż", "rce_report")):
        rep = _safe(lambda fn=fn: getattr(opt, fn)() or {}, {})
        out[key] = {"sprawdzone_encje": rep.get("checked"), "widziane": rep.get("seen"),
                    "dziś": rep.get("today"), "jutro": rep.get("tomorrow")}
    if hasattr(opt, "buy_tomorrow_status"):
        out["zakup_jutro"] = _safe(lambda: opt.buy_tomorrow_status(), {})
    return out


async def async_build_report(rt, log_lines: int = REPORT_LOG_LINES) -> dict[str, Any]:
    """Jeden raport do wklejenia przy zgłaszaniu problemu: wersja, ustawienia, plan, auto-stosowanie (powody i historia),
    autotest i ostatnie wpisy dziennika. Zwraca {"text", "filename", "summary"}; tekst jest dodatkowo czyszczony z adresów,
    numerów seryjnych, e-maili i usług powiadomień."""
    hass = rt.hass
    now = dt_util.now()
    cfg = _redact(dict(rt.cfg or {}))
    secrets = _secret_values(dict(rt.cfg or {}))
    plan = _safe(lambda: rt.plan() or {}, {})
    settings = {}
    for dom in _SETTING_DOMAINS:
        for st in _safe(lambda dom=dom: list(hass.states.async_all(dom)), []):
            eid = getattr(st, "entity_id", "")
            if eid.split(".", 1)[-1].startswith("bms_"):
                settings[eid] = st.state
    from .selftest import run as selftest_run
    try:
        selftest = await selftest_run(rt)
    except Exception as err:  # noqa: BLE001
        selftest = {"error": str(err)}
    report: dict[str, Any] = {
        "integration_version": VERSION, "generated_at": now.isoformat(timespec="seconds"), "brand": _safe(lambda: rt.brand(), ""),
        "config": cfg, "settings": dict(sorted(settings.items())),
        "plan": {"generated_at": plan.get("generated_at"), "mode": plan.get("mode"), "error": plan.get("error"),
                 "proposals": _proposals(plan)},
        "auto_apply": _redact({k: rt.state.get(k) for k in _AUTO_STATE_KEYS}),
        "state": _redact({k: rt.state.get(k) for k in _STATE_KEYS}),
        "prices": _safe(lambda: _price_sources(rt), {}),
        "selftest": selftest,
        "log": _safe(lambda: rt.log.last(max(1, int(log_lines))), []),
    }
    lines = [f"EMS komp-dec {VERSION} — raport diagnostyczny {report['generated_at']}",
             f"Falownik: {report['brand'] or '?'}", ""]
    sm = (selftest or {}).get("summary") or {}
    if sm:
        lines += [f"Autotest: {sm.get('errors', 0)} błędów, {sm.get('warnings', 0)} ostrzeżeń, {sm.get('ok', 0)} OK"]
        ic = {"ok": "OK", "warn": "UWAGA", "error": "BŁĄD"}
        for g in selftest.get("groups") or []:
            bad = [c for c in g.get("checks") or [] if c.get("status") != "ok"]
            lines.append(f"== {g.get('name')}" + ("" if bad else " — wszystko OK"))
            for c in bad:
                lines.append(f"[{ic.get(c.get('status'), c.get('status'))}] {c.get('title')}: {c.get('detail')}"
                             + (f" → {c.get('fix')}" if c.get("fix") else ""))
        lines.append("")
    for title, key in (("Plan i propozycje", "plan"), ("Auto-stosowanie (powody, historia, ostatnie zmiany)", "auto_apply"),
                       ("Stan", "state"), ("Ustawienia (przełączniki i liczby EMS)", "settings"), ("Konfiguracja", "config"),
                       ("Źródła cen (co widzi czytnik: encje, atrybuty z listami, użyte źródło)", "prices")):
        lines += [f"== {title}", json.dumps(report[key], ensure_ascii=False, indent=1, default=str), ""]
    lines.append(f"== Dziennik decyzji (ostatnie {len(report['log'])}, najnowsze pierwsze)")
    for e in report["log"]:
        lines.append(f"{str(e.get('ts', ''))[5:19].replace('T', ' ')} [{e.get('level', '')}/{e.get('kind', '')}] {e.get('msg', '')}")
    text = scrub_text("\n".join(lines), secrets)
    return {"text": text, "filename": f"ems-raport-{now.strftime('%Y%m%d-%H%M')}.txt",
            "summary": {"errors": sm.get("errors", 0), "warnings": sm.get("warnings", 0), "log_lines": len(report["log"])}}
