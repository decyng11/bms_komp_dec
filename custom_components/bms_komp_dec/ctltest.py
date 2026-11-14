"""Test sterowania falownikiem (3): bezpieczny zapis i odczyt zwrotny przez cały łańcuch HA → falownik → encja.

Zmieniamy „maksymalny prąd ładowania baterii” o jeden krok (±1 A w dozwolonym zakresie), czekamy, aż encja pokaże nową
wartość, i zawsze przywracamy poprzednią. To sprawdza, że komendy EMS naprawdę docierają do falownika — bez
przełączania trybów pracy i bez wpływu na sprzedaż czy ładowanie z sieci."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from homeassistant.util import dt as dt_util

from . import brands

WAIT_S = 30.0
POLL_S = 1.0
TOL = 0.06


def _fnum(st) -> float | None:
    try:
        return float(st.state)
    except (AttributeError, TypeError, ValueError):
        return None


def _entity(rt) -> str | None:
    brand = rt.brand()
    if brand == brands.DEYE:
        return rt.eid("charge_current")
    if brand == brands.SOFAR_HYBRID:
        return brands.role_eid(rt.hass, rt.cfg, brand, "charge_current")
    return None


async def _wait_for(rt, eid: str, value: float, sleep=asyncio.sleep) -> float | None:
    """Sekundy do chwili, gdy encja pokaże `value`; None = nie doczekano się."""
    t0 = time.monotonic()
    while time.monotonic() - t0 <= WAIT_S:
        v = _fnum(rt.hass.states.get(eid))
        if v is not None and abs(v - value) <= TOL:
            return round(time.monotonic() - t0, 1)
        await sleep(POLL_S)
    return None


async def run(rt, sleep=asyncio.sleep) -> dict[str, Any]:
    res: dict[str, Any] = {"ts": dt_util.now().isoformat(), "ok": False, "entity": None, "detail": ""}

    def done(detail: str, ok: bool = False) -> dict[str, Any]:
        res["ok"], res["detail"] = ok, detail
        rt.state["control_test"] = res
        rt.log.add("command", f"Test sterowania falownikiem: {detail}", "ok" if ok else "error")
        try:
            rt._save_state()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
        return res

    eid = _entity(rt)
    if not eid:
        return done("ten typ falownika nie ma w EMS encji prądu ładowania — test niedostępny")
    res["entity"] = eid
    st = rt.hass.states.get(eid)
    v0 = _fnum(st)
    if st is None or v0 is None:
        return done(f"encja {eid} jest niedostępna albo nie ma wartości liczbowej")
    if rt.brand_test_mode():
        return done("włączony tryb próbny — komendy nie są zapisywane, więc test niczego by nie sprawdził")
    attrs = st.attributes or {}
    try:
        mn, mx = float(attrs.get("min")), float(attrs.get("max"))
        step = float(attrs.get("step") or 1.0)
    except (TypeError, ValueError):
        return done(f"encja {eid} nie podaje zakresu (min/max) — nie wiem, jaką wartość bezpiecznie ustawić")
    v1 = v0 + step if v0 + step <= mx + 1e-9 else v0 - step
    if v1 < mn - 1e-9 or abs(v1 - v0) < 1e-9:
        return done(f"zakres encji {eid} ({mn:g}–{mx:g}) nie pozwala na bezpieczną zmianę o jeden krok")
    v1 = int(v1) if float(v1).is_integer() else round(v1, 2)
    v0w = int(v0) if float(v0).is_integer() else round(v0, 2)
    res.update({"from": v0w, "to": v1})
    set_s = restore_s = None
    err_txt = ""
    async with rt._lock:  # noqa: SLF001 — nie wchodzimy w paradę innym komendom
        try:
            await rt._call("number", eid, v1)  # noqa: SLF001
            set_s = await _wait_for(rt, eid, float(v1), sleep)
        except Exception as err:  # noqa: BLE001
            err_txt = str(err)
        finally:
            try:
                await rt._call("number", eid, v0w)  # noqa: SLF001
                restore_s = await _wait_for(rt, eid, float(v0w), sleep)
            except Exception as err:  # noqa: BLE001
                err_txt = (err_txt + "; " if err_txt else "") + f"przywracanie: {err}"
    res.update({"set_s": set_s, "restore_s": restore_s})
    if err_txt:
        return done(f"błąd zapisu: {err_txt}")
    if set_s is None:
        return done(f"falownik nie potwierdził zmiany {eid} z {v0w} na {v1} w ciągu {WAIT_S:.0f} s (komenda nie dotarła albo odczyt jest opóźniony)")
    if restore_s is None:
        return done(f"zmiana zadziałała ({set_s} s), ale przywrócenie {v0w} nie zostało potwierdzone w {WAIT_S:.0f} s — sprawdź ręcznie {eid}")
    return done(f"działa: {eid} {v0w} → {v1} potwierdzone po {set_s} s, przywrócone po {restore_s} s", True)
