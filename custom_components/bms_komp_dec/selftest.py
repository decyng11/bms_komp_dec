"""Autotest (Diagnostyka → 🧪 Autotest): sprawdzenie na żywo tego, czego nie da się sprawdzić bez prawdziwej instalacji.

Tylko odczyt — nic nie jest zapisywane do falownika ani do ustawień. Wynik to grupy kontroli (ok / ostrzeżenie / błąd)
z opisem i podpowiedzią; karta składa z nich raport do skopiowania."""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .const import CONF_GRID_POWER, CONF_GRID_VOLTAGE_L1, CONF_SOC, DOMAIN, VERSION

_BAD = ("unknown", "unavailable", "none", "")
_INVERTER_HINT = re.compile(r"solarman|deye|sunsynk|inverter|falownik|solis|growatt|goodwe|huawei|fronius|sofar|foxess", re.IGNORECASE)


def _c(cid: str, title: str, status: str, detail: str, fix: str = "") -> dict[str, str]:
    return {"id": cid, "title": title, "status": status, "detail": detail, "fix": fix}


def _age_min(st) -> float | None:
    t = getattr(st, "last_reported", None) or getattr(st, "last_updated", None)
    if t is None:
        return None
    try:
        return max(0.0, (dt_util.utcnow() - t).total_seconds() / 60.0)
    except Exception:  # noqa: BLE001
        return None


def _inverter_group(rt) -> list[dict[str, str]]:
    hass, cfg = rt.hass, rt.cfg
    out = []
    for key, label in ((CONF_SOC, "SOC baterii"), (CONF_GRID_POWER, "Moc sieci")):
        eid = cfg.get(key)
        st = hass.states.get(eid) if eid else None
        if st is None:
            out.append(_c(f"live_{key}", label, "error", f"brak encji {eid or '(nie ustawiono)'}", "Wskaż encję w konfiguracji BMS."))
            continue
        if str(st.state).strip().lower() in _BAD:
            out.append(_c(f"live_{key}", label, "error", f"{eid} = „{st.state}”", "Logger nie odpowiada — sprawdź zasilanie i Wi-Fi loggera."))
            continue
        age = _age_min(st)
        if age is not None and age > 10 and key == CONF_GRID_POWER:
            out.append(_c(f"live_{key}", label, "warn", f"{eid} = {st.state}, bez zmian od {age:.0f} min",
                          "Moc sieci zwykle zmienia się co kilka sekund — możliwe, że odczyty stoją."))
        else:
            out.append(_c(f"live_{key}", label, "ok", f"{eid} = {st.state}" + (f" (odczyt sprzed {age:.0f} min)" if age is not None and age >= 1 else "")))
    data = rt.coordinator.data or {}
    keys = [k for k in ("pv_power", "load_power", "battery_power", "grid_power") if isinstance(data.get(k), (int, float))]
    out.append(_c("live_coord", "Dane w BMS (co 10 s)", "ok" if len(keys) == 4 else "warn",
                  ", ".join(f"{k.replace('_power', '')} {data[k]:.0f} W" for k in keys) or "brak",
                  "" if len(keys) == 4 else "Część mocy jest liczona z innych odczytów — sprawdź encje mocy w konfiguracji."))
    # wpisy integracji (kreator: BMS + falownik bezpośredni) i skąd są encje sterujące
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        from .direct import is_inverter_entry
        inv = [e for e in entries if is_inverter_entry(e)]
        bms = [e for e in entries if not is_inverter_entry(e)]
        has_solarman = bool(hass.config_entries.async_entries("solarman"))
        src = "falownik połączony bezpośrednio" if inv else ("ha-solarman" if has_solarman else "brak integracji falownika")
        st_ok = "ok" if bms and (inv or has_solarman) else "warn"
        out.append(_c("entries", "Wpisy integracji", st_ok, f"BMS ×{len(bms)}, falownik bezpośredni ×{len(inv)}, ha-solarman: {'tak' if has_solarman else 'nie'} → {src}",
                      "" if st_ok == "ok" else "Kreator nie dokończył konfiguracji — uruchom go ponownie z Diagnostyki."))
        if inv and has_solarman:
            out.append(_c("entries_both", "Dwa połączenia z falownikiem", "warn",
                          "Jest i falownik bezpośredni, i ha-solarman — logger zwykle przyjmuje tylko jedno połączenie naraz.",
                          "Zostaw jedno z nich (np. usuń wpis tego falownika z ha-solarman)."))
    except Exception as err:  # noqa: BLE001
        out.append(_c("entries", "Wpisy integracji", "warn", f"nie udało się sprawdzić: {err}"))
    try:
        from homeassistant.helpers import entity_registry as er
        reg = er.async_get(hass)
        plats = {}
        for role in ("work_mode", "charge_current", "export_surplus", "tou_select"):
            ent = reg.async_get(rt.eid(role))
            plats[role] = getattr(ent, "platform", None) or "?"
        uniq = sorted(set(plats.values()))
        out.append(_c("ctl_src", "Encje sterujące falownikiem", "ok" if len(uniq) == 1 and uniq[0] != "?" else "warn",
                      ", ".join(f"{r}: {p}" for r, p in plats.items()),
                      "" if len(uniq) == 1 and uniq[0] != "?" else "Encje sterujące pochodzą z różnych integracji albo spoza rejestru — sprawdź konfigurację."))
    except Exception:  # noqa: BLE001
        pass
    return out


