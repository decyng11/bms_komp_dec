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

from . import evdhw
from .helpers import number_value, state_float, switch_on

_LOGGER = logging.getLogger(__name__)

MIN_SWITCH_S = 600          # najkrótszy odstęp między zmianami stanu jednego urządzenia
HOLD_S = 300                # warunek musi trwać tyle, zanim zmienimy stan
HARD_OFF = ("dzienny limit", "warunek", "temperatura", "osiągnięto", "brak odczytu", "cel ", "auto naładowane", "limit przyłącza")   # wyłączamy od razu, bez czekania na odstęp
SESSION_IDLE_S = 600        # sesja EV bez warunku „podłączone” kończy się po tylu sekundach bez poboru
SESSION_MIN_KWH = 0.2       # krótsze sesje nie trafiają do dziennika ani powiadomień
AMPS_MIN_S = 30             # najrzadziej co tyle sekund zmieniamy prąd ładowarki
MANUAL_GRACE_S = 90         # tyle czekamy na odświeżenie stanu przełącznika po naszej komendzie
POWER_UNITS = {"w": 1.0, "kw": 1000.0}


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _hour_costs(curve: dict | None, kw: float) -> tuple[datetime, list[tuple[float, float] | None]] | None:
    """Koszt (zł) i energia z nadwyżki PV (kWh) pracy urządzenia o mocy `kw` w kolejnych godzinach planu; None = brak ceny zakupu."""
    if not curve or not curve.get("start"):
        return None
    try:
        t0 = datetime.fromisoformat(str(curve["start"]))
    except ValueError:
        return None
    pv, load = curve.get("pv") or [], curve.get("load") or []
    buy, sell = curve.get("buy") or [], curve.get("sell") or []
    n = min(len(pv), len(load), len(buy))
    e = max(0.01, kw)
    out: list[tuple[float, float] | None] = []
    for h in range(n):
        b = _f(buy[h])
        if b is None:
            out.append(None)
            continue
        sl = _f(sell[h]) if h < len(sell) else None
        sur = max(0.0, (_f(pv[h]) or 0.0) - (_f(load[h]) or 0.0))
        from_pv = min(e, sur)
        out.append((from_pv * max(0.0, sl if sl is not None else 0.0) + (e - from_pv) * b, from_pv))
    return t0, out


def best_window(curve: dict | None, hours: float, kw: float, deadline: datetime | None = None) -> tuple[datetime, datetime, float, float] | None:
    """Najtańszy ciągły blok `hours` godzin w planie 24 h (energia z nadwyżki PV po cenie sprzedaży, reszta po cenie
    zakupu). Zwraca (początek, koniec, koszt zł, kWh z PV). Z `deadline` blok musi się skończyć najpóźniej o tej porze."""
    hc = _hour_costs(curve, kw)
    if hc is None:
        return None
    t0, costs = hc
    span = max(1, int(math.ceil(hours)))
    best = None
    for s in range(0, max(0, len(costs) - span + 1)):
        window = costs[s:s + span]
        if any(c is None for c in window):
            continue
        if deadline is not None and t0 + timedelta(hours=s + span) > deadline:
            break
        cost = sum(c[0] for c in window)
        pv_used = sum(c[1] for c in window)
        if best is None or cost < best[1] - 1e-9:
            best = (s, cost, pv_used)
    if best is None:
        return None
    s, cost, pv_used = best
    start = t0 + timedelta(hours=s)
    return start, start + timedelta(hours=span), round(cost, 2), round(pv_used, 2)


