"""Sterowanie dodatkowymi urządzeniami: włączanie przełącznika przy nadwyżce PV albo w najtańszych godzinach.

Działa tylko przy włączonym switch.bms_device_control (domyślnie wyłączony) i tylko dla urządzeń, którym w zakładce
Urządzenia wskazano przełącznik (switch / input_boolean) i tryb. Zasady bezpieczeństwa:
  • stan zmieniamy najwyżej co 10 minut, a warunek musi trwać 5 minut (bez „migania”),
  • wyłączamy tylko to, co sami włączyliśmy — urządzenia włączonego ręcznie nie ruszamy,
  • gdy ktoś przełączy urządzenie ręcznie wbrew EMS, EMS nie steruje nim do końca dnia,
  • przy zaniku sieci niczego nie włączamy, a to, co włączyliśmy, wyłączamy,
  • dzienny limit czasu pracy (ctl_max_h) wyłącza urządzenie po jego przekroczeniu,
  • po wyłączeniu głównego przełącznika wyłączamy urządzenia, które EMS włączył,
  • oszczędzanie energii: gdy SOC spadnie poniżej progu (device_shed_soc), wyłączamy wszystkie urządzenia z przełącznikiem
    poza oznaczonymi „nie dotyczy” (ctl_no_shed) i włączamy z powrotem po odbiciu SOC o 5 pkt (tylko te, które były włączone),
  • każda akcja trafia do dziennika decyzji.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .helpers import number_value, state_float, switch_on

_LOGGER = logging.getLogger(__name__)

MIN_SWITCH_S = 600          # najkrótszy odstęp między zmianami stanu jednego urządzenia
HOLD_S = 300                # warunek musi trwać tyle, zanim zmienimy stan
MANUAL_GRACE_S = 90         # tyle czekamy na odświeżenie stanu przełącznika po naszej komendzie
POWER_UNITS = {"w": 1.0, "kw": 1000.0}


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def best_window(curve: dict | None, hours: float, kw: float) -> tuple[datetime, datetime, float, float] | None:
    """Najtańszy ciągły blok `hours` godzin w planie 24 h (energia z nadwyżki PV po cenie sprzedaży, reszta po cenie
    zakupu). Zwraca (początek, koniec, koszt zł, kWh z PV)."""
    if not curve or not curve.get("start"):
        return None
    try:
        t0 = datetime.fromisoformat(str(curve["start"]))
    except ValueError:
        return None
    pv, load = curve.get("pv") or [], curve.get("load") or []
    buy, sell = curve.get("buy") or [], curve.get("sell") or []
    n = min(len(pv), len(load), len(buy))
    span = max(1, int(math.ceil(hours)))
    e = max(0.01, kw)
    best = None
    for s in range(0, max(0, n - span + 1)):
        cost, pv_used, ok = 0.0, 0.0, True
        for h in range(s, s + span):
            b = _f(buy[h])
            if b is None:
                ok = False
                break
            sl = _f(sell[h]) if h < len(sell) else None
            sur = max(0.0, (_f(pv[h]) or 0.0) - (_f(load[h]) or 0.0))
            from_pv = min(e, sur)
            pv_used += from_pv
            cost += from_pv * max(0.0, sl if sl is not None else 0.0) + (e - from_pv) * b
        if ok and (best is None or cost < best[1] - 1e-9):
            best = (s, cost, pv_used)
    if best is None:
        return None
    s, cost, pv_used = best
    start = t0 + timedelta(hours=s)
    return start, start + timedelta(hours=span), round(cost, 2), round(pv_used, 2)


class DeviceController:
    def __init__(self, rt) -> None:
        self.rt = rt
        self.hass = rt.hass

    # ------------------------------------------------------------ stan
    def _st(self) -> dict[str, Any]:
        st = self.rt.state.get("dev_ctl")
        if not isinstance(st, dict):
            st = {}
            self.rt.state["dev_ctl"] = st
        return st

    def enabled(self) -> bool:
        return switch_on(self.hass, "device_control", False)

    def status(self) -> dict[str, Any]:
        """Dla karty: stan sterowania każdego urządzenia."""
        out = {}
        st = self._st()
        for d in self.rt.devices.devices:
            if d.get("ctl_mode", "off") == "off" or not d.get("switch_eid"):
                continue
            rec = st.get(d["id"]) or {}
            sw = self.hass.states.get(d["switch_eid"])
            out[d["id"]] = {"mode": d["ctl_mode"], "switch": d["switch_eid"], "state": sw.state if sw else None,
                            "owned": rec.get("cmd") == "on", "manual": bool(rec.get("manual")),
                            "reason": rec.get("reason"), "on_h": round(float(rec.get("on_s") or 0.0) / 3600.0, 2),
                            "window": rec.get("window"), "last": rec.get("last")}
        return {"enabled": self.enabled(), "devices": out}

    # ------------------------------------------------------------ akcje
    async def _switch(self, d: dict, rec: dict, on: bool, why: str, now: datetime) -> None:
        eid = d["switch_eid"]
        domain = eid.split(".", 1)[0]
        try:
            await self.hass.services.async_call(domain, "turn_on" if on else "turn_off", {"entity_id": eid}, blocking=False)
        except Exception as err:  # noqa: BLE001
            self.rt.log.add("devices", f"{d['name']}: nie udało się {'włączyć' if on else 'wyłączyć'} ({err})", "error")
            return
        rec["cmd"] = "on" if on else "off"
        rec["ts"] = now.timestamp()
        rec.pop("since_on", None)
        rec.pop("since_off", None)
        rec["last"] = f"{dt_util.as_local(now):%H:%M} {'wł.' if on else 'wył.'}: {why}"
        rec["reason"] = why
        self.rt.log.add("devices", f"{d['name']}: {'włączono' if on else 'wyłączono'} — {why}", "ok")
        self.rt._save_state()  # noqa: SLF001

    def _power_w(self, d: dict) -> float | None:
        eid = d.get("power_eid")
        if not eid:
            return None
        st = self.hass.states.get(eid)
        v = state_float(self.hass, eid)
        if v is None or st is None:
            return None
        unit = str((st.attributes or {}).get("unit_of_measurement") or "W").strip().lower()
        return v * POWER_UNITS.get(unit, 1.0)

    # ------------------------------------------------------------ oszczędzanie energii przy niskim SOC
    SHED_RESTORE_PTS = 5.0

    async def _shed_tick(self, now: datetime) -> None:
        thr = number_value(self.hass, "device_shed_soc", 0.0)
        soc = self.rt.soc()
        ts = now.timestamp()
        day = dt_util.as_local(now).date().isoformat()
        active = self.enabled() and thr > 0
        st = self._st()
        shed_names, back_names = [], []
        for d in self.rt.devices.devices:
            if not d.get("switch_eid"):
                continue
            rec = st.setdefault(d["id"], {})
            sw = self.hass.states.get(d["switch_eid"])
            if sw is None or sw.state not in ("on", "off"):
                continue
            is_on = sw.state == "on"
            if rec.get("shed"):
                if is_on and ts - float(rec.get("ts") or 0.0) > MANUAL_GRACE_S:     # ktoś włączył ręcznie — szanujemy do końca dnia
                    rec.pop("shed", None); rec.pop("shed_was_on", None); rec["shed_skip"] = day
                    rec["reason"] = "włączone ręcznie mimo niskiego SOC"
                    self.rt._save_state()  # noqa: SLF001
                    continue
                back = (not active or d.get("ctl_no_shed")
                        or (soc is not None and soc >= thr + self.SHED_RESTORE_PTS))
                if self._held(rec, "shed_back", back, ts):
                    was_on = bool(rec.get("shed_was_on"))
                    rec.pop("shed", None); rec.pop("shed_was_on", None)
                    if was_on and not is_on:
                        await self._switch(d, rec, True, f"SOC odbił ({soc:.0f}%), koniec oszczędzania" if soc is not None else "koniec oszczędzania", now)
                    rec["cmd"] = None             # nie przejmujemy urządzenia — zwykłe sterowanie trybu liczy od nowa
                    back_names.append(d["name"])
                continue
            if rec.get("shed_skip") == day:
                continue
            low = active and not d.get("ctl_no_shed") and soc is not None and soc < thr
            if not self._held(rec, "shed_low", low, ts):
                continue
            rec.pop("shed_low", None)
            if is_on:
                await self._switch(d, rec, False, f"oszczędzanie energii: SOC {soc:.0f}% < {thr:.0f}%", now)
                rec["cmd"] = None
                rec["shed"] = True
                rec["shed_was_on"] = True
                shed_names.append(d["name"])
                self.rt._save_state()  # noqa: SLF001
        n = self.rt.monitor.notifier
        if shed_names:
            await n.send("device_shed", "🔋 EMS: oszczędzanie energii — urządzenia wyłączone",
                         f"SOC {soc:.0f}% poniżej progu {thr:.0f}%. Wyłączono: {', '.join(shed_names)}. "
                         f"Włączę je z powrotem po SOC ≥ {thr + self.SHED_RESTORE_PTS:.0f}%.", key="shed", level="warn")
        if back_names:
            await n.send("device_shed", "🔋 EMS: koniec oszczędzania energii",
                         f"Włączono z powrotem: {', '.join(back_names)}.", key="shed_back", level="info")

    # ------------------------------------------------------------ co minutę
    async def tick(self, now: datetime) -> None:
        try:
            await self._shed_tick(now)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS urządzenia: oszczędzanie energii: %s", err, exc_info=True)
        devs = [d for d in self.rt.devices.devices if d.get("switch_eid") and d.get("ctl_mode", "off") != "off"]
        st = self._st()
        known = {d["id"] for d in self.rt.devices.devices}
        for did in [k for k in st if k not in known]:
            st.pop(did, None)
        if not devs:
            return
        loc = dt_util.as_local(now)
        day = loc.date().isoformat()
        ts = now.timestamp()
        enabled = self.enabled()
        go = self.rt.state.get("grid_outage") or {}
        outage = go.get("since") is not None
        data = self.rt.coordinator.data or {}
        grid = _f(data.get("grid_power"))
        soc = self.rt.soc()
        plan_curve = (self.rt.plan() or {}).get("curve")
        for d in devs:
            rec = st.setdefault(d["id"], {})
            if rec.get("day") != day:                       # nowy dzień: licznik pracy i blokada ręczna od zera
                rec.update(day=day, on_s=0.0, manual=False)
            sw = self.hass.states.get(d["switch_eid"])
            if sw is None or sw.state not in ("on", "off"):
                rec["reason"] = "przełącznik niedostępny"
                continue
            is_on = sw.state == "on"
            owned = rec.get("cmd") == "on"
            last_tick = _f(rec.get("tick"))
            rec["tick"] = ts
            if owned and is_on and last_tick is not None and 0 < ts - last_tick <= 180:
                rec["on_s"] = float(rec.get("on_s") or 0.0) + (ts - last_tick)
            # główny przełącznik wyłączony: wyłączamy to, co sami włączyliśmy, i nic więcej nie robimy
            if not enabled:
                if owned and is_on:
                    await self._switch(d, rec, False, "sterowanie urządzeniami wyłączone", now)
                elif owned:
                    rec["cmd"] = "off"
                rec["reason"] = "sterowanie wyłączone"
                continue
            # ręczne przełączenie wbrew EMS (po czasie na odświeżenie stanu) → do końca dnia bez sterowania
            if (rec.get("cmd") in ("on", "off") and is_on != (rec["cmd"] == "on")
                    and ts - float(rec.get("ts") or 0.0) > MANUAL_GRACE_S and not rec.get("manual")):
                rec["manual"] = True
                rec["cmd"] = None
                rec["reason"] = "przełączone ręcznie — EMS nie steruje do końca dnia"
                self.rt.log.add("devices", f"{d['name']}: przełączone ręcznie — EMS nie steruje nim do końca dnia", "info")
                self.rt._save_state()  # noqa: SLF001
                continue
            if rec.get("manual"):
                continue
            if rec.get("shed"):
                rec["reason"] = "oszczędzanie energii (niski SOC)"
                continue
            want, why = self._decide(d, rec, now, is_on, owned, grid, soc, plan_curve)
            limit_h = float(d.get("ctl_max_h") or 0.0)
            if want and limit_h > 0 and float(rec.get("on_s") or 0.0) >= limit_h * 3600.0:
                want, why = False, f"dzienny limit pracy {limit_h:g} h"
            if want and outage:
                want, why = False, "zanik sieci"
            rec["reason"] = why
            can_switch = ts - float(rec.get("ts") or 0.0) >= MIN_SWITCH_S
            if want and not is_on and can_switch:
                await self._switch(d, rec, True, why, now)
            elif not want and is_on and owned and (can_switch or outage or why.startswith("dzienny limit")):
                await self._switch(d, rec, False, why, now)

    def _held(self, rec: dict, key: str, cond: bool, ts: float) -> bool:
        """True, gdy warunek `key` trwa nieprzerwanie co najmniej HOLD_S."""
        if not cond:
            rec.pop(key, None)
            return False
        since = _f(rec.get(key))
        if since is None:
            rec[key] = ts
            return False
        return ts - since >= HOLD_S

    def _decide(self, d: dict, rec: dict, now: datetime, is_on: bool, owned: bool, grid: float | None,
                soc: float | None, curve: dict | None) -> tuple[bool, str]:
        ts = now.timestamp()
        need = float(d.get("ctl_power_w") or 1000.0)
        if d["ctl_mode"] == "pv":
            if grid is None:
                return (is_on and owned), "brak odczytu mocy sieci"
            export = max(0.0, -grid)
            own = (self._power_w(d) if self._power_w(d) is not None else need) if (is_on and owned) else 0.0
            surplus = own - grid                 # nadwyżka bez tego urządzenia (import z sieci ją pomniejsza)
            soc_min = float(d.get("ctl_soc") or 0.0)
            soc_ok = soc is None or soc >= soc_min
            if is_on and owned:
                off = surplus < 0.5 * need or (soc is not None and soc < soc_min - 10.0)
                if self._held(rec, "since_off", off, ts):
                    return False, f"nadwyżka PV spadła ({surplus / 1000:.1f} kW)" if surplus < 0.5 * need else f"SOC {soc:.0f}%"
                return True, f"nadwyżka PV {surplus / 1000:.1f} kW"
            on = surplus >= need and soc_ok
            if self._held(rec, "since_on", on, ts):
                return True, f"nadwyżka PV {surplus / 1000:.1f} kW, SOC {soc:.0f}%" if soc is not None else f"nadwyżka PV {surplus / 1000:.1f} kW"
            if not soc_ok:
                return False, f"czeka na SOC ≥ {soc_min:.0f}%"
            return False, f"czeka na nadwyżkę ≥ {need / 1000:.1f} kW (jest {export / 1000:.1f} kW)"
        # najtańsze godziny
        win = rec.get("window")
        in_win = False
        if isinstance(win, list) and len(win) == 2:
            try:
                ws, we = datetime.fromisoformat(win[0]), datetime.fromisoformat(win[1])
                in_win = ws <= now < we
                if now >= we:
                    win = None
            except ValueError:
                win = None
        else:
            win = None
        if not in_win:                                       # okno wybieramy od nowa tylko poza oknem (nie przesuwamy w trakcie)
            bw = best_window(curve, float(d.get("ctl_hours") or 2.0), need / 1000.0)
            if bw is not None:
                win = [bw[0].isoformat(), bw[1].isoformat()]
                rec["window"] = win
                in_win = bw[0] <= now < bw[1]
            elif win is None:
                rec["window"] = None
        if in_win:
            return True, f"najtańsze godziny {win[0][11:16]}–{win[1][11:16]}"
        if win:
            return False, f"czeka na okno {win[0][11:16]}–{win[1][11:16]}"
        return False, "brak planu z cenami"