def _pv_group(rt) -> list[dict[str, str]]:
    out = []
    opt = rt.optimizer
    try:
        pvp = opt.pv_card_payload()
    except Exception as err:  # noqa: BLE001
        return [_c("pv", "Prognoza PV", "error", f"błąd odczytu: {err}")]
    src = pvp.get("pv_forecast_source") or "—"
    for lbl, key in (("dziś", "pv_hourly_today"), ("jutro", "pv_hourly_tomorrow")):
        arr = pvp.get(key)
        tot = round(sum(v for v in arr if isinstance(v, (int, float))), 1) if arr else None
        daily = next((d.get("kwh") for d in (pvp.get("pv_daily") or []) if d.get("date") == (dt_util.now().date() + timedelta(days=0 if lbl == "dziś" else 1)).isoformat()), None)
        if arr:
            note = f"{src}: {tot} kWh z godzin" + (f", suma dzienna {daily} kWh" if daily is not None else "")
            bad = daily is not None and tot is not None and daily > 1 and abs(tot - daily) / daily > 0.25
            out.append(_c(f"pv_{lbl}", f"Prognoza PV godzinowa — {lbl}", "warn" if bad else "ok", note,
                          "Suma godzinowa różni się od dziennej o ponad 25% — sprawdź, czy encja prognozy dotyczy wszystkich połaci." if bad else ""))
        else:
            out.append(_c(f"pv_{lbl}", f"Prognoza PV godzinowa — {lbl}", "error" if lbl == "dziś" else "warn", "brak",
                          "Zainstaluj Solcast albo Forecast.Solar i wskaż encję prognozy w konfiguracji BMS."))
    fc = getattr(opt, "pv_fc", None)
    if fc is not None and fc.has_forecast_solar():
        n = getattr(fc, "_fs_entries", 0)
        out.append(_c("pv_fs", "Forecast.Solar (dane godzinowe z HA)", "ok" if n and not fc.fs_error else "warn",
                      f"wpisów z prognozą: {n}" + (f" — {fc.fs_error}" if fc.fs_error else ""),
                      "" if n and not fc.fs_error else "Twoja wersja HA może nie udostępniać prognozy godzinowej Forecast.Solar — wyślij ten raport."))
    try:
        corr = rt.insights.pv_correction()
        out.append(_c("pv_corr", "Korekta prognozy PV", "ok", f"× {corr['factor']} (dni z danymi: {corr['days']})"))
    except Exception:  # noqa: BLE001
        pass
    return out


