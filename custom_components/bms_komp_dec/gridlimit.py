"""Ochrona przyłącza: ograniczanie mocy ładowania baterii z sieci.

Dwa ustawienia (liczby w zakładce EMS, 0 = wyłączone, każdy ustawia własne wartości — limity przyłączy są różne):
- „Moc ładowania z sieci” (kW): stały sufit; EMS wpisuje do falownika odpowiedni prąd (A = kW / napięcie baterii),
  a plan liczy okna ładowania z tą mocą (niższa moc = dłuższe okno);
- „Limit poboru z sieci” (kW): gdy pobór (dom + ładowanie) przekracza limit, EMS na bieżąco zmniejsza prąd ładowania
  z sieci, a gdy jest zapas — przywraca go do sufitu (albo do wartości, którą użytkownik miał przed redukcją).

Reaguje co ok. 10 s (falownik i licznik odświeżają się wolniej), więc krótki szczyt może się jeszcze zdarzyć.
Działa tylko na Deye (encja „Battery Grid Charging Current”)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.util import dt as dt_util

from . import brands
from . import inverter_ctl as ictl
from .const import CONF_BATTERY_VOLTAGE
from .helpers import number_value, state_float

_LOGGER = logging.getLogger(__name__)

MIN_A = 5.0               # nie schodzimy poniżej — ładowanie nie ma być „zamrożone” przez chwilowy szczyt
MIN_WRITE_GAP_S = 20.0    # najczęściej co tyle sekund jedna zmiana
HEADROOM_KW = 0.5         # zapas pod limitem przy przywracaniu prądu
OVER_MARGIN_KW = 0.3      # redukcja z naddatkiem, by nie trzeba było poprawiać co chwilę
CHARGING_W = 200.0        # poniżej tej mocy ładowania redukcja prądu nic nie da
NOTE_GAP_S = 3600.0


def grid_charge_current_eid(hass, cfg: dict[str, Any]) -> str | None:
    """Encja „Battery Grid Charging Current” (number) falownika Deye — po prefiksie encji trybu pracy albo po końcówce."""
    tails = ("battery_grid_charging_current", "grid_charging_current", "grid_charge_current")
    prefix = ictl.prefix_of(ictl.resolve(hass, cfg, "work_mode"))
    for t in tails:
        eid = f"number.{prefix}_{t}"
        if hass.states.get(eid) is not None:
            return eid
    try:
        for eid in hass.states.async_entity_ids("number"):
            obj = eid.split(".", 1)[1]
            if any(obj == t or obj.endswith("_" + t) for t in tails):
                return eid
    except Exception:  # noqa: BLE001
        pass
    return None


def plan_decision(cur: float, ceiling: float | None, base: float, p_w: float | None, charging_w: float,
                  limit_kw: float, v: float) -> tuple[float, str]:
    """Czysta decyzja: (docelowy prąd w A, powód: 'ceiling'|'reduce'|'restore'|'hold'|'cannot')."""
    ceil_a = ceiling if ceiling else base
    if limit_kw <= 0 or p_w is None:
        return (ceil_a, "ceiling") if abs(cur - ceil_a) >= 1.0 else (cur, "hold")
    over_w = p_w - limit_kw * 1000.0
    if over_w > 0:
        if charging_w < CHARGING_W:
            return cur, "cannot"                      # to dom przekracza limit — ładowanie nie jest przyczyną
        want = max(MIN_A, cur - (over_w + OVER_MARGIN_KW * 1000.0) / v)
        want = min(want, ceil_a)
        return (want, "reduce") if cur - want >= 1.0 else (cur, "cannot" if cur <= MIN_A + 0.5 else "hold")
    if -over_w > (HEADROOM_KW + 0.5) * 1000.0 and cur < ceil_a - 0.5:
        want = min(ceil_a, cur + (-over_w - HEADROOM_KW * 1000.0) / v)
        return (want, "restore") if want - cur >= 1.0 else (cur, "hold")
    if cur > ceil_a + 0.5:
        return ceil_a, "ceiling"
    return cur, "hold"


class GridLimiter:
    def __init__(self, rt) -> None:
        self.rt = rt
        self._last_write = 0.0
        self._last_note = 0.0

    async def _restore_base(self, gl: dict) -> None:
        rt = self.rt
        eid = grid_charge_current_eid(rt.hass, rt.cfg)
        cur = state_float(rt.hass, eid) if eid else None
        if cur is None or abs(cur - float(gl["auto"])) > 1.0:
            return                                   # ktoś zmienił ręcznie — nie nadpisujemy
        base = float(gl["base"])
        try:
            async with rt._lock:  # noqa: SLF001
                await rt._call("number", eid, base)  # noqa: SLF001
            rt.log.add("guard", f"Ochrona przyłącza wyłączona: przywrócono prąd ładowania z sieci {base:.0f} A", "info")
        except Exception as err:  # noqa: BLE001
            rt.log.add("guard", f"Ochrona przyłącza: nie udało się przywrócić {eid}: {err}", "error")

    async def tick(self, now) -> None:
        rt = self.rt
        hass = rt.hass
        limit_kw = number_value(hass, "grid_import_limit_kw", 0.0)
        cap_kw = number_value(hass, "grid_charge_power_kw", 0.0)
        gl = rt.state.setdefault("grid_limit", {})
        if limit_kw <= 0 and cap_kw <= 0:
            if gl.get("auto") is not None and gl.get("base") and rt.brand() == brands.DEYE:
                await self._restore_base(gl)      # wyłączono ochronę po redukcji — oddajemy prąd sprzed redukcji
            if gl:
                gl.clear()
            return
        if rt.brand() != brands.DEYE:
            return
        eid = grid_charge_current_eid(hass, rt.cfg)
        cur = state_float(hass, eid) if eid else None
        v = rt.coordinator.get_float_opt(CONF_BATTERY_VOLTAGE)
        if cur is None or not v or v < 10.0:
            if not gl.get("missing_logged"):
                gl["missing_logged"] = True
                rt.log.add("guard", "Ochrona przyłącza: brak encji „Battery Grid Charging Current” albo napięcia baterii — "
                                    "nie mogę ograniczyć mocy ładowania z sieci.", "warn")
            return
        gl.pop("missing_logged", None)
        # wartość użytkownika (ręcznie ustawiona) pamiętamy jako punkt odniesienia do przywracania
        auto = gl.get("auto")
        if auto is None or abs(cur - float(auto)) > 1.0:
            gl["base"] = cur
            gl["auto"] = None
        base = float(gl.get("base") or cur)
        amax = (hass.states.get(eid).attributes or {}).get("max")
        ceiling = cap_kw * 1000.0 / v if cap_kw > 0 else None
        try:
            if amax is not None:
                ceiling = min(ceiling, float(amax)) if ceiling else None
        except (TypeError, ValueError):
            pass
        p = rt.grid_power()
        data = rt.coordinator.data or {}
        bp = data.get("battery_power")
        try:
            charging_w = float(bp) * int(rt.battery_sign()["sign"]) if bp is not None else 0.0
        except (TypeError, ValueError):
            charging_w = 0.0
        want, why = plan_decision(cur, ceiling, base, p, charging_w, limit_kw, v)
        want = float(int(round(want)))
        ts = now.timestamp() if hasattr(now, "timestamp") else dt_util.now().timestamp()
        if why == "cannot":
            if p is not None and ts - self._last_note >= NOTE_GAP_S:
                self._last_note = ts
                await rt.monitor.notifier.send(
                    "grid_limit", "⚡ EMS: pobór z sieci przekracza limit przyłącza",
                    f"Pobór {p / 1000.0:.1f} kW przy limicie {limit_kw:.1f} kW. Ładowanie z sieci jest już "
                    f"{'ograniczone do minimum' if cur <= MIN_A + 0.5 else 'wyłączone z przyczyny po stronie domu'} "
                    f"— nadwyżkę powoduje zużycie domu.", key="grid_limit", level="warn")
            return
        if abs(want - cur) < 1.0 or ts - self._last_write < MIN_WRITE_GAP_S:
            return
        self._last_write = ts
        try:
            async with rt._lock:  # noqa: SLF001
                await rt._call("number", eid, want)  # noqa: SLF001
        except Exception as err:  # noqa: BLE001
            rt.log.add("guard", f"Ochrona przyłącza: nie udało się ustawić {eid}={want:.0f} A: {err}", "error")
            return
        gl["auto"] = want
        rt._save_state()  # noqa: SLF001
        txt = {"reduce": f"pobór {0 if p is None else p / 1000.0:.1f} kW przekracza limit {limit_kw:.1f} kW",
               "restore": "jest zapas pod limitem", "ceiling": f"sufit mocy ładowania {cap_kw:.1f} kW"}.get(why, why)
        rt.log.add("guard", f"Ochrona przyłącza: prąd ładowania z sieci {cur:.0f} → {want:.0f} A ({txt})",
                   "warn" if why == "reduce" else "info")