def cheapest_slots(curve: dict | None, hours: float, kw: float, deadline: datetime | None = None,
                   horizon_h: float = 24.0, not_before: datetime | None = None) -> tuple[list[datetime], float, float] | None:
    """`hours` najtańszych godzin planu (nie muszą być sąsiednie — auto, bojler), tylko takie, które kończą się przed `deadline`
    (bez terminu: w ciągu `horizon_h` od początku planu). Zwraca (początki godzin po kolei, koszt zł, kWh z PV); gdy do terminu jest
    mniej godzin niż trzeba — wszystkie dostępne. `not_before` (teraz) odrzuca godziny już zakończone — nieodświeżony plan nie
    może dać zestawu z przeszłości. None = brak planu z cenami."""
    hc = _hour_costs(curve, kw)
    if hc is None:
        return None
    t0, costs = hc
    span = max(1, int(math.ceil(hours)))
    limit = deadline if deadline is not None else t0 + timedelta(hours=horizon_h)
    cand = [(c[0], i, c[1]) for i, c in enumerate(costs)
            if c is not None and t0 + timedelta(hours=i + 1) <= limit and (not_before is None or t0 + timedelta(hours=i + 1) > not_before)]
    if not cand:
        return None
    pick = sorted(cand)[:span]
    pick.sort(key=lambda x: x[1])
    return [t0 + timedelta(hours=i) for _c, i, _p in pick], round(sum(c for c, _i, _p in pick), 2), round(sum(p for _c, _i, p in pick), 2)