def _price_group(rt) -> list[dict[str, str]]:
    out = []
    b, s = rt.buy_price(), rt.sell_price()
    out.append(_c("price_now", "Ceny teraz", "ok" if s is not None and b is not None else "error",
                  f"zakup {b if b is not None else '—'} zł/kWh, sprzedaż {s if s is not None else '—'} zł/kWh",
                  "" if s is not None and b is not None else "Sprawdź encje cen w konfiguracji BMS."))
    try:
        arr = rt.optimizer.rce_arrays()
        today = dt_util.now().date()
        for lbl, d in (("dziś", today), ("jutro", today + timedelta(days=1))):
            n = sum(1 for v in (arr.get(d.isoformat()) or []) if isinstance(v, (int, float)))
            need = int(rt.optimizer.rce_expected_hours(d)) if hasattr(rt.optimizer, "rce_expected_hours") else 24
            ok = n >= need
            out.append(_c(f"rce_{lbl}", f"Ceny sprzedaży godzinowe — {lbl}", "ok" if ok else ("warn" if lbl == "jutro" else "error"),
                          f"{n}/{need} godzin", "" if ok else ("Ceny na jutro pojawiają się po południu." if lbl == "jutro" else "Sprawdź integrację z cenami.")))
    except Exception as err:  # noqa: BLE001
        out.append(_c("rce", "Ceny godzinowe", "warn", f"nie udało się odczytać: {err}"))
    return out


def _grid_group(rt) -> list[dict[str, str]]:
    eid = rt.cfg.get(CONF_GRID_VOLTAGE_L1)
    st = rt.hass.states.get(eid) if eid else None
    thr = 100.0
    try:
        from . import notify_cfg as ncfg
        thr = ncfg.threshold(rt.monitor.notifier.cfg(), "grid_outage") or 100.0
    except Exception:  # noqa: BLE001
        pass
    if st is None:
        return [_c("grid_v", "Wykrywanie zaniku sieci", "warn", f"brak encji napięcia L1 ({eid or 'nie ustawiono'})",
                   "Wskaż encję napięcia sieci L1 w konfiguracji — bez niej BMS nie zauważy zaniku sieci.")]
    try:
        v = float(st.state)
    except (TypeError, ValueError):
        return [_c("grid_v", "Wykrywanie zaniku sieci", "warn", f"{eid} = „{st.state}” (brak liczby)")]
    go = rt.state.get("grid_outage") or {}
    if v < thr:
        return [_c("grid_v", "Wykrywanie zaniku sieci", "warn", f"{eid} = {v:.0f} V — poniżej progu {thr:.0f} V, BMS uznaje to za zanik sieci"
                   + (" (zgłoszony)" if go.get("notified") else ""),
                   "Jeśli sieć jest, a napięcie pokazuje 0 V, ta encja nie nadaje się do wykrywania zaniku — wskaż inną.")]
    return [_c("grid_v", "Wykrywanie zaniku sieci", "ok", f"{eid} = {v:.0f} V (próg zaniku {thr:.0f} V)")]


