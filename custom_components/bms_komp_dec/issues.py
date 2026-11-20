"""Lista „co dziś nie działa”: jedno miejsce, które zbiera braki danych i usterki, o których EMS już wie z osobnych kontroli
(ceny RCE i zakupu, prognoza PV, plan, zapis do falownika, kolizja okien, urządzenia, alarmy, naprawione pliki zapisu).

Nic tu nie wysyła powiadomień (od tego jest monitor) — to widok „stan na teraz”, liczony co minutę przez runtime i pokazywany
w banerze na górze karty oraz w raporcie diagnostycznym. Każda kontrola jest osobna i odporna na wyjątki: awaria jednej nie
zasłania pozostałych."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .helpers import switch_on
from .tariff import get_profile

_LOGGER = logging.getLogger(__name__)

RCE_TOMORROW_FROM = 15      # ceny RCE na jutro są publikowane w okolicy 13–14; wcześniej brak nie jest usterką
BUY_TOMORROW_INFO_FROM = 16
PV_TODAY_FROM = 4
PV_TOMORROW_FROM = 18
BUY_TODAY_FROM = 6
STALE_PLAN_S = 45 * 60
LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2}
MAX_ISSUES = 12


def _issue(iid: str, level: str, title: str, detail: str = "", fix: str = "") -> dict[str, Any]:
    return {"id": iid, "level": level, "title": title, "detail": detail, "fix": fix}


def _count(arr: Any) -> int:
    return sum(1 for v in (arr or []) if isinstance(v, (int, float)) and not isinstance(v, bool))


def _rce(rt, now: datetime) -> list[dict[str, Any]]:
    opt = rt.optimizer
    arrays = opt.rce_arrays() or {}
    out = []
    today = now.date()
    for d, iid, label, active in ((today, "rce_today", "dziś", True),
                                  (today + timedelta(days=1), "rce_tomorrow", "jutro", now.hour >= RCE_TOMORROW_FROM)):
        if not active:
            continue
        need = 24
        fn = getattr(opt, "rce_expected_hours", None)
        if callable(fn):
            need = int(fn(d))
        n = _count(arrays.get(d.isoformat()))
        if n < need:
            out.append(_issue(iid, "warn", f"Brak pełnych cen sprzedaży (RCE) na {label}", f"{n}/{need} godzin.",
                              "Plan sprzedaży z baterii na ten dzień będzie niepełny — sprawdź integrację z cenami RCE (Ustawienia → Diagnostyka → raport, sekcja „Źródła cen”)."))
    return out


def _buy(rt, now: datetime) -> list[dict[str, Any]]:
    opt = rt.optimizer
    prof = get_profile()
    if prof.mode == "zone":
        return []
    out = []
    today = now.date()
    have_today = _count(opt.buy_hourly_for(today)) > 0
    if prof.mode == "dynamic" and now.hour >= BUY_TODAY_FROM and not have_today:
        out.append(_issue("buy_today", "warn", "Brak cen zakupu na dziś (taryfa dynamiczna)",
                          "Encja ceny zakupu nie podaje cen godzinowych — planer używa okien z konfiguracji.",
                          "Sprawdź integrację cen (np. Pstryk) i encję zakupu w konfiguracji EMS."))
    if have_today and hasattr(opt, "buy_tomorrow_status"):
        st = opt.buy_tomorrow_status()
        state, text = st.get("state"), st.get("text") or ""
        if state in ("not_exposed", "missing"):
            out.append(_issue("buy_tomorrow", "warn", "Brak cen zakupu na jutro", text))
        elif state == "waiting" and now.hour >= BUY_TOMORROW_INFO_FROM:
            out.append(_issue("buy_tomorrow", "info", "Ceny zakupu na jutro jeszcze nieopublikowane", text))
    return out


def _pv(rt, now: datetime) -> list[dict[str, Any]]:
    opt = rt.optimizer
    out = []
    if now.hour >= PV_TODAY_FROM and opt._read_pv_hourly(0) is None:  # noqa: SLF001
        out.append(_issue("pv_today", "warn", "Brak prognozy PV na dziś",
                          "Plan liczy tak, jakby słońca nie było.",
                          "Sprawdź integrację prognozy (Solcast / Forecast.Solar) i encje prognozy w konfiguracji EMS."))
    if now.hour >= PV_TOMORROW_FROM and opt._read_pv_hourly(1) is None:  # noqa: SLF001
        out.append(_issue("pv_tomorrow", "warn", "Brak prognozy PV na jutro", "Plan na jutro liczy tak, jakby słońca nie było.",
                          "Sprawdź integrację prognozy (Solcast / Forecast.Solar)."))
    return out


def _plan(rt, now: datetime) -> list[dict[str, Any]]:
    plan = rt.plan() or {}
    out = []
    if plan.get("error"):
        out.append(_issue("plan_error", "error", "Plan niedostępny", str(plan["error"])[:300],
                          "Bez planu EMS pracuje wg ustawionych godzin. Sprawdź odczyt SOC i źródła cen."))
        return out
    gen = dt_util.parse_datetime(str(plan.get("generated_at") or ""))
    if gen is not None:
        age = (now - dt_util.as_local(gen)).total_seconds()
        if age > STALE_PLAN_S:
            out.append(_issue("plan_stale", "warn", "Plan nie był odświeżany",
                              f"Ostatnio policzony {int(age // 60)} min temu.", "Sprawdź dziennik decyzji i autotest (Ustawienia → Diagnostyka)."))
    return out


def _write(rt, now: datetime) -> list[dict[str, Any]]:
    from . import brands
    from .health import _direct_write_blocked
    ctl = brands.control_entities(rt.hass, rt.cfg)
    blocked = _direct_write_blocked(rt.hass, [e for e in ctl.values() if e])
    if not blocked:
        return []
    names = ", ".join(dict.fromkeys(n for _e, n in blocked))
    return [_issue("write_blocked", "error", "Zapis do falownika jest wyłączony",
                   f"Falownik „{names}” (połączony bezpośrednio) nie przyjmie komend EMS.",
                   "Ustawienia → Urządzenia i usługi → EMS komp-dec → wpis falownika → Konfiguruj → zaznacz „Zezwól na zapis do falownika”.")]


def _windows(rt, now: datetime) -> list[dict[str, Any]]:
    from .health import window_conflict_check
    res = window_conflict_check(rt)
    if res.get("status") != "error":
        return []
    return [_issue("window_conflict", "warn", "Okna ładowania i sprzedaży nakładają się", str(res.get("detail") or ""), str(res.get("fix") or ""))]


def _devices(rt, now: datetime) -> list[dict[str, Any]]:
    if not rt.dev_ctl.enabled():
        return []
    bad = []
    for d in rt.devices.devices:
        if d.get("switch_eid") and d.get("ctl_mode", "off") != "off":
            st = rt.hass.states.get(d["switch_eid"])
            if st is None or st.state not in ("on", "off"):
                bad.append(d.get("name") or d["switch_eid"])
    if not bad:
        return []
    return [_issue("devices_switch", "warn", "Przełącznik urządzenia jest niedostępny", ", ".join(bad[:5]),
                   "EMS nie może nimi sterować, dopóki przełącznik nie wróci (sprawdź integrację urządzenia).")]


def _alarms(rt, now: datetime) -> list[dict[str, Any]]:
    act = rt.state.get("alarms_active")
    if not isinstance(act, dict) or not act:
        return []
    return [_issue("alarms", "error", "Alarm falownika", "; ".join(f"{e} = {v}" for e, v in list(act.items())[:4]),
                   "Szczegóły: Ustawienia → Alarmy.")]


def _brand(rt, now: datetime) -> list[dict[str, Any]]:
    from . import brands
    brand = brands.detect(rt.hass, rt.cfg)
    if brand != brands.DEYE and switch_on(rt.hass, "brand_test_mode", True):
        return [_issue("brand_test", "warn", "Tryb próbny falownika jest włączony",
                       "Komendy trafiają tylko do dziennika jako „ustawiłbym …” — falownik ich nie dostaje.",
                       "Gdy kroki w dzienniku są właściwe, wyłącz switch.bms_brand_test_mode.")]
    return []


def _repairs(rt, now: datetime) -> list[dict[str, Any]]:
    items = rt.integrity_items()
    if not items:
        return []
    return [_issue("data_repaired", "info", "Przy starcie naprawiono uszkodzone dane", " ".join(i.summary() + "." for i in items)[:600],
                   "Kopie oryginałów są w .storage (pliki …_backup). Nic więcej nie trzeba robić.")]


_CHECKS = (_alarms, _write, _plan, _windows, _rce, _buy, _pv, _devices, _brand, _repairs)


def collect(rt, now: datetime | None = None) -> list[dict[str, Any]]:
    """Aktualna lista problemów, najpoważniejsze pierwsze (stała kolejność w obrębie poziomu)."""
    now = dt_util.as_local(now) if now else dt_util.now()
    out: list[dict[str, Any]] = []
    for check in _CHECKS:
        try:
            out.extend(check(rt, now))
        except Exception:  # noqa: BLE001
            _LOGGER.debug("EMS: kontrola „%s” nie powiodła się", check.__name__, exc_info=True)
    out.sort(key=lambda i: LEVEL_ORDER.get(i["level"], 3))
    return out[:MAX_ISSUES]