def _ranges(starts: list[datetime]) -> str:
    """Kolejne godziny zwinięte w przedziały: „02:00–04:00, 05:00–06:00”."""
    out: list[list[datetime]] = []
    for t in sorted(starts):
        if out and t == out[-1][1]:
            out[-1][1] = t + timedelta(hours=1)
        else:
            out.append([t, t + timedelta(hours=1)])
    return ", ".join(f"{dt_util.as_local(a):%H:%M}–{dt_util.as_local(b):%H:%M}" for a, b in out)


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
            cond_ok, cond_why = self.cond_state(d)
            out[d["id"]] = {"mode": d["ctl_mode"], "switch": d["switch_eid"], "state": sw.state if sw else None,
                            "cond": ({"eid": d["ctl_cond_eid"], "ok": cond_ok, "why": cond_why} if d.get("ctl_cond_eid") else None),
                            "owned": rec.get("cmd") == "on", "manual": bool(rec.get("manual")),
                            "reason": rec.get("reason"), "on_h": round(float(rec.get("on_s") or 0.0) / 3600.0, 2),
                            "window": rec.get("window"), "last": rec.get("last"),
                            "sess": ({"kwh": round(float((rec.get("sess") or {}).get("kwh") or 0.0), 2), "cost": round(float((rec.get("sess") or {}).get("cost") or 0.0), 2)} if rec.get("sess") else None),
                            "last_sess": rec.get("last_sess"), "amps": rec.get("amps"), "temp": rec.get("temp"), "dhw_target": rec.get("dhw_target"),
                            "leg_week": rec.get("leg_week"), "need_h": rec.get("need_h")}
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

    def cond_state(self, d: dict) -> tuple[bool, str | None]:
        """Warunek uruchomienia urządzenia (np. „auto podłączone”): (spełniony, powód niespełnienia).

        Bez warunku zawsze spełniony. Encja niedostępna albo nieznana = niespełniony (lepiej nie włączyć niż włączyć w ciemno)."""
        eid = str(d.get("ctl_cond_eid") or "")
        if not eid:
            return True, None
        allowed = [x for x in str(d.get("ctl_cond_states") or "on").split(",") if x] or ["on"]
        st = self.hass.states.get(eid)
        name = str(((st.attributes or {}).get("friendly_name") if st is not None else None) or eid)
        if st is None or str(st.state).lower() in ("unknown", "unavailable", "none", ""):
            return False, f"warunek: {name} niedostępny"
        cur = str(st.state).strip().lower()
        if cur in allowed:
            return True, None
        return False, f"warunek: {name} = {cur} (potrzebne: {' lub '.join(allowed)})"

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
            if d.get("category") == "ev":
                await self._ev_session(d, rec, now)
                self._ev_need(d, rec)
            want, why = self._decide(d, rec, now, is_on, owned, grid, soc, plan_curve)
            want, why = self._kind_gates(d, rec, now, want, why, is_on, owned, grid, soc, plan_curve)
            limit_h = float(d.get("ctl_max_h") or 0.0)
            if want and limit_h > 0 and float(rec.get("on_s") or 0.0) >= limit_h * 3600.0:
                want, why = False, f"dzienny limit pracy {limit_h:g} h"
            if want and outage:
                want, why = False, "zanik sieci"
            if want:
                cond_ok, cond_why = self.cond_state(d)
                if not cond_ok:
                    want, why = False, str(cond_why)
            rec["reason"] = why
            can_switch = ts - float(rec.get("ts") or 0.0) >= MIN_SWITCH_S
            if want and not is_on and can_switch:
                await self._switch(d, rec, True, why, now)
            elif not want and is_on and owned and (can_switch or outage or why.startswith(HARD_OFF)):
                await self._switch(d, rec, False, why, now)
            if d.get("category") == "ev" and d.get("ev_current_eid"):
                await self._ev_regulate(d, rec, now, want, is_on, owned, grid)
            if d.get("dhw_setpoint_eid"):
                await self._dhw_setpoint(d, rec, now, want and is_on)

    # ------------------------------------------------------------ EV: sesja, cel, prąd
    def _ev_need(self, d: dict, rec: dict) -> None:
        """Ile godzin ładowania brakuje do celu (dla trybu najtańszych godzin); bez celu zostają godziny z ustawień."""
        car = state_float(self.hass, d["ev_soc_eid"]) if d.get("ev_soc_eid") else None
        h = evdhw.ev_hours_needed(d.get("ev_target_kwh"), (rec.get("sess") or {}).get("kwh"), car, d.get("ev_target_pct"), d.get("ev_car_kwh"), d.get("ctl_power_w"))
        if h is None or h <= 0:
            rec.pop("need_h", None)
        else:
            rec["need_h"] = min(12.0, max(0.5, h))

    async def _ev_session(self, d: dict, rec: dict, now: datetime) -> None:
        """Sesja ładowania: energia i szacowany koszt (cena zakupu × energia); koniec, gdy auto odłączone albo długo bez poboru."""
        ts = now.timestamp()
        has_cond = bool(d.get("ctl_cond_eid"))
        p = self._power_w(d)
        active = self.cond_state(d)[0] if has_cond else (p is not None and p > 50.0)
        sess = rec.get("sess")
        if active and not sess:
            rec["sess"] = sess = {"t0": ts, "kwh": 0.0, "cost": 0.0, "last": ts}
        if not sess:
            return
        dt = ts - float(sess.get("last") or ts)
        sess["last"] = ts
        if p is not None and 0 < dt <= 180:
            e = max(0.0, p) * dt / 3_600_000.0
            sess["kwh"] = float(sess.get("kwh") or 0.0) + e
            price = self.rt.buy_price_signed()
            if price is not None:
                sess["cost"] = float(sess.get("cost") or 0.0) + e * price
        if active:
            sess.pop("idle", None)
            return
        end = has_cond
        if not has_cond:
            idle = sess.setdefault("idle", ts)
            end = ts - float(idle) >= SESSION_IDLE_S
        if not end:
            return
        rec.pop("sess", None)
        kwh, cost = float(sess.get("kwh") or 0.0), float(sess.get("cost") or 0.0)
        if kwh < SESSION_MIN_KWH:
            return
        rec["last_sess"] = {"end": dt_util.as_local(now).isoformat(timespec="minutes"), "kwh": round(kwh, 2), "cost": round(cost, 2),
                            "min": round((ts - float(sess.get("t0") or ts)) / 60.0)}
        self.rt.log.add("devices", f"{d['name']}: sesja ładowania zakończona — {kwh:.1f} kWh, ok. {cost:.2f} zł", "ok")
        self.rt._save_state()  # noqa: SLF001
        await self.rt.monitor.notifier.send("ev_session", "🚗 EMS: koniec sesji ładowania",
                                            f"{d['name']}: {kwh:.1f} kWh w ok. {rec['last_sess']['min']} min, szacunkowo {cost:.2f} zł "
                                            "(cena zakupu × energia, bez uwzględnienia własnego PV).", key=d["id"], level="info")

    async def _set_number(self, eid: str, value: float, rec: dict, key: str, now: datetime, min_s: float) -> bool:
        ts = now.timestamp()
        if rec.get(key) == value or ts - float(rec.get(key + "_ts") or 0.0) < min_s:
            return False
        try:
            await self.hass.services.async_call("number", "set_value", {"entity_id": eid, "value": value}, blocking=False)
        except Exception as err:  # noqa: BLE001
            self.rt.log.add("devices", f"nie udało się ustawić {eid} na {value:g} ({err})", "error")
            return False
        rec[key], rec[key + "_ts"] = value, ts
        return True

    async def _ev_regulate(self, d: dict, rec: dict, now: datetime, want: bool, is_on: bool, owned: bool, grid: float | None) -> None:
        """Prąd ładowarki: za nadwyżką PV (tryb pv) albo maksymalny (pozostałe), zawsze pod limitem przyłącza."""
        if not (want and (is_on or rec.get("cmd") == "on")):
            return
        volts, ph, lo, hi = d["ev_volts"], d["ev_phases"], d["ev_min_a"], d["ev_max_a"]
        p_own = self._power_w(d)
        if d["ctl_mode"] == "pv":
            if grid is None:
                return
            own = (p_own if p_own is not None else float(d["ctl_power_w"])) if (is_on and owned) else 0.0
            amps = evdhw.amps_for_power(own - grid, volts, ph, lo, hi) or int(lo)        # pauzę przy braku nadwyżki robi tryb pv (z histerezą)
        else:
            amps = int(hi)
        if d.get("ev_grid_limit_w") and grid is not None:
            lim = evdhw.limit_amps(amps, max(0.0, grid), d["ev_grid_limit_w"], p_own or 0.0, volts, ph, lo)
            if lim <= 0 and amps > 0:
                rec["reason"] = f"limit przyłącza {d['ev_grid_limit_w']:.0f} W — za mało miejsca na ładowanie"
                if is_on and owned:
                    await self._switch(d, rec, False, rec["reason"], now)
                return
            amps = lim
        await self._set_number(d["ev_current_eid"], float(amps), rec, "amps", now, AMPS_MIN_S)

    # ------------------------------------------------------------ bramki rodzaju urządzenia (EV, CWU)
    def _kind_gates(self, d: dict, rec: dict, now: datetime, want: bool, why: str, is_on: bool, owned: bool,
                    grid: float | None, soc: float | None, curve: dict | None) -> tuple[bool, str]:
        loc = dt_util.as_local(now)
        if d.get("category") == "ev":
            car = state_float(self.hass, d["ev_soc_eid"]) if d.get("ev_soc_eid") else None
            done, dwhy = evdhw.ev_goal((rec.get("sess") or {}).get("kwh"), d.get("ev_target_kwh"), car, d.get("ev_target_pct"))
            if done:
                return False, str(dwhy)
            floor = float(d.get("ev_soc_floor") or 0.0)
            if want and floor > 0 and d["ctl_mode"] in ("now", "cheap") and soc is not None and soc < floor:
                return False, f"bateria domu {soc:.0f}% poniżej {floor:.0f}%"
            return want, why
        if not any(d.get(k) for k in ("dhw_temp_eid", "dhw_comfort_c", "dhw_max_c", "dhw_boost_c", "dhw_leg")):
            return want, why
        temp = state_float(self.hass, d["dhw_temp_eid"]) if d.get("dhw_temp_eid") else None
        leg_due = bool(d.get("dhw_leg")) and evdhw.legionella_due(loc, d.get("dhw_leg_dow"), rec.get("leg_week"))
        g = evdhw.dhw_decide(temp, loc, d, leg_due)
        rec["temp"] = evdhw.sane_temp(temp)
        rec["dhw_target"] = g.get("target")
        if g.get("leg_done"):
            rec["leg_week"] = evdhw.week_key(loc)
            self.rt.log.add("devices", f"{d['name']}: antylegionella wykonana ({rec['temp']} °C)", "ok")
            self.rt._save_state()  # noqa: SLF001
        if g["block"] and not g["force"]:
            return False, str(g["reason"])
        if g["force"]:
            return True, str(g["reason"])
        if g.get("leg"):
            w2, _y2 = self._decide(dict(d, ctl_mode="cheap"), rec, now, is_on, owned, grid, soc, curve)
            if w2 or loc.hour >= 21:
                return True, f"{g['reason']}" + (" (najtańsze godziny)" if w2 else " (po 21:00, domykam)")
        return want, why

    async def _dhw_setpoint(self, d: dict, rec: dict, now: datetime, boosting: bool) -> None:
        """Pompa ciepła: temperatura zadana wysoka podczas grzania „na zapas”, niska poza nim."""
        val = float(d["dhw_sp_hi"] if boosting else d["dhw_sp_lo"])
        if val > 0:
            await self._set_number(d["dhw_setpoint_eid"], val, rec, "sp", now, 300.0)

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
        # ujemna cena zakupu: tryb „neg” albo dodatkowo do „pv”/„cheap” — dostajemy zapłatę za pobór, więc włączamy odbiornik
        if d["ctl_mode"] == "neg" or d.get("ctl_neg"):
            thr = float(d.get("ctl_neg_price") or 0.0)
            price = self.rt.buy_price_signed()
            neg = price is not None and price < thr
            if neg:
                why = f"cena zakupu {price:+.2f} zł/kWh (< {thr:+.2f})"
                if (is_on and owned) or self._held(rec, "neg_on", True, ts):
                    return True, why
                if d["ctl_mode"] == "neg":
                    return False, f"{why} — potwierdzam przez 5 min"
            else:
                rec.pop("neg_on", None)
                if d["ctl_mode"] == "neg":
                    return False, ("brak ceny zakupu" if price is None else f"czeka na cenę zakupu < {thr:+.2f} zł/kWh (jest {price:+.2f})")
        if d["ctl_mode"] == "neg":
            return False, "czeka na ujemną cenę zakupu"
        if d["ctl_mode"] == "now":
            return True, "natychmiast"
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
        deadline = self._deadline(now, d)
        if d.get("ctl_split"):
            return self._decide_split(d, rec, now, curve, need, deadline)
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
            bw = best_window(curve, float(rec.get("need_h") or d.get("ctl_hours") or 2.0), need / 1000.0, deadline)
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
        if deadline is not None and curve:
            return False, f"brak tak taniego okna przed {dt_util.as_local(deadline):%H:%M}"
        return False, "brak planu z cenami"

    @staticmethod
    def _deadline(now: datetime, d: dict) -> datetime | None:
        """Najbliższa pora „gotowe do godziny X” po `now` (ctl_ready_h = 0: bez terminu)."""
        try:
            rh = int(d.get("ctl_ready_h") or 0)
        except (TypeError, ValueError):
            return None
        if not 1 <= rh <= 23:
            return None
        loc = dt_util.as_local(now)
        dl = loc.replace(hour=rh, minute=0, second=0, microsecond=0)
        return dl if dl > loc else dl + timedelta(days=1)

    def _decide_split(self, d: dict, rec: dict, now: datetime, curve: dict | None, need: float,
                      deadline: datetime | None) -> tuple[bool, str]:
        """Najtańsze godziny z przerwami: zestaw godzin wybieramy raz na „okres” (do terminu albo 24 h) i go nie zmieniamy,
        żeby plan nie przestawiał godzin w trakcie. Nowy zestaw dopiero po końcu okresu."""
        slots: list[datetime] = []
        for x in rec.get("slots") or []:
            try:
                slots.append(datetime.fromisoformat(str(x)))
            except ValueError:
                continue
        try:
            period_end = datetime.fromisoformat(str(rec.get("slots_end"))) if rec.get("slots_end") else None
        except ValueError:
            period_end = None
        if period_end is None or now >= period_end:
            slots, period_end = [], None
            rec["slots"], rec["slots_end"] = None, None
        if not slots:
            hours = float(rec.get("need_h") or d.get("ctl_hours") or 2.0)
            got = cheapest_slots(curve, hours, need / 1000.0, deadline, not_before=now)
            if got is None:
                return False, ("brak godzin przed terminem" if (deadline is not None and curve) else "brak planu z cenami")
            slots = got[0]
            period_end = deadline if deadline is not None else now + timedelta(hours=24)
            rec["slots"] = [t.isoformat() for t in slots]
            rec["slots_end"] = period_end.isoformat()
            rec["slots_cost"] = got[1]
        upcoming = [t for t in slots if t + timedelta(hours=1) > now]
        if any(t <= now < t + timedelta(hours=1) for t in slots):
            return True, f"najtańsze godziny {_ranges(slots)}" + (f" (gotowe przed {dt_util.as_local(deadline):%H:%M})" if deadline else "")
        if upcoming:
            return False, f"czeka na godziny {_ranges(upcoming)}"
        return False, "zaplanowane godziny minęły — następny zestaw od końca okresu"