async def _devices_group(rt) -> list[dict[str, str]]:
    out = []
    hass = rt.hass
    for d in rt.devices.devices:
        probs, infos = [], []
        for key, kind in (("power_eid", "moc"), ("energy_eid", "energia")):
            eid = d.get(key)
            if not eid:
                continue
            st = hass.states.get(eid)
            if st is None:
                probs.append(f"{kind}: brak encji {eid}")
            elif str(st.state).strip().lower() in _BAD:
                probs.append(f"{kind}: {eid} niedostępna")
            else:
                sc = (st.attributes or {}).get("state_class")
                infos.append(f"{kind} {st.state} {(st.attributes or {}).get('unit_of_measurement', '')}".strip()
                             + ("" if sc else " (bez state_class — brak historii sprzed dodania)"))
        if d.get("switch_eid"):
            sw = hass.states.get(d["switch_eid"])
            if sw is None:
                probs.append(f"przełącznik {d['switch_eid']} nie istnieje")
            else:
                infos.append(f"przełącznik {sw.state}")
        out.append(_c(f"dev_{d['id']}", f"Urządzenie: {d['name']}", "error" if probs else "ok", "; ".join(probs + infos) or "—",
                      "Popraw encje w „Edytuj” w zakładce Urządzenia." if probs else ""))
    try:
        from .discover import async_discover
        res = await async_discover(hass, dict(rt.cfg or {}), list(rt.devices.devices))
        sus = [c for c in res.get("candidates") or [] if _INVERTER_HINT.search(f"{c.get('integration')} {c.get('name')} {c.get('energy_eid')}")]
        if sus:
            out.append(_c("disc_inv", "Wyszukiwanie urządzeń", "warn",
                          "Wśród propozycji są liczniki, które wyglądają na falownik: "
                          + ", ".join(f"{c['energy_eid']} ({c.get('integration') or '?'})" for c in sus[:5]),
                          "Wyślij ten raport — dopiszę tę integrację do pomijanych."))
        else:
            out.append(_c("disc_inv", "Wyszukiwanie urządzeń", "ok", f"propozycji: {res.get('total', 0)}, bez liczników falownika"))
    except Exception as err:  # noqa: BLE001
        out.append(_c("disc_inv", "Wyszukiwanie urządzeń", "warn", f"nie udało się sprawdzić: {err}"))
    ctl = rt.dev_ctl.status()
    n = len(ctl["devices"])
    if n:
        out.append(_c("dev_ctl", "Sterowanie urządzeniami", "ok" if ctl["enabled"] else "warn",
                      f"{'włączone' if ctl['enabled'] else 'wyłączone'}, urządzeń z przełącznikiem: {n}",
                      "" if ctl["enabled"] else "Włącz „Sterowanie urządzeniami” w zakładce Urządzenia, jeśli BMS ma włączać przełączniki."))
    return out


def _work_group(rt) -> list[dict[str, str]]:
    out = []
    plan = rt.plan()
    if not plan:
        out.append(_c("plan", "Plan 24 h", "warn", "jeszcze nie policzony", "Plan powstaje w ciągu minuty od startu — odśwież za chwilę."))
    elif plan.get("error"):
        out.append(_c("plan", "Plan 24 h", "error", str(plan.get("error"))))
    else:
        out.append(_c("plan", "Plan 24 h", "ok", f"policzony {str(plan.get('generated_at') or '')[11:16]}, tryb {plan.get('mode') or 'normal'}"))
    st = rt.state
    out.append(_c("notify_saved", "Ustawienia powiadomień", "ok",
                  "zapisane w integracji" if isinstance(st.get("notify_cfg"), dict) else "domyślne (nie zmieniano)"))
    try:
        rep = rt.repairs.status()
        out.append(_c("repairs", "Zgłoszenia w Naprawach HA", "ok" if not rep["active"] else "warn",
                      ", ".join(rep["active"]) or "brak"))
    except Exception:  # noqa: BLE001
        pass
    try:
        today = dt_util.now().date().isoformat()
        n = sum(1 for k in rt.insights.hours if k.startswith(today))
        out.append(_c("hourly", "Dziennik godzinowy (oszczędności)", "ok" if n else "warn", f"godzin z danymi dziś: {n}",
                      "" if n else "Dane zbierają się co 10 s — sprawdź za godzinę."))
    except Exception:  # noqa: BLE001
        pass
    return out


async def run(rt) -> dict[str, Any]:
    from .health import health_check
    hc = health_check(rt)
    groups = [
        {"name": "Falownik i połączenie", "checks": _inverter_group(rt)},
        {"name": "Prognoza PV", "checks": _pv_group(rt)},
        {"name": "Ceny", "checks": _price_group(rt)},
        {"name": "Zanik sieci", "checks": _grid_group(rt)},
        {"name": "Urządzenia", "checks": await _devices_group(rt)},
        {"name": "Działanie", "checks": _work_group(rt)},
        {"name": "Konfiguracja (jak w kreatorze)", "checks": hc["checks"]},
    ]
    allc = [c for g in groups for c in g["checks"]]
    n_err = sum(1 for c in allc if c["status"] == "error")
    n_warn = sum(1 for c in allc if c["status"] == "warn")
    return {"version": VERSION, "time": dt_util.now().isoformat(timespec="seconds"), "groups": groups,
            "commands": hc.get("commands") or [],
            "summary": {"errors": n_err, "warnings": n_warn, "ok": len(allc) - n_err - n_warn}}
