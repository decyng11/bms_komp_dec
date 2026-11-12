"""Codzienna propozycja harmonogramu i tryb automatycznego stosowania (funkcja 6)."""
from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant

from . import inbox
from .const import TIMES
from .helpers import find_eid, number_value, state_str, switch_on

_LOGGER = logging.getLogger(__name__)

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
VALID_TIME_KEYS = {k for k, _ in TIMES}

# (start, stop) — dla sprzedaży i blokady PV start < stop; ładowanie z sieci może przechodzić przez północ
CROSS_MIDNIGHT_OK = {"start_grid_charge", "start_grid_charge_2"}
PAIRS = [
    ("bateria_sprzedaz_start", "bateria_sprzedaz_stop"),
    ("bateria_sprzedaz_start_2", "bateria_sprzedaz_stop_2"),
    ("start_grid_charge", "stop_grid_charge"),
    ("start_grid_charge_2", "stop_grid_charge_2"),
    ("pv_export_start", "pv_export_stop"),
]


# przełącznik zestawu, bez którego okno (godziny Start/Stop) nigdy nie zadziała
SET_SWITCH = {
    "start_grid_charge": "ladowanie_z_sieci_1", "stop_grid_charge": "ladowanie_z_sieci_1",
    "start_grid_charge_2": "ladowanie_z_sieci_2", "stop_grid_charge_2": "ladowanie_z_sieci_2",
    "bateria_sprzedaz_start": "bateria_sprzedaz_1", "bateria_sprzedaz_stop": "bateria_sprzedaz_1",
    "bateria_sprzedaz_start_2": "bateria_sprzedaz_2", "bateria_sprzedaz_stop_2": "bateria_sprzedaz_2",
}
SALE_SWITCHES = {"bateria_sprzedaz_1", "bateria_sprzedaz_2"}
SET_TIMES = {
    "ladowanie_z_sieci_1": ("start_grid_charge", "stop_grid_charge"),
    "ladowanie_z_sieci_2": ("start_grid_charge_2", "stop_grid_charge_2"),
    "bateria_sprzedaz_1": ("bateria_sprzedaz_start", "bateria_sprzedaz_stop"),
    "bateria_sprzedaz_2": ("bateria_sprzedaz_start_2", "bateria_sprzedaz_stop_2"),
}


