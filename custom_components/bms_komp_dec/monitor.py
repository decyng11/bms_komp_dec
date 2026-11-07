"""Powiadomienia i monitoring zdrowia instalacji.

Wysyła (persistent_notification + opcjonalnie usługa notify, np. aplikacja mobilna) tylko to, co wymaga
reakcji: niski SOC przy progu odcięcia, aktywny alarm/błąd falownika (z opisem kodu Fxx), dryf wartości po
zapisie parametru, brak cen RCE na jutro, utrata łączności z falownikiem. Każde zdarzenie ma własny
„cooldown”, a czasy ostatnich wysyłek są zapamiętywane (restart HA nie powtarza powiadomień).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from . import inverter_ctl as ictl
from . import notify_cfg as ncfg
from .const import CONF_BATTERY_TEMPERATURE, CONF_GRID_POWER, CONF_GRID_VOLTAGE_L1
from .helpers import switch_on
from .tariff import get_profile, next_offpeak_window

_LOGGER = logging.getLogger(__name__)

NOTIFY_ID_PREFIX = "bms_"
LOW_SOC_COOLDOWN_S = 6 * 3600
ALARM_COOLDOWN_S = 3600
RCE_COOLDOWN_S = 20 * 3600
COMM_COOLDOWN_S = 3 * 3600
COMM_LOSS_AFTER_S = 600
RCE_CHECK_FROM_HOUR = 18          # ceny na jutro bywają publikowane dopiero po południu
LOW_SOC_MIN_THRESHOLD = 12.0      # gdy nie znamy progu falownika: HARD_FLOOR (10) + 2

# Opisy kodów błędów hybryd NISKONAPIĘCIOWYCH Deye (SG01LP1 / SG03LP1 / SG04LP3 / SG05LP1) wg instrukcji producenta.
# W innych seriach znaczenia bywają inne (HP3: F42 = niezgodne wersje równoległe, F46 = zbyt niskie napięcie AC,
# F56 = zbyt niskie napięcie baterii 1; falowniki sieciowe: F29 = przełącznik obciążenia AC) — stąd FAULT_NOTE.
FAULT_NOTE = ("Opis kodu dotyczy hybryd niskonapięciowych Deye (SG01LP1/SG03LP1/SG04LP3/SG05LP1). W innych modelach "
              "(np. wysokonapięciowe HP3, falowniki sieciowe) znaczenie kodu bywa inne — sprawdź instrukcję swojego modelu.")
FAULT_TEXT = {
    "F13": "Zmiana trybu pracy", "F18": "Nadprądowy błąd sprzętowy AC", "F20": "Nadprądowy błąd sprzętowy DC",
    "F23": "Przejściowy prąd upływu (GFCI)", "F24": "Błąd izolacji DC", "F26": "Niezbalansowana szyna DC",
    "F29": "Błąd magistrali równoległej CAN", "F35": "Brak sieci AC", "F41": "Zatrzymany system równoległy",
    "F42": "Zbyt niskie napięcie linii AC", "F46": "Błąd baterii zapasowej", "F47": "Zbyt wysoka częstotliwość AC",
    "F48": "Zbyt niska częstotliwość AC", "F56": "Zbyt niskie napięcie szyny DC (zwykle: rozładowana bateria)", "F63": "Błąd ARC (łuk elektryczny)",
    "F64": "Zbyt wysoka temperatura radiatora",
}

_ALARM_KEY_RE = re.compile(r"fault|alarm|warning|error|alert|protect|problem|status")
_ALARM_STRICT_RE = re.compile(r"fault|alarm|warn|error")
_OK_STATES = {
    "unknown", "unavailable", "", "0", "0.0", "off", "ok", "normal", "none", "no_fault", "no fault", "standby",
    "waiting", "on-grid", "on grid", "selling", "stand-by", "self-test", "running", "grid",
}


def fault_text(value: Any) -> str:
    codes = re.findall(r"F\d{2}", str(value), flags=re.IGNORECASE)
    out = []
    for c in codes:
        c = c.upper()
        out.append(f"{c}: {FAULT_TEXT[c]}" if c in FAULT_TEXT else c)
    return "; ".join(out)


def detect_alarms(hass, prefix: str) -> list[dict[str, str]]:
    """Aktywne alarmy/błędy czujników falownika (te same reguły co zakładka Alarmy w Diagnostyce)."""
    found: list[dict[str, str]] = []
    pre = f"{prefix}_" if prefix else ""
    try:
        states = list(hass.states.async_all())
    except Exception:  # noqa: BLE001
        return found
    for st in states:
        eid = getattr(st, "entity_id", "")
        dom, _, obj = eid.partition(".")
        if dom not in ("sensor", "binary_sensor") or (pre and not obj.startswith(pre)):
            continue
        key = obj[len(pre):]
        dc = str((getattr(st, "attributes", None) or {}).get("device_class") or "")
        if not (_ALARM_KEY_RE.search(key) or (dom == "binary_sensor" and re.search(r"problem|safety|tamper", dc))):
            continue
        v = str(st.state).strip().lower()
        if v in _OK_STATES:
            continue
        if re.search(r"status|state", key) and not _ALARM_STRICT_RE.search(key):
            continue
        name = (getattr(st, "attributes", None) or {}).get("friendly_name") or eid
        found.append({"entity_id": eid, "state": str(st.state), "name": str(name)})
    return found


class Notifier:
    def __init__(self, rt) -> None:
        self.rt = rt

    def _service(self) -> str | None:
        raw = str(self.rt.cfg.get("notify_service") or "").strip()
        if not raw:
            return None
        return raw.split(".", 1)[1] if raw.startswith("notify.") else raw

    def cfg(self) -> dict[str, Any]:
        """Ustawienia z konfiguratora (Diagnostyka → Powiadomienia) nałożone na domyślne."""
        return ncfg.effective(self.rt.state.get("notify_cfg"))

    async def send(self, kind: str, title: str, message: str, *, key: str | None = None,
                   cooldown_s: float = 0.0, level: str = "warn", force: bool = False) -> bool:
        """True, gdy powiadomienie faktycznie wysłano (nie wstrzymał go odstęp, konfigurator ani wyłącznik).

        Rodzaj z katalogu: włączenie, odstęp i kanał (telefon / tylko HA) z konfiguratora; w ciszy nocnej
        na telefon trafiają tylko rodzaje oznaczone „przez ciszę nocną”. force=True (wiadomość testowa) pomija limity."""
        rt = self.rt
        key = key or kind
        cfg = self.cfg()
        kc = ncfg.kind(cfg, kind)
        if not force and not kc.get("on", True):
            rt.log.add("notify", f"{title} (nie wysłano — wyłączone w konfiguratorze): {message}", "info")
            return False
        if kind in ncfg.CATALOG:
            cooldown_s = float(kc.get("cooldown", 0)) * 60.0
        now = dt_util.now()
        now_ts = now.timestamp()
        sent = rt.state.setdefault("notified", {})
        last = sent.get(key)
        if not force and cooldown_s and isinstance(last, (int, float)) and now_ts - last < cooldown_s:
            return False
        sent[key] = now_ts
        if len(sent) > 60:                                   # pamiętamy tylko świeże wpisy
            for k in sorted(sent, key=lambda x: sent[x])[: len(sent) - 60]:
                sent.pop(k, None)
        rt._save_state()  # noqa: SLF001
        rt.log.add("notify", f"{title}: {message}", level)
        if not switch_on(rt.hass, "notifications_enabled", True):
            return False
        try:
            await rt.hass.services.async_call(
                "persistent_notification", "create",
                {"title": title, "message": message, "notification_id": f"{NOTIFY_ID_PREFIX}{kind}"})
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS: nie udało się utworzyć powiadomienia: %s", err)
        svc = self._service()
        loc = dt_util.as_local(now)
        quiet = not force and not kc.get("quiet_ok") and ncfg.in_quiet(cfg, loc.hour, loc.minute)
        if svc and kc.get("phone", True) and not quiet:
            try:
                await rt.hass.services.async_call("notify", svc, {"title": title, "message": message})
            except Exception as err:  # noqa: BLE001
                rt.log.add("notify", f"Usługa notify.{svc} nie zadziałała: {err}", "error")
        return True

    async def dismiss(self, kind: str) -> None:
        try:
            await self.rt.hass.services.async_call(
                "persistent_notification", "dismiss", {"notification_id": f"{NOTIFY_ID_PREFIX}{kind}"})
        except Exception:  # noqa: BLE001
            pass


class Monitor:
    _rce_alarm = False

    def __init__(self, rt) -> None:
        self.rt = rt
        self.notifier = Notifier(rt)
        self._comm_since: datetime | None = None
        self._comm_notified = False

    async def tick(self, now: datetime) -> None:
        for name, chk in (("niski SOC", self._low_soc), ("alarmy", self._alarms),
                          ("ceny RCE", self._rce), ("łączność", self._comm),
                          ("SOC dnia", self._soc_track), ("bateria pełna", self._battery_full),
                          ("temperatura", self._battery_temp), ("sieć", self._grid_outage),
                          ("pobór z sieci", self._high_import), ("ceny jutro", self._prices_tomorrow),
                          ("źródła danych", self._sources), ("zużycie", self._load_above),
                          ("PV jutro", self._weak_pv), ("zdrowie baterii", self._health),
                          ("podsumowania", self._summaries)):
            try:
                await chk(now)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("EMS monitor [%s]: %s", name, err, exc_info=True)

    # ------------------------------------------------------------- niski SOC
    async def _low_soc(self, now: datetime) -> None:
        rt = self.rt
        soc = rt.soc()
        if soc is None:
            return
        try:
            fl = float(rt.inverter_floor()["hourly"][now.hour])
        except Exception:  # noqa: BLE001
            fl = 0.0
        thr = max(fl + 3.0, LOW_SOC_MIN_THRESHOLD) if fl > 0 else LOW_SOC_MIN_THRESHOLD
        st = rt.state
        if soc <= thr:
            cheap = ""
            try:
                w = next_offpeak_window(now)
                if w:
                    cheap = (f" Tanie okno trwa do {w[1]:%H}:00." if w[2]
                             else f" Najbliższe tanie okno: {w[0]:%H}:00–{w[1]:%H}:00.")
            except Exception:  # noqa: BLE001
                pass
            floor_txt = f"próg odcięcia falownika {fl:.0f}%" if fl > 0 else "bardzo niski poziom"
            sent = await self.notifier.send(
                "low_soc", "🔋 EMS: niski stan baterii",
                f"Bateria {soc:.0f}% ({floor_txt}). Poniżej progu falownik nie zasila domu z baterii i pobiera prąd z sieci.{cheap}",
                cooldown_s=LOW_SOC_COOLDOWN_S)
            st["low_soc_active"] = True
            if sent:
                rt._save_state()  # noqa: SLF001
        elif st.get("low_soc_active") and soc >= thr + 6.0:
            st["low_soc_active"] = False
            st.get("notified", {}).pop("low_soc", None)       # kolejny spadek zgłosimy od razu
            rt._save_state()  # noqa: SLF001
            await self.notifier.dismiss("low_soc")

    # ----------------------------------------------------------------- alarmy
    async def _alarms(self, now: datetime) -> None:
        rt = self.rt
        prefix = ictl.prefix_of(rt.eid("work_mode"))
        active = {a["entity_id"]: a for a in detect_alarms(rt.hass, prefix)}
        known: dict[str, str] = rt.state.setdefault("alarms_active", {})
        changed = False
        for eid, a in active.items():
            if known.get(eid) == a["state"]:
                continue
            known[eid] = a["state"]
            changed = True
            txt = fault_text(a["state"])
            body = f"{a['name']}: {a['state']}" + (f" — {txt}" if txt else "")
            await self.notifier.send(
                "alarm", "⚠ EMS: alarm falownika",
                body + (f"\n{FAULT_NOTE}" if txt else "") + "\nSzczegóły: Diagnostyka → Alarmy.",
                key=f"alarm:{eid}:{a['state']}", cooldown_s=ALARM_COOLDOWN_S, level="error")
        for eid in [e for e in known if e not in active]:
            known.pop(eid, None)
            changed = True
            rt.log.add("notify", f"Alarm ustąpił: {eid}", "ok")
        if changed:
            if not known:
                await self.notifier.dismiss("alarm")
            rt._save_state()  # noqa: SLF001

    # -------------------------------------------------------------- ceny RCE
    async def _rce(self, now: datetime) -> None:
        if now.hour < RCE_CHECK_FROM_HOUR:
            return
        arrays = self.rt.optimizer._read_rce_arrays()  # noqa: SLF001
        tomorrow = (now + timedelta(days=1)).date()
        key = tomorrow.isoformat()
        arr = arrays.get(key) or []
        n = sum(1 for v in arr if isinstance(v, (int, float)))
        need = self._rce_hours(tomorrow)
        if n >= need:
            if self._rce_alarm:                       # ceny w końcu się pojawiły — zdejmujemy stare powiadomienie
                self._rce_alarm = False
                await self.notifier.dismiss("rce_missing")
                self.rt.log.add("notify", "Ceny RCE na jutro są już pełne", "ok")
            return
        sent = await self.notifier.send(
            "rce_missing", "💰 EMS: brak cen RCE na jutro",
            f"Po godz. {RCE_CHECK_FROM_HOUR}:00 nie ma pełnych cen RCE na jutro ({n}/{need} godzin). "
            "Plan sprzedaży z baterii na jutro będzie niepełny — sprawdź integrację z cenami RCE." + self._rce_detail(),
            key=f"rce_missing:{key}", cooldown_s=RCE_COOLDOWN_S)
        if sent:
            self._rce_alarm = True

    def _rce_hours(self, d) -> int:
        """Ile godzin cen ma kompletna doba: 24, a w dobie wiosennej zmiany czasu 23 (godziny 02:00 nie ma)."""
        fn = getattr(self.rt.optimizer, "rce_expected_hours", None)
        try:
            return int(fn(d)) if callable(fn) else 24
        except Exception:  # noqa: BLE001
            return 24

    def _rce_detail(self) -> str:
        """Co czytnik cen widział w encjach — żeby fałszywy alarm (inny format encji) dało się od razu zdiagnozować."""
        fn = getattr(self.rt.optimizer, "rce_report", None)
        if not callable(fn):
            return ""
        try:
            rep = fn()
        except Exception:  # noqa: BLE001
            return ""
        seen = rep.get("seen") or []
        if not seen:
            return " Nie znalazłem żadnej encji z cenami (sprawdzane m.in.: " + ", ".join((rep.get("checked") or [])[:3]) + ")."
        txt = " Odczyt encji: " + "; ".join(seen[:3]) + "."
        src = (rep.get("today") or {}).get("source")
        return txt + (f" Ceny na dziś czytam z {src}." if src else " Nie znalazłem też cen na dziś.")

    # ------------------------------------------------------------ łączność
    async def _comm(self, now: datetime) -> None:
        rt = self.rt
        lost = rt.soc() is None and rt.coordinator.get_float_opt(CONF_GRID_POWER) is None
        if lost:
            if self._comm_since is None:
                self._comm_since = now
            elif (now - self._comm_since).total_seconds() >= COMM_LOSS_AFTER_S:
                mins = int((now - self._comm_since).total_seconds() // 60)
                if await self.notifier.send(
                        "comm_loss", "📡 EMS: brak danych z falownika",
                        f"Od ok. {mins} min brak odczytu SOC i mocy sieci. Sprawdź logger Solarman i sieć Wi-Fi falownika.",
                        cooldown_s=COMM_COOLDOWN_S, level="error"):
                    self._comm_notified = True
        else:
            if self._comm_notified:
                rt.log.add("notify", "Łączność z falownikiem wróciła", "ok")
                await self.notifier.dismiss("comm_loss")
            self._comm_since = None
            self._comm_notified = False

    # ======================================================== rozszerzenia 0.8.1 (konfigurator powiadomień)
    def _thr(self, kind: str) -> float | None:
        return ncfg.threshold(self.notifier.cfg(), kind)

    def _once(self, tag: str, day_key: str) -> bool:
        """True za pierwszym razem dla (tag, dzień) — zdarzenia „raz na dobę” niezależnie od odstępu."""
        done = self.rt.state.setdefault("notify_once", {})
        if done.get(tag) == day_key:
            return False
        done[tag] = day_key
        if len(done) > 40:
            for k in list(done)[: len(done) - 40]:
                done.pop(k, None)
        return True

    async def _soc_track(self, now: datetime) -> None:
        """SOC min/max dnia (do podsumowania dziennego)."""
        soc = self.rt.soc()
        if soc is None:
            return
        day = dt_util.as_local(now).date().isoformat()
        st = self.rt.state.setdefault("soc_day", {})
        if st.get("date") != day:
            if st.get("date"):
                self.rt.state["soc_prev"] = dict(st)
            st.clear()
            st.update({"date": day, "min": soc, "max": soc})
        else:
            st["min"] = min(float(st.get("min", soc)), soc)
            st["max"] = max(float(st.get("max", soc)), soc)

    async def _battery_full(self, now: datetime) -> None:
        soc = self.rt.soc()
        if soc is None or soc < 99.5:
            return
        day = dt_util.as_local(now).date().isoformat()
        if self._once("battery_full", day):
            await self.notifier.send("battery_full", "🔋 EMS: bateria naładowana", f"SOC {soc:.0f}% — bateria jest pełna.",
                                     key=f"full:{day}", level="info")

    async def _battery_temp(self, now: datetime) -> None:
        t = self.rt.coordinator.get_float_opt(CONF_BATTERY_TEMPERATURE)
        if t is None:
            return
        st = self.rt.state.setdefault("temp_alarm", {})
        hi, lo = self._thr("battery_temp_high"), self._thr("battery_temp_low")
        if hi is not None:
            if t > hi and not st.get("hi"):
                st["hi"] = True
                await self.notifier.send("battery_temp_high", "🌡 EMS: wysoka temperatura baterii",
                                         f"Temperatura baterii {t:.1f} °C (próg {hi:.0f} °C).", level="error")
            elif t < hi - 3.0:
                st["hi"] = False
        if lo is not None:
            if t < lo and not st.get("lo"):
                st["lo"] = True
                await self.notifier.send("battery_temp_low", "🥶 EMS: niska temperatura baterii",
                                         f"Temperatura baterii {t:.1f} °C (próg {lo:.0f} °C). Ładowanie w niskiej temperaturze skraca życie ogniw.")
            elif t > lo + 3.0:
                st["lo"] = False

    async def _grid_outage(self, now: datetime) -> None:
        v = self.rt.coordinator.get_float_opt(CONF_GRID_VOLTAGE_L1)
        if v is None:
            return
        thr = self._thr("grid_outage") or 100.0
        st = self.rt.state.setdefault("grid_outage", {})
        if v < thr:
            if st.get("since") is None:
                st["since"] = now.timestamp()
            elif not st.get("notified") and now.timestamp() - float(st["since"]) >= 60:
                st["notified"] = True
                soc = self.rt.soc()
                try:
                    top = ", ".join(f"{nm} {p / 1000:.1f} kW" for nm, p in self.rt.devices.top_now())
                except Exception:  # noqa: BLE001
                    top = ""
                await self.notifier.send("grid_outage", "⚡ EMS: zanik sieci",
                                         f"Napięcie sieci L1 {v:.0f} V — dom zasilany z baterii" + (f" (SOC {soc:.0f}%)." if soc is not None else ".")
                                         + (f" Teraz najwięcej pobierają: {top}." if top else ""),
                                         key="grid_down", level="error")
        elif v >= thr + 60.0 and st.get("since") is not None:
            was = st.get("notified")
            mins = int((now.timestamp() - float(st["since"])) // 60)
            st.clear()
            if was:
                await self.notifier.send("grid_outage", "⚡ EMS: sieć wróciła", f"Napięcie sieci L1 {v:.0f} V. Przerwa trwała ok. {mins} min.",
                                         key="grid_up", level="info")

    async def _high_import(self, now: datetime) -> None:
        if not ncfg.kind(self.notifier.cfg(), "high_import").get("on"):
            return
        p = self.rt.coordinator.get_float_opt(CONF_GRID_POWER)
        thr = (self._thr("high_import") or 7.0) * 1000.0
        st = self.rt.state.setdefault("high_import", {})
        if p is not None and p > thr:
            if st.get("since") is None:
                st["since"] = now.timestamp()
            elif now.timestamp() - float(st["since"]) >= 300 and not st.get("sent"):
                st["sent"] = True
                await self.notifier.send("high_import", "🔌 EMS: duży pobór z sieci",
                                         f"Od 5 min pobór z sieci {p / 1000.0:.1f} kW (próg {thr / 1000.0:.1f} kW).")
        else:
            st.clear()

    def _plan_props(self) -> dict:
        try:
            return (self.rt.plan() or {}).get("proposals") or {}
        except Exception:  # noqa: BLE001
            return {}

    async def _prices_tomorrow(self, now: datetime) -> None:
        if now.hour < 14:
            return
        tomorrow = (now + timedelta(days=1)).date()
        key = tomorrow.isoformat()
        arr = (self.rt.optimizer._read_rce_arrays() or {}).get(key) or []  # noqa: SLF001
        vals = [(h, float(v)) for h, v in enumerate(arr) if isinstance(v, (int, float))]
        if len(vals) < self._rce_hours(tomorrow):
            return
        lo = self._thr("rce_negative")
        low = [h for h, v in vals if lo is not None and v <= lo]
        if low and self._once("rce_negative", key):
            spans = _spans(low)
            mn = min(v for _h, v in vals)
            await self.notifier.send("rce_negative", "📉 EMS: niskie ceny RCE jutro",
                                     f"Jutro cena sprzedaży ≤ {lo:.2f} zł/kWh w godzinach {spans} (najniżej {mn:.2f} zł/kWh). "
                                     "W tych godzinach lepiej ładować baterię niż eksportować do sieci.", key=f"rce_neg:{key}", level="info")
        hi = self._thr("rce_high")
        top_h, top_v = max(vals, key=lambda x: x[1])
        if hi is not None and top_v >= hi and self._once("rce_high", key):
            props = self._plan_props()
            sale = [f"{p.get('proposed')}" for k, p in props.items() if k.startswith("bateria_sprzedaz_start") and p.get("proposed") and not p.get("skip")]
            plan_txt = f" Plan sprzedaży z baterii: start {', '.join(sale)}." if sale else " Plan nie przewiduje sprzedaży z baterii."
            await self.notifier.send("rce_high", "📈 EMS: wysoka cena sprzedaży jutro",
                                     f"Jutro o {top_h:02d}:00 cena RCE {top_v:.2f} zł/kWh (próg {hi:.2f}).{plan_txt}", key=f"rce_high:{key}", level="info")

    async def _sources(self, now: datetime) -> None:
        opt = self.rt.optimizer
        today = dt_util.as_local(now).date()
        if now.hour >= 18:
            try:
                pv1 = opt._read_pv_hourly(1)  # noqa: SLF001
            except Exception:  # noqa: BLE001
                pv1 = None
            if pv1 is None and self._once("pv_forecast_missing", today.isoformat()):
                await self.notifier.send("pv_forecast_missing", "☀️ EMS: brak prognozy PV",
                                         "Brak godzinowej prognozy PV na jutro (Solcast / Forecast.Solar). Plan liczy tak, jakby jutro nie było słońca. "
                                         "Sprawdź integrację prognozy i encje prognozy w konfiguracji EMS.")
        if now.hour >= 6 and get_profile().mode == "dynamic":
            try:
                have = opt.buy_hourly_for(today)
            except Exception:  # noqa: BLE001
                have = None
            if not have and self._once("buy_prices_missing", today.isoformat()):
                await self.notifier.send("buy_prices_missing", "💸 EMS: brak cen zakupu",
                                         "Tryb taryfy „dynamiczna”, a encja ceny zakupu nie podaje dziś cen godzinowych. "
                                         "Planer używa okien z konfiguracji. Sprawdź integrację cen (np. Pstryk).")

    async def _load_above(self, now: datetime) -> None:
        if now.hour < 12:
            return
        lf = (self.rt.coordinator.data or {}).get("load_forecast") or {}
        days = lf.get("days") or []
        today = next((d for d in days if isinstance(d, dict) and d.get("label") == "Dziś"), None)
        if not today:
            return
        fc, nc = today.get("forecast"), today.get("nowcast")
        thr = self._thr("load_above") or 30.0
        if isinstance(fc, (int, float)) and isinstance(nc, (int, float)) and fc > 0.5 and nc > fc * (1 + thr / 100.0):
            day = dt_util.as_local(now).date().isoformat()
            if self._once("load_above", day):
                await self.notifier.send("load_above", "🏠 EMS: zużycie dziś wyższe niż zwykle",
                                         f"Przy obecnym tempie dom zużyje dziś ok. {nc:.1f} kWh, a prognoza dnia to {fc:.1f} kWh "
                                         f"(+{(nc / fc - 1) * 100:.0f}%). Bateria może nie wystarczyć do rana.")

    async def _weak_pv(self, now: datetime) -> None:
        if now.hour < 17:
            return
        try:
            pv = self.rt.optimizer._read_pv_forecast_kwh("pv_forecast_tomorrow", "")  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pv = None
        thr = self._thr("weak_pv") or 3.0
        if pv is None or pv >= thr:
            return
        day = dt_util.as_local(now).date().isoformat()
        if not self._once("weak_pv", day):
            return
        props = self._plan_props()
        st, sp = props.get("start_grid_charge") or {}, props.get("stop_grid_charge") or {}
        if st.get("proposed") and not st.get("skip"):
            gc = f" Plan: ładowanie z sieci {st.get('proposed')}–{sp.get('proposed') or '?'}."
        else:
            gc = " Plan nie przewiduje ładowania z sieci."
        await self.notifier.send("weak_pv", "☁️ EMS: słaba prognoza PV na jutro",
                                 f"Prognoza PV na jutro {pv:.1f} kWh (próg {thr:.1f} kWh).{gc}", level="info")

    async def _health(self, now: datetime) -> None:
        if now.hour != 12:
            return
        try:
            from .const import CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH
            cap = float(self.rt.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
            s = self.rt.stats.summary(cap)
        except Exception:  # noqa: BLE001
            return
        trend = s.get("eff_trend_pp")
        thr = self._thr("battery_health") or 3.0
        if isinstance(trend, (int, float)) and trend <= -thr:
            await self.notifier.send("battery_health", "🔋 EMS: spadek sprawności baterii",
                                     f"Sprawność cyklu z 30 dni {s.get('eff_30d')}% wobec {s.get('eff_90d')}% z 90 dni ({trend:+.1f} pkt). "
                                     "To orientacyjny wskaźnik — sprawdź, czy nie zmieniło się coś w instalacji.", key="health")

    # --------------------------------------------------------- podsumowania
    async def _summaries(self, now: datetime) -> None:
        cfg = self.notifier.cfg()
        sch = cfg["sched"]
        loc = dt_util.as_local(now)
        hm = loc.strftime("%H:%M")
        sent = self.rt.state.setdefault("summary_sent", {})
        today = loc.date()
        if ncfg.kind(cfg, "summary_daily").get("on") and hm >= sch["daily"]["time"] and sent.get("daily") != today.isoformat():
            sent["daily"] = today.isoformat()
            self.rt._save_state()  # noqa: SLF001
            await self.notifier.send("summary_daily", f"📅 EMS: podsumowanie dnia {today:%d.%m}", self._summary_body("day", today), level="info")
        if (ncfg.kind(cfg, "summary_weekly").get("on") and loc.weekday() == sch["weekly"]["weekday"]
                and hm >= sch["weekly"]["time"] and sent.get("weekly") != today.isoformat()):
            sent["weekly"] = today.isoformat()
            self.rt._save_state()  # noqa: SLF001
            await self.notifier.send("summary_weekly", "🗓 EMS: podsumowanie tygodnia", self._summary_body("week", today), level="info")

    def _summary_body(self, kind: str, day) -> str:
        """Treść podsumowania; błąd w liczeniu nie może zgubić całej wiadomości (znacznik „wysłano” jest już ustawiony)."""
        try:
            text = self.rt.summary_text(kind, day)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("EMS: podsumowanie (%s) — błąd liczenia: %s", kind, err, exc_info=True)
            self.rt.log.add("notify", f"Podsumowanie ({kind}): nie udało się policzyć szczegółów — {err}", "error")
            return f"Nie udało się policzyć szczegółów podsumowania ({err}). Sprawdź dziennik EMS."
        return text or "Brak danych do podsumowania za ten okres."


def _spans(hours: list[int]) -> str:
    """[1,2,3,7] → „01–04, 07–08”."""
    out: list[str] = []
    start = prev = None
    for h in sorted(hours):
        if start is None:
            start = prev = h
        elif h == prev + 1:
            prev = h
        else:
            out.append(f"{start:02d}–{prev + 1:02d}")
            start = prev = h
    if start is not None:
        out.append(f"{start:02d}–{prev + 1:02d}")
    return ", ".join(out)
