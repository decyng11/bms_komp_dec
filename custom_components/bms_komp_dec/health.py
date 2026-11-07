"""Kreator instalacji / test zdrowia: czy integracja ma wszystko, czego potrzebuje, i co zrobi komenda.

Wynik (lista kontroli ze statusem ok/warn/error i podpowiedzią, co zrobić) służy karcie jako „Kreator”
oraz osobom, które instalują integrację na innym falowniku. Nic tu NIE zmienia ustawień falownika:
komendy są tylko wyliczane („na sucho”) — widać encje i wartości, które zostałyby ustawione."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from . import inverter_ctl as ictl
from .const import (
    CONF_BATTERY_CAPACITY_KWH, CONF_BATTERY_POWER, CONF_ENERGY_BATT_CHARGE_TODAY, CONF_ENERGY_GRID_EXPORT_TODAY,
    CONF_ENERGY_GRID_IMPORT_TODAY, CONF_ENERGY_LOAD_TODAY, CONF_ENERGY_PV_TODAY, CONF_GRID_POWER, CONF_LOAD_POWER,
    CONF_PRICE_BUY_ENTITY, CONF_PRICE_SELL_ENTITY, CONF_PV_FORECAST_TODAY, CONF_PV_FORECAST_TOMORROW, CONF_PV_POWER,
    CONF_SOC, DEFAULT_BATTERY_CAPACITY_KWH, DEFAULT_PRICE_BUY_ENTITY, DEFAULT_PRICE_SELL_ENTITY,
    DEFAULT_PV_FORECAST_TODAY, DEFAULT_PV_FORECAST_TOMORROW, BUTTONS, TIMES, VERSION,
)
from .helpers import find_eid, switch_on
from .runtime import COMMAND_LABELS
from .tariff import get_profile

_BAD = ("unknown", "unavailable", "none", "")

# Wykres historii na karcie korzysta z Chart.js: najpierw z lokalnej kopii (frontend/vendor), a gdy jej nie ma — z CDN.
# Sprawdzane raz przy imporcie modułu (HA importuje integrację poza pętlą zdarzeń); po wgraniu plików — restart HA.
_VENDOR_DIR = Path(__file__).parent / "frontend" / "vendor"
_VENDOR_FILES = ("chart.umd.min.js", "chartjs-adapter-date-fns.bundle.min.js")
try:
    _VENDOR_OK = all((_VENDOR_DIR / f).is_file() for f in _VENDOR_FILES)
except OSError:
    _VENDOR_OK = False

ROLE_LABEL = {
    "work_mode": "Tryb pracy falownika (select)",
    "charge_current": "Maks. prąd ładowania baterii (number)",
    "export_surplus": "Moc eksportu / nadwyżki (number)",
    "tou_select": "Time of Use (select)",
}
SENSOR_LABEL = [
    (CONF_SOC, "Stan naładowania baterii (SOC)", True),
    (CONF_PV_POWER, "Moc PV", False),
    (CONF_LOAD_POWER, "Moc zużycia domu", False),
    (CONF_BATTERY_POWER, "Moc baterii", False),
    (CONF_GRID_POWER, "Moc sieci", True),
    (CONF_ENERGY_PV_TODAY, "Produkcja PV dziś (licznik)", False),
    (CONF_ENERGY_LOAD_TODAY, "Zużycie dziś (licznik)", False),
    (CONF_ENERGY_GRID_IMPORT_TODAY, "Import z sieci dziś (licznik)", False),
    (CONF_ENERGY_GRID_EXPORT_TODAY, "Eksport do sieci dziś (licznik)", False),
    (CONF_ENERGY_BATT_CHARGE_TODAY, "Ładowanie baterii dziś (licznik)", False),
]


def _chk(cid: str, title: str, status: str, detail: str, fix: str = "") -> dict[str, str]:
    return {"id": cid, "title": title, "status": status, "detail": detail, "fix": fix}


def _numeric(st) -> bool:
    if st is None or str(st.state).strip().lower() in _BAD:
        return False
    try:
        float(st.state)
        return True
    except (TypeError, ValueError):
        return False


def _fmt_value(v: Any) -> Any:
    return v if isinstance(v, (int, float)) else str(v)


def commands_preview(rt) -> list[dict[str, Any]]:
    """Co zrobiłby każdy przycisk (encja → wartość) bez wykonywania czegokolwiek."""
    out: list[dict[str, Any]] = []
    for key, name, _icon in BUTTONS:
        entry: dict[str, Any] = {"key": key, "label": COMMAND_LABELS.get(key, name), "steps": [], "ok": True, "error": None}
        try:
            steps = rt._steps(key)  # noqa: SLF001
        except HomeAssistantError as err:
            entry.update(ok=False, error=str(err))
            out.append(entry)
            continue
        except Exception as err:  # noqa: BLE001
            entry.update(ok=False, error=f"{type(err).__name__}: {err}")
            out.append(entry)
            continue
        missing = []
        for domain, eid, value in steps:
            exists = rt.hass.states.get(eid) is not None
            if not exists:
                missing.append(eid)
            entry["steps"].append({"domain": domain, "entity_id": eid, "value": _fmt_value(value), "exists": exists})
        if missing:
            entry.update(ok=False, error="brak encji: " + ", ".join(dict.fromkeys(missing)))
        out.append(entry)
    return out


def _direct_write_blocked(hass, eids: list[str]) -> list[tuple[str, str]]:
    """[(encja, nazwa falownika)] — encje sterujące należące do falownika dodanego bezpośrednio z wyłączonym zapisem."""
    out: list[tuple[str, str]] = []
    try:
        from homeassistant.helpers import entity_registry as er
        from .direct import is_inverter_entry
        reg = er.async_get(hass)
        for eid in dict.fromkeys(eids):
            ent = reg.async_get(eid) if hasattr(reg, "async_get") else reg.entities.get(eid)
            ce_id = getattr(ent, "config_entry_id", None) if ent is not None else None
            entry = hass.config_entries.async_get_entry(ce_id) if ce_id else None
            if entry is not None and is_inverter_entry(entry) and not (entry.options or {}).get("allow_write"):
                out.append((eid, entry.title))
    except Exception:  # noqa: BLE001
        pass
    return out


def health_check(rt) -> dict[str, Any]:
    hass, cfg = rt.hass, rt.cfg
    checks: list[dict[str, str]] = []

    # --- encje sterujące falownikiem (zależnie od marki)
    from . import brands
    brand = brands.detect(hass, cfg)
    ctl = brands.control_entities(hass, cfg)
    checks.append(_chk("brand", "Marka falownika (sterowanie)", "ok", brands.LABELS.get(brand, brand)))
    if brand != brands.DEYE:
        for role, eid in ctl.items():
            label = f"Sterowanie: {brands.ROLES[brand][role][1][0]}"
            st = hass.states.get(eid) if eid else None
            if st is None:
                checks.append(_chk(f"ctl_{role}", label, "error", "nie znaleziono encji",
                                   "Sprawdź, czy falownik jest połączony i czy jego profil ma tę encję."))
            elif str(st.state).lower() in _BAD:
                checks.append(_chk(f"ctl_{role}", label, "warn", f"{eid} jest teraz „{st.state}”."))
            else:
                checks.append(_chk(f"ctl_{role}", label, "ok", f"{eid} = {st.state}"))
        mode = ctl.get("mode")
        if mode and hass.states.get(mode) is not None:
            kinds = ("self_use", "passive") if brand == brands.SOFAR_G3 else ("auto", "timed")
            bad = [k for k in kinds if brands.pick(hass, mode, k) is None]
            checks.append(_chk("opt_mode", f"Opcje {mode}", "error" if bad else "ok",
                               f"brak: {', '.join(bad)}" if bad else ", ".join(f"{k}→{brands.pick(hass, mode, k)}" for k in kinds)))
        test = switch_on(hass, "brand_test_mode", True)
        checks.append(_chk("brand_test", "Tryb próbny (Sofar)", "warn" if test else "ok",
                           "włączony — komendy trafiają tylko do dziennika jako „ustawiłbym …”" if test
                           else "wyłączony — EMS zapisuje ustawienia do falownika",
                           "Sprawdź w dzienniku, czy kroki komend są właściwe, i dopiero wtedy wyłącz switch.bms_brand_test_mode." if test else ""))
    else:
        for role in ("work_mode", "charge_current", "export_surplus", "tou_select"):
            eid = rt.eid(role)
            st = hass.states.get(eid)
            if st is None:
                checks.append(_chk(f"ctl_{role}", ROLE_LABEL[role], "error", f"Nie znaleziono encji {eid}.",
                                   "Zmień konfigurację integracji i wskaż właściwą encję (albo zaznacz „Wykryj encje ponownie”)."))
            elif str(st.state).lower() in _BAD:
                checks.append(_chk(f"ctl_{role}", ROLE_LABEL[role], "warn", f"{eid} jest teraz „{st.state}”.",
                                   "Sprawdź połączenie z loggerem Solarman; komendy nie zadziałają, dopóki encja jest niedostępna."))
            else:
                checks.append(_chk(f"ctl_{role}", ROLE_LABEL[role], "ok", f"{eid} = {st.state}"))
    # falownik dodany bezpośrednio: bez „Zezwól na zapis” żadna komenda EMS nie dojdzie do falownika
    blocked = _direct_write_blocked(hass, [e for e in ctl.values() if e])
    if blocked:
        names = ", ".join(dict.fromkeys(n for _e, n in blocked))
        checks.append(_chk("direct_write", "Zapis do falownika", "error",
                           f"Falownik „{names}” (połączony bezpośrednio) ma wyłączony zapis — komendy i harmonogram EMS "
                           f"nie zmienią jego ustawień ({', '.join(e for e, _n in blocked)}).",
                           "Ustawienia → Urządzenia i usługi → EMS komp-dec → wpis falownika → Konfiguruj → zaznacz „Zezwól na zapis do falownika”."))
    # nazwy opcji select (Deye)
    for role, kinds in ((("work_mode", ("export", "zero")), ("tou_select", ("tou_off", "tou_on"))) if brand == brands.DEYE else ()):
        eid = rt.eid(role)
        if hass.states.get(eid) is None:
            continue
        opts = ictl.options_of(hass, eid)
        bad = [k for k in kinds if ictl.pick_option(hass, eid, k) is None]
        if bad:
            checks.append(_chk(f"opt_{role}", f"Opcje {eid}", "error",
                               f"Brak oczekiwanych opcji ({', '.join(bad)}). Dostępne: {', '.join(opts or [])}.",
                               "Ten model/firmware nazywa tryby inaczej — zgłoś nazwy opcji, a komendy zostaną dopasowane."))
        else:
            picked = ", ".join(f"{k}→{ictl.pick_option(hass, eid, k)}" for k in kinds)
            checks.append(_chk(f"opt_{role}", f"Opcje {eid}", "ok", picked))

    # --- czujniki
    for key, label, must in SENSOR_LABEL:
        eid = cfg.get(key)
        st = hass.states.get(eid) if eid else None
        if st is None:
            checks.append(_chk(f"sensor_{key}", label, "error" if must else "warn",
                               f"Nie znaleziono encji {eid or '(nie ustawiono)'}.",
                               "Wskaż encję w konfiguracji integracji." + ("" if must else " Bez niej część statystyk będzie niedostępna.")))
        elif not _numeric(st):
            checks.append(_chk(f"sensor_{key}", label, "warn", f"{eid} = „{st.state}” (brak wartości liczbowej).",
                               "Jeśli to trwa — sprawdź logger Solarman."))
        else:
            checks.append(_chk(f"sensor_{key}", label, "ok", f"{eid} = {st.state} {st.attributes.get('unit_of_measurement', '')}".strip()))

    # --- ceny i prognozy
    for key, default, label, must in (
        (CONF_PRICE_SELL_ENTITY, DEFAULT_PRICE_SELL_ENTITY, "Cena sprzedaży (RCE / Pstryk / inna)", True),
        (CONF_PRICE_BUY_ENTITY, DEFAULT_PRICE_BUY_ENTITY, "Cena zakupu", False),
        (CONF_PV_FORECAST_TODAY, DEFAULT_PV_FORECAST_TODAY, "Prognoza PV na dziś", False),
        (CONF_PV_FORECAST_TOMORROW, DEFAULT_PV_FORECAST_TOMORROW, "Prognoza PV na jutro", False),
    ):
        eid = rt.optimizer.config.get(key, default)
        st = hass.states.get(eid)
        if st is None:
            checks.append(_chk(f"src_{key}", label, "error" if must else "warn", f"Nie znaleziono encji {eid}.",
                               "Wskaż encję w konfiguracji integracji." + ("" if must else
                               " Bez niej planer użyje wartości zastępczych (mniej dokładny plan).")))
        else:
            checks.append(_chk(f"src_{key}", label, "ok", f"{eid} = {st.state}"))
    try:
        pvp = rt.optimizer.pv_card_payload()
        src = pvp.get("pv_forecast_source")
        have = [lbl for lbl, k in (("dziś", "pv_hourly_today"), ("jutro", "pv_hourly_tomorrow")) if pvp.get(k)]
        if have:
            checks.append(_chk("pv_hourly", "Prognoza PV godzinowa", "ok", f"{src or 'źródło nieznane'}: {', '.join(have)}"))
        else:
            fs_err = getattr(getattr(rt.optimizer, "pv_fc", None), "fs_error", None)
            checks.append(_chk("pv_hourly", "Prognoza PV godzinowa", "warn",
                               "brak — planer liczy bez wiedzy, kiedy w ciągu dnia będzie słońce" + (f" ({fs_err})" if fs_err else ""),
                               "Zainstaluj Solcast albo Forecast.Solar i wskaż jego encję prognozy na dziś/jutro w konfiguracji."))
    except Exception as err:  # noqa: BLE001
        checks.append(_chk("pv_hourly", "Prognoza PV godzinowa", "warn", f"nie udało się odczytać: {err}"))
    try:
        arrays = rt.optimizer._read_rce_arrays()  # noqa: SLF001
        from homeassistant.util import dt as dt_util
        from datetime import timedelta
        today = dt_util.now().date()
        for lbl, d in (("dziś", today), ("jutro", today + timedelta(days=1))):
            n = sum(1 for v in (arrays.get(d.isoformat()) or []) if isinstance(v, (int, float)))
            need_fn = getattr(rt.optimizer, "rce_expected_hours", None)
            need = int(need_fn(d)) if callable(need_fn) else 24
            rep = rt.optimizer.rce_report() if hasattr(rt.optimizer, "rce_report") else {}
            src = (rep.get("today" if lbl == "dziś" else "tomorrow") or {}).get("source")
            seen = "; ".join((rep.get("seen") or [])[:3]) or "nie znaleziono encji z cenami"
            if n >= need:
                checks.append(_chk(f"rce_{lbl}", f"Ceny RCE {lbl}", "ok", f"pełne {need} godzin" + (f" ({src})" if src else "")))
            elif lbl == "jutro":
                checks.append(_chk("rce_jutro", "Ceny RCE jutro", "warn", f"{n}/{need} godzin",
                                   "Ceny na jutro są publikowane po południu — to normalne wcześniej w ciągu dnia. "
                                   f"Odczyt encji: {seen}."))
            else:
                checks.append(_chk("rce_dziś", "Ceny RCE dziś", "error" if n == 0 else "warn", f"{n}/{need} godzin",
                                   f"Sprawdź integrację z cenami RCE. Odczyt encji: {seen}."))
    except Exception as err:  # noqa: BLE001
        checks.append(_chk("rce", "Ceny RCE", "warn", f"nie udało się odczytać: {err}"))

    # --- bateria, taryfa
    cap = rt.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH)
    if cfg.get(CONF_BATTERY_CAPACITY_KWH) is None:
        checks.append(_chk("capacity", "Pojemność baterii", "warn", f"Używam wartości domyślnej {cap} kWh.",
                           "Ustaw rzeczywistą pojemność w konfiguracji — od niej zależą plany i rezerwa."))
    else:
        checks.append(_chk("capacity", "Pojemność baterii", "ok", f"{float(cap):.1f} kWh"))
    try:
        est, n_est = rt.stats.capacity_estimate()
        if est and float(cap) > 0 and n_est >= 3 and not (0.7 <= est / float(cap) <= 1.3):
            checks.append(_chk("capacity_est", "Pojemność baterii a własny szacunek", "warn",
                               f"skonfigurowano {float(cap):.1f} kWh, szacunek z ładowania ok. {est:.1f} kWh ({n_est} pomiarów)",
                               "Szacunek jest orientacyjny (SOC jest zaokrąglany, liczy się tylko zakres użyteczny). "
                               "Jeśli różnica jest duża, sprawdź pojemność w konfiguracji."))
    except Exception:  # noqa: BLE001
        pass
    try:
        inv = rt.inverter_floor()
        src = inv.get("source") or "brak danych"
        fl = max(inv.get("hourly") or [0.0])
        if fl > 0:
            checks.append(_chk("floor", "Próg odcięcia baterii", "ok", f"do {fl:.0f}% ({src})"))
        else:
            checks.append(_chk("floor", "Próg odcięcia baterii", "warn", f"nie wykryto ({src})",
                               "Ustaw ręcznie „Próg odcięcia baterii w falowniku” (number.bms_inverter_floor_soc)."))
    except Exception as err:  # noqa: BLE001
        checks.append(_chk("floor", "Próg odcięcia baterii", "warn", str(err)))
    try:
        prof = get_profile()
        mode = getattr(prof, "mode", "zone")
        if mode == "zone":
            checks.append(_chk("tariff", "Taryfa", "ok", f"strefowa: {prof.label()} (szczyt: {prof.as_text()})"))
        else:
            from homeassistant.util import dt as dt_util
            today = dt_util.now().date()
            rep_b = rt.optimizer.buy_report() if hasattr(rt.optimizer, "buy_report") else {}
            hrs = (rep_b.get("today") or {}).get("hours", 0)
            src = (rep_b.get("today") or {}).get("source")
            seen = "; ".join((rep_b.get("seen") or [])[:3]) or "nie znaleziono encji zakupu"
            if prof.dynamic_for(today):
                checks.append(_chk("tariff", "Taryfa", "ok", f"{prof.label()} — ceny zakupu: {hrs} godz. z {src}"))
            elif mode == "dynamic":
                checks.append(_chk("tariff", "Taryfa", "error",
                                   f"Tryb dynamiczny, ale encja zakupu nie podaje dziś pełnej listy cen godzinowych ({hrs} godz.). "
                                   f"Planer używa okien z konfiguracji ({prof.as_text()}).",
                                   f"Wskaż encję zakupu z listą cen godzinowych (np. Pstryk: sensor.pstryk_json_buy). Odczyt encji: {seen}."))
            else:
                checks.append(_chk("tariff", "Taryfa", "ok",
                                   f"auto: encja zakupu nie podaje cen godzinowych o zmiennej wysokości ({hrs} godz.) — "
                                   f"taryfa strefowa, szczyt: {prof.as_text()}."))
    except Exception as err:  # noqa: BLE001
        checks.append(_chk("tariff", "Taryfa", "warn", str(err)))
    bs = rt.battery_sign()
    checks.append(_chk("sign", "Znak mocy baterii", "ok" if bs["source"] != "domyślny (Deye)" else "warn",
                       f"ładowanie = {'moc dodatnia' if bs['sign'] > 0 else 'moc ujemna'} ({bs['source']})",
                       "" if bs["source"] != "domyślny (Deye)" else
                       "Przyjęto konwencję Deye. Gdy strzałki baterii są odwrócone, ustaw number.bms_battery_charge_sign."))

    # --- harmonogram: encje czasu i przełączniki
    miss = [k for k, _ in TIMES if hass.states.get(find_eid(hass, "time", k)) is None]
    checks.append(_chk("times", "Godziny harmonogramu", "ok" if not miss else "error",
                       "wszystkie encje czasu istnieją" if not miss else "brak: " + ", ".join(miss),
                       "" if not miss else "Przeładuj integrację (Ustawienia → Urządzenia i usługi → EMS komp-dec → ⋮ → Przeładuj)."))

    # --- powiadomienia
    svc = str(cfg.get("notify_service") or "").strip()
    if svc:
        name = svc.split(".", 1)[1] if svc.startswith("notify.") else svc
        if hass.services.has_service("notify", name):
            checks.append(_chk("notify", "Powiadomienia na telefon", "ok", f"usługa notify.{name} istnieje"))
        else:
            checks.append(_chk("notify", "Powiadomienia na telefon", "error", f"Usługa notify.{name} nie istnieje.",
                               "Sprawdź nazwę w Narzędzia deweloperskie → Usługi (np. notify.mobile_app_<telefon>)."))
    else:
        checks.append(_chk("notify", "Powiadomienia na telefon", "warn",
                           "Nie ustawiono usługi — powiadomienia pojawią się tylko w Home Assistant (dzwonek).",
                           "Wpisz usługę w konfiguracji integracji (pole „Usługa powiadomień na telefon”)."))

    # --- karta: biblioteka wykresów z zewnętrznego serwera
    if _VENDOR_OK:
        checks.append(_chk("chartjs", "Biblioteka wykresów (Chart.js)", "ok", "lokalna kopia w folderze integracji"))
    else:
        checks.append(_chk("chartjs", "Biblioteka wykresów (Chart.js)", "warn",
                           "Wykres historii pobiera Chart.js z cdn.jsdelivr.net — skrypt z zewnętrznego serwera działa w interfejsie HA "
                           "z Twoją sesją, a przeglądarka nie sprawdza jego integralności.",
                           "Pobierz 2 pliki wymienione w custom_components/bms_komp_dec/frontend/vendor/README.txt, wgraj je do tego folderu "
                           "i zrestartuj HA — karta użyje kopii lokalnej i przestanie łączyć się z CDN."))

    n_err = sum(1 for c in checks if c["status"] == "error")
    n_warn = sum(1 for c in checks if c["status"] == "warn")
    cmds = commands_preview(rt)
    n_cmd_bad = sum(1 for c in cmds if not c["ok"])
    return {
        "version": VERSION,
        "checks": checks,
        "commands": cmds,
        "summary": {"errors": n_err, "warnings": n_warn, "ok": len(checks) - n_err - n_warn, "commands_failing": n_cmd_bad,
                    "ready": n_err == 0 and n_cmd_bad == 0},
    }