async def async_enable_sets(runtime, hass: HomeAssistant, keys) -> list[str]:
    """Włącza przełączniki zestawów, których godziny właśnie zapisano — bez tego okno nigdy nie wystartuje.

    Sprzedaż z baterii włączamy TYLKO, gdy nie ma zakazu sprzedaży (import z sieci, bilans arbitrażu: bateria
    naładowana więcej niż wyprodukowało PV, tryb burzowy). Samo włączenie niczego nie uruchamia — każdy start sprzedaży
    i tak przechodzi te same blokady w czasie wykonania."""
    out: list[str] = []
    done = runtime.state.setdefault("auto_enabled", [])
    for sw_key in sorted({SET_SWITCH[k] for k in keys if k in SET_SWITCH}):
        eid = find_eid(hass, "switch", sw_key)
        st = hass.states.get(eid)
        if st is None or st.state == "on":
            continue
        k1, k2 = SET_TIMES[sw_key]
        t1, t2 = _current(hass, k1), _current(hass, k2)
        if not t1 or not t2 or "00:00" in (t1, t2) or t1 == t2:
            continue                                   # okno niepełne — nie ma czego włączać
        label = st.attributes.get("friendly_name") or sw_key
        if sw_key in SALE_SWITCHES:
            why = runtime.sell_block_reason(strict_grid=False)
            if why:
                runtime.log.add("auto", f"Nie włączam „{label}”: zakaz sprzedaży — {why}", "warn")
                continue
        try:
            await hass.services.async_call("switch", "turn_on", {"entity_id": eid}, blocking=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS: nie udało się włączyć %s: %s", eid, err)
            continue
        was_disabled = list(runtime.state.get("auto_disabled") or [])
        if sw_key in was_disabled:        # wyłączył go wcześniej sam EMS (plan pomijał sprzedaż) — to nie jest „włączone przez auto-stosowanie”
            runtime.state["auto_disabled"] = [x for x in was_disabled if x != sw_key]
        elif sw_key not in done:
            done.append(sw_key)
        out.append(sw_key)
        runtime.log.add("auto", f"Włączono „{label}” ({t1}–{t2}) — bez tego okno by nie wystartowało", "ok")
    if out:
        runtime._save_state()  # noqa: SLF001
    return out


async def async_sync_sale_sets(runtime, hass: HomeAssistant, proposals: dict[str, Any]) -> list[str]:
    """Plan pomija sprzedaż (np. nieopłacalna przy małym PV, zakaz arbitrażu) → wyłącz włączony zestaw sprzedaży,
    żeby stare godziny nie wykonały sprzedaży, której plan nie przewiduje. Zapamiętuje wyłączone zestawy,
    by włączyć je z powrotem, gdy plan znów zaproponuje sprzedaż. Pomija propozycje o niskiej pewności (brak danych)."""
    off: list[str] = []
    done = runtime.state.setdefault("auto_disabled", [])
    for sw_key in sorted(SALE_SWITCHES):
        k1, k2 = SET_TIMES[sw_key]
        p1, p2 = proposals.get(k1), proposals.get(k2)
        if not isinstance(p1, dict) or not isinstance(p2, dict) or not (p1.get("skip") and p2.get("skip")):
            continue
        if p1.get("confidence") == "low":
            continue
        eid = find_eid(hass, "switch", sw_key)
        st = hass.states.get(eid)
        label = (st.attributes.get("friendly_name") if st is not None else None) or sw_key
        why = str(p1.get("reason") or "").replace("Pomiń — ", "")[:220]
        if st is not None and st.state == "on":
            try:
                await hass.services.async_call("switch", "turn_off", {"entity_id": eid}, blocking=True)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS: nie udało się wyłączyć %s: %s", eid, err)
                continue
            if sw_key not in done:
                done.append(sw_key)
            off.append(sw_key)
            runtime.log.add("auto", f"Wyłączono „{label}”: plan nie przewiduje sprzedaży — {why}", "warn")
        # wyzeruj okno (stop = start), żeby w falowniku nie wisiały stare godziny sprzedaży
        t1, t2 = _current(hass, k1), _current(hass, k2)
        if t1 and t2 and t1 != t2 and t1 != "00:00":
            n, _err = await apply_times(hass, {k2: t1})
            if n:
                runtime.log.add("auto", f"Wyzerowano okno sprzedaży „{label}” ({t1}–{t2} → {t1}–{t1}): brak propozycji", "info")
    if off:
        runtime._save_state()  # noqa: SLF001
    return off


def _plan_confirmed_keys(runtime, proposals: dict[str, Any]) -> set[str]:
    """Klucze godzin zestawów sprzedaży wyłączonych przez EMS, dla których plan znów proponuje sprzedaż (bez zmiany godzin)."""
    out: set[str] = set()
    for sw_key in runtime.state.get("auto_disabled") or []:
        k1, k2 = SET_TIMES.get(sw_key, (None, None))
        p1, p2 = proposals.get(k1), proposals.get(k2)
        if isinstance(p1, dict) and isinstance(p2, dict) and not p1.get("skip") and not p2.get("skip") and p1.get("proposed") and p2.get("proposed"):
            out.update((k1, k2))
    return out


def _minutes(hm: str | None) -> int | None:
    if not hm or not TIME_RE.match(hm[:5]):
        return None
    return int(hm[:2]) * 60 + int(hm[3:5])


async def apply_times(hass: HomeAssistant, times: dict[str, Any]) -> tuple[int, list[str]]:
    """Zapisuje godziny do encji time.bms_*. Zwraca (zastosowane, pominięte)."""
    applied = 0
    skipped: list[str] = []
    if not isinstance(times, dict):
        return 0, ["times nie jest słownikiem"]
    for key, val in times.items():
        if key not in VALID_TIME_KEYS:
            skipped.append(f"{key}: nieznany klucz")
            continue
        if not isinstance(val, str) or not TIME_RE.match(val):
            skipped.append(f"{key}: zły format ({val})")
            continue
        eid = find_eid(hass, "time", key)
        if not hass.states.get(eid):
            skipped.append(f"{key}: brak encji")
            continue
        try:
            await hass.services.async_call(
                "time", "set_value", {"entity_id": eid, "time": val + ":00"}, blocking=True)
            applied += 1
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS apply: błąd %s: %s", eid, err)
            skipped.append(f"{key}: {err}")
    return applied, skipped


def _current(hass: HomeAssistant, key: str) -> str | None:
    raw = state_str(hass, find_eid(hass, "time", key))
    return raw[:5] if raw else None


async def async_auto_apply(runtime, hass: HomeAssistant, result: dict[str, Any],
                           dry_run: bool | None = None) -> dict[str, Any]:
    """Stosuje propozycje z zabezpieczeniami. Zwraca {'applied': {...}, 'skipped': [...]}.

    dry_run=True (albo włączony przełącznik „Auto-stosowanie: tylko podgląd”): przechodzi przez wszystkie
    zabezpieczenia i pokazuje, co zostałoby zmienione ('would_apply'), ale niczego nie zapisuje."""
    if dry_run is None:
        dry_run = switch_on(hass, "auto_apply_dry_run", False)
    log = runtime.log
    proposals = result.get("proposals") or {}
    skipped: list[str] = []

    # Zabezpieczenie 1: nie zmieniamy harmonogramu, gdy system właśnie coś wykonuje.
    busy = []
    if runtime.is_selling():
        busy.append("trwa sprzedaż")
    if runtime.pv_charge_blocked():
        busy.append("ładowanie PV zablokowane")
    if runtime.grid_charging_on():
        busy.append("trwa ładowanie z sieci")
    if busy:
        msg = "Auto-stosowanie wstrzymane: " + ", ".join(busy)
        log.add("auto", msg, "warn")
        return {"applied": {}, "skipped": [msg]}

    disabled_sets = [] if dry_run else await async_sync_sale_sets(runtime, hass, proposals)
    max_shift = number_value(hass, "auto_apply_max_shift_h", 4.0)
    wanted: dict[str, str] = {}
    for key, p in proposals.items():
        if key not in VALID_TIME_KEYS or not isinstance(p, dict):
            continue
        proposed = p.get("proposed")
        if p.get("skip") or not proposed or not TIME_RE.match(str(proposed)):
            continue
        cur = _current(hass, key)
        if cur == proposed:
            continue
        if inbox.is_rejected(runtime.state, key, proposed):
            skipped.append(f"{key}: propozycja odrzucona w panelu")
            continue
        if p.get("confidence") == "low":
            skipped.append(f"{key}: niska pewność propozycji")
            continue
        cur_m, new_m = _minutes(cur), _minutes(proposed)
        # Zabezpieczenie 2: limit przesunięcia względem aktualnego ustawienia.
        if max_shift > 0 and cur_m not in (None, 0) and new_m is not None:
            shift_h = abs(new_m - cur_m) / 60.0
            if shift_h > max_shift:
                skipped.append(f"{key}: przesunięcie {shift_h:.1f} h > limit {max_shift:.0f} h")
                continue
        wanted[key] = str(proposed)

    # Zabezpieczenie 3: spójność par start/stop (start < stop, obie godziny ustawione).
    final: dict[str, str] = {}
    for start_k, stop_k in PAIRS:
        if start_k not in wanted and stop_k not in wanted:
            continue
        start_v = wanted.get(start_k) or _current(hass, start_k)
        stop_v = wanted.get(stop_k) or _current(hass, stop_k)
        s_m, e_m = _minutes(start_v), _minutes(stop_v)
        crosses = start_k in CROSS_MIDNIGHT_OK
        if s_m is None or e_m is None or s_m == 0 or e_m == 0 or s_m == e_m or (s_m > e_m and not crosses):
            skipped.append(f"{start_k}/{stop_k}: niespójna para ({start_v}→{stop_v})")
            continue
        for k in (start_k, stop_k):
            if k in wanted:
                final[k] = wanted[k]

    if not final:
        if not dry_run:
            await async_enable_sets(runtime, hass, _plan_confirmed_keys(runtime, proposals))
        log.add("auto", "Auto-stosowanie: brak zmian do wprowadzenia"
                + (f" ({len(skipped)} pominiętych)" if skipped else ""))
        return {"applied": {}, "skipped": skipped, "disabled_sets": disabled_sets}

    previous = {k: (_current(hass, k) or "00:00") for k in final}
    if dry_run:
        changes = ", ".join(f"{k}: {previous[k]}→{v}" for k, v in final.items())
        log.add("auto", f"Auto-stosowanie (PODGLĄD, bez zapisu) zmieniłoby {len(final)}: {changes}", "info",
                skipped=len(skipped))
        return {"applied": {}, "would_apply": final, "previous": previous, "skipped": skipped, "dry_run": True}
    applied_n, apply_skipped = await apply_times(hass, final)
    skipped.extend(apply_skipped)
    enabled = await async_enable_sets(runtime, hass, set(final) | _plan_confirmed_keys(runtime, proposals)) if applied_n else []
    runtime.state["last_applied"] = previous
    runtime._save_state()  # noqa: SLF001
    changes = ", ".join(f"{k}: {previous[k]}→{v}" for k, v in final.items())
    if enabled:
        changes += "; włączono zestawy: " + ", ".join(enabled)
    log.add("auto", f"Auto-zastosowano {applied_n} zmian(y): {changes}", "ok", skipped=len(skipped))
    if applied_n:
        try:
            await runtime.monitor.notifier.send(
                "auto_apply", "🤖 EMS: auto-stosowanie zmieniło harmonogram",
                f"Zmieniono {applied_n}: {changes}.\nCofnięcie: usługa bms_komp_dec.undo_auto_apply lub zakładka EMS.",
                key="auto_apply", level="info")
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS: powiadomienie o auto-stosowaniu nieudane: %s", err)
    return {"applied": final, "skipped": skipped, "disabled_sets": disabled_sets}


async def async_undo_auto_apply(runtime, hass: HomeAssistant) -> dict[str, Any]:
    prev = runtime.state.get("last_applied") or {}
    if not prev and not runtime.state.get("auto_disabled") and not runtime.state.get("auto_enabled"):
        runtime.log.add("auto", "Cofnięcie: brak zapisanych poprzednich ustawień")
        return {"applied": 0, "skipped": ["brak danych do cofnięcia"]}
    applied_n, skipped = await apply_times(hass, dict(prev))
    for sw_key in list(runtime.state.get("auto_enabled") or []):     # zestawy włączone przez auto-stosowanie wracają do wyłączonych
        eid = find_eid(hass, "switch", sw_key)
        if hass.states.get(eid):
            try:
                await hass.services.async_call("switch", "turn_off", {"entity_id": eid}, blocking=True)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS: nie udało się wyłączyć %s: %s", eid, err)
    runtime.state["auto_enabled"] = []
    for sw_key in list(runtime.state.get("auto_disabled") or []):    # zestawy sprzedaży wyłączone przez plan wracają jako włączone
        eid = find_eid(hass, "switch", sw_key)
        if hass.states.get(eid):
            try:
                await hass.services.async_call("switch", "turn_on", {"entity_id": eid}, blocking=True)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS: nie udało się włączyć %s: %s", eid, err)
    runtime.state["auto_disabled"] = []
    runtime.state["last_applied"] = {}
    runtime._save_state()  # noqa: SLF001
    runtime.log.add("auto", f"Cofnięto auto-zastosowane godziny ({applied_n})", "ok")
    return {"applied": applied_n, "skipped": skipped}


def _store_sale_plan(runtime, proposals: dict[str, Any]) -> None:
    """Zapamiętuje zaplanowaną sprzedaż (kWh, przychód brutto, zysk netto) na dany dzień — do porównania z faktem.

    Każdy zestaw (poranny / wieczorny szczyt) zapisywany osobno, więc późniejsze odświeżenie planu nie kasuje okna,
    które już minęło."""
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    today = dt_util.now().date()
    store = runtime.state.setdefault("sale_plan", {})
    changed = False
    for key in ("bateria_sprzedaz_start", "bateria_sprzedaz_start_2"):
        p = proposals.get(key)
        if not isinstance(p, dict) or p.get("skip") or "sale_kwh" not in p:
            continue
        d = (today + timedelta(days=int(p.get("sale_day") or 0))).isoformat()
        rec = store.setdefault(d, {"sets": {}})
        rec.setdefault("sets", {})[key] = {"kwh": round(float(p.get("sale_kwh") or 0.0), 2),
                                           "gross": round(float(p.get("sale_gross_pln") or 0.0), 2),
                                           "net": round(float(p.get("gain_pln") or 0.0), 2)}
        for f in ("kwh", "gross", "net"):
            rec[f] = round(sum(v[f] for v in rec["sets"].values()), 2)
        changed = True
    if changed:
        runtime._save_state()  # noqa: SLF001


async def async_daily_suggest(runtime, hass: HomeAssistant, optimizer) -> None:
    """Uruchamiane codziennie (16:00): propozycja + opcjonalnie automatyczne zastosowanie."""
    result = await optimizer.suggest()
    if result.get("error"):
        runtime.log.add("auto", f"Propozycja harmonogramu: {result['error']}", "warn")
        return
    proposals = result.get("proposals") or {}
    _store_sale_plan(runtime, proposals)
    worthwhile = [
        p for k, p in proposals.items()
        if not p.get("skip") and p.get("proposed") and p.get("proposed") != p.get("current")
        and not inbox.is_rejected(runtime.state, k, p.get("proposed"))
    ]
    if not worthwhile:
        if switch_on(hass, "auto_apply", False):      # nawet bez zmian godzin: wyłącz zestaw sprzedaży, gdy plan jej nie przewiduje
            outcome = await async_auto_apply(runtime, hass, result)
            off = outcome.get("disabled_sets") or []
            if off:
                await runtime.monitor.notifier.send(
                    "auto_apply", "🤖 EMS: wyłączono sprzedaż z baterii",
                    "Plan nie przewiduje dziś opłacalnej sprzedaży, więc wyłączyłem: " + ", ".join(off)
                    + ".\nZestaw włączy się sam, gdy plan znów zaproponuje sprzedaż (albo cofnij: usługa bms_komp_dec.undo_auto_apply).",
                    key="auto_apply", level="info")
        runtime.log.add("auto", "Propozycja harmonogramu: bez zmian")
        return

    lines = ["Nowa propozycja harmonogramu (EMS):", ""]
    for p in worthwhile:
        lines.append(f"• {p['label']}: {p['current']} → {p['proposed']}")

    if switch_on(hass, "auto_apply", False):
        outcome = await async_auto_apply(runtime, hass, result)
        if outcome.get("dry_run"):
            lines += ["", f"PODGLĄD (przełącznik „Auto-stosowanie: tylko podgląd”): zmieniłbym {len(outcome.get('would_apply') or {})}, "
                          "ale nic nie zapisano."]
        else:
            lines += ["", f"Zastosowano automatycznie: {len(outcome['applied'])}."]
            if outcome.get("disabled_sets"):
                lines += [f"Wyłączono zestawy sprzedaży (plan jej nie przewiduje): {', '.join(outcome['disabled_sets'])}."]
        if outcome["skipped"]:
            lines += ["Pominięto:"] + [f"– {s}" for s in outcome["skipped"]]
        lines += ["", "Cofnięcie: usługa bms_komp_dec.undo_auto_apply lub zakładka EMS."]
    else:
        runtime.log.add("auto", f"Nowa propozycja harmonogramu ({len(worthwhile)} zmian) — czeka na zatwierdzenie")
        lines += ["", "Otwórz panel i dzwonek 🔔 → „Do decyzji”: Potwierdź albo Odrzuć."]

    await runtime.monitor.notifier.send("proposal", "🤖 EMS: propozycja harmonogramu", "\n".join(lines),
                                        key="proposal", level="info")
