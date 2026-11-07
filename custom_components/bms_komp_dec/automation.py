"""Codzienna propozycja harmonogramu i tryb automatycznego stosowania (funkcja 6)."""
from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant

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
            _LOGGER.error("BMS apply: błąd %s: %s", eid, err)
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
        log.add("auto", "Auto-stosowanie: brak zmian do wprowadzenia"
                + (f" ({len(skipped)} pominiętych)" if skipped else ""))
        return {"applied": {}, "skipped": skipped}

    previous = {k: (_current(hass, k) or "00:00") for k in final}
    if dry_run:
        changes = ", ".join(f"{k}: {previous[k]}→{v}" for k, v in final.items())
        log.add("auto", f"Auto-stosowanie (PODGLĄD, bez zapisu) zmieniłoby {len(final)}: {changes}", "info",
                skipped=len(skipped))
        return {"applied": {}, "would_apply": final, "previous": previous, "skipped": skipped, "dry_run": True}
    applied_n, apply_skipped = await apply_times(hass, final)
    skipped.extend(apply_skipped)
    runtime.state["last_applied"] = previous
    runtime._save_state()  # noqa: SLF001
    changes = ", ".join(f"{k}: {previous[k]}→{v}" for k, v in final.items())
    log.add("auto", f"Auto-zastosowano {applied_n} zmian(y): {changes}", "ok", skipped=len(skipped))
    if applied_n:
        try:
            await runtime.monitor.notifier.send(
                "auto_apply", "🤖 BMS: auto-stosowanie zmieniło harmonogram",
                f"Zmieniono {applied_n}: {changes}.\nCofnięcie: usługa bms_komp_dec.undo_auto_apply lub zakładka EMS.",
                key="auto_apply", level="info")
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("BMS: powiadomienie o auto-stosowaniu nieudane: %s", err)
    return {"applied": final, "skipped": skipped}


async def async_undo_auto_apply(runtime, hass: HomeAssistant) -> dict[str, Any]:
    prev = runtime.state.get("last_applied") or {}
    if not prev:
        runtime.log.add("auto", "Cofnięcie: brak zapisanych poprzednich ustawień")
        return {"applied": 0, "skipped": ["brak danych do cofnięcia"]}
    applied_n, skipped = await apply_times(hass, dict(prev))
    runtime.state["last_applied"] = {}
    runtime._save_state()  # noqa: SLF001
    runtime.log.add("auto", f"Cofnięto auto-zastosowane godziny ({applied_n})", "ok")
    return {"applied": applied_n, "skipped": skipped}


async def async_daily_suggest(runtime, hass: HomeAssistant, optimizer) -> None:
    """Uruchamiane codziennie (16:00): propozycja + opcjonalnie automatyczne zastosowanie."""
    result = await optimizer.suggest()
    if result.get("error"):
        runtime.log.add("auto", f"Propozycja harmonogramu: {result['error']}", "warn")
        return
    proposals = result.get("proposals") or {}
    worthwhile = [
        p for p in proposals.values()
        if not p.get("skip") and p.get("proposed") and p.get("proposed") != p.get("current")
    ]
    if not worthwhile:
        runtime.log.add("auto", "Propozycja harmonogramu: bez zmian")
        return

    lines = ["Nowa propozycja harmonogramu (BMS):", ""]
    for p in worthwhile:
        lines.append(f"• {p['label']}: {p['current']} → {p['proposed']}")

    if switch_on(hass, "auto_apply", False):
        outcome = await async_auto_apply(runtime, hass, result)
        if outcome.get("dry_run"):
            lines += ["", f"PODGLĄD (przełącznik „Auto-stosowanie: tylko podgląd”): zmieniłbym {len(outcome.get('would_apply') or {})}, "
                          "ale nic nie zapisano."]
        else:
            lines += ["", f"Zastosowano automatycznie: {len(outcome['applied'])}."]
        if outcome["skipped"]:
            lines += ["Pominięto:"] + [f"– {s}" for s in outcome["skipped"]]
        lines += ["", "Cofnięcie: usługa bms_komp_dec.undo_auto_apply lub zakładka EMS."]
    else:
        runtime.log.add("auto", f"Nowa propozycja harmonogramu ({len(worthwhile)} zmian) — czeka na zatwierdzenie")
        lines += ["", "Otwórz panel → zakładka EMS → 'Zaproponuj' → 'Zastosuj zaznaczone'."]

    await runtime.monitor.notifier.send("proposal", "🤖 BMS: propozycja harmonogramu", "\n".join(lines),
                                        key="proposal", level="info")
