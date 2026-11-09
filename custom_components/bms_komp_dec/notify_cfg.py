"""Konfigurator powiadomień: katalog rodzajów, ustawienia użytkownika (włącz, telefon, odstęp, cisza nocna, progi)
i harmonogram podsumowań. Ustawienia trzyma runtime (rt.state["notify_cfg"]) — działają bez otwartej karty."""
from __future__ import annotations

import math
import re
from typing import Any

# Odstępy do wyboru (minuty): ile najkrócej między dwoma powiadomieniami tego samego rodzaju. 0 = bez limitu.
COOLDOWNS = (0, 5, 15, 30, 60, 180, 360, 720, 1200, 1440, 10080)

# key: (grupa, nazwa, opis, domyślnie włączone, domyślnie na telefon, odstęp [min], przez ciszę nocną, próg)
# próg: (etykieta, jednostka, domyślna, min, max, krok) albo None
CATALOG: dict[str, tuple] = {
    # --- bateria
    "low_soc": ("Bateria", "Niski stan baterii", "SOC spadł do progu odcięcia falownika (+3%).", True, True, 360, False, None),
    "battery_full": ("Bateria", "Bateria naładowana do pełna", "SOC osiągnął 100% (raz na dobę).", False, True, 1440, False, None),
    "grid_charge_target": ("Bateria", "Ładowanie z sieci poniżej celu", "Po końcu ładowania z sieci SOC jest niższy niż cel planu.", True, True, 720, False,
                           ("tolerancja", "pkt %", 5.0, 1.0, 30.0, 1.0)),
    "battery_temp_high": ("Bateria", "Wysoka temperatura baterii", "Temperatura baterii powyżej progu.", True, True, 180, True,
                          ("próg", "°C", 45.0, 30.0, 70.0, 1.0)),
    "battery_temp_low": ("Bateria", "Niska temperatura baterii", "Temperatura baterii poniżej progu (ładowanie LiFePO4 poniżej 0 °C szkodzi).", True, True, 360, False,
                         ("próg", "°C", 3.0, -20.0, 15.0, 1.0)),
    "battery_health": ("Bateria", "Spadek sprawności baterii", "Sprawność cyklu z 30 dni spadła względem 90 dni o więcej niż próg.", True, True, 10080, False,
                       ("spadek", "pkt %", 3.0, 1.0, 20.0, 0.5)),
    # --- falownik
    "alarm": ("Falownik", "Alarm falownika", "Kod błędu/ostrzeżenia z falownika (z opisem Fxx).", True, True, 60, True, None),
    "comm_loss": ("Falownik", "Brak danych z falownika", "Od 10 min brak odczytu SOC i mocy sieci.", True, True, 180, True, None),
    "grid_outage": ("Falownik", "Zanik i powrót sieci", "Napięcie sieci L1 spadło poniżej progu (praca z baterii) i wróciło.", True, True, 15, True,
                    ("próg napięcia", "V", 100.0, 50.0, 200.0, 5.0)),
    "command_unconfirmed": ("Falownik", "Falownik nie potwierdził komendy", "Po komendzie i jej ponowieniu stan falownika się nie zgadza.", True, True, 60, False, None),
    "drift": ("Falownik", "Parametr zmienił wartość po zapisie", "Wartość zapisana do falownika zmieniła się po kilku minutach.", True, True, 30, False, None),
    "guard_action": ("Falownik", "Zadziałało zabezpieczenie", "Zabezpieczenie zatrzymało sprzedaż albo odblokowało ładowanie z PV.", True, True, 60, False, None),
    "grid_limit": ("Falownik", "Przekroczony limit poboru z sieci", "Pobór z sieci przekracza ustawiony limit przyłącza mimo ograniczenia mocy ładowania.", True, True, 60, False, None),
    "high_import": ("Falownik", "Duży pobór z sieci", "Pobór z sieci powyżej progu przez 5 minut.", False, True, 60, False,
                    ("próg", "kW", 7.0, 1.0, 30.0, 0.5)),
    # --- ceny i plan
    "rce_missing": ("Ceny i plan", "Brak cen RCE na jutro", "Po 18:00 nadal brak pełnych cen RCE na jutro.", True, True, 1200, False, None),
    "rce_negative": ("Ceny i plan", "Niskie / ujemne ceny RCE jutro", "Jutro są godziny z ceną sprzedaży ≤ progu — lepiej ładować baterię niż eksportować.", True, True, 1440, False,
                     ("próg", "zł/kWh", 0.0, -1.0, 1.0, 0.01)),
    "arbitrage_window": ("Ceny i plan", "Okno arbitrażu jutro", "Jutro opłaca się kupić tanio i sprzedać drogo: zysk z 1 kWh po stracie cyklu przekracza próg.", True, True, 1440, False,
                         ("min. zysk", "zł/kWh", 0.30, 0.0, 3.0, 0.05)),
    "rce_high": ("Ceny i plan", "Wysoka cena sprzedaży jutro", "Jutro cena RCE przekracza próg; podaje godzinę i plan sprzedaży.", True, True, 1440, False,
                 ("próg", "zł/kWh", 1.0, 0.1, 5.0, 0.05)),
    "buy_prices_missing": ("Ceny i plan", "Brak cen zakupu (taryfa dynamiczna)", "Taryfa dynamiczna, a encja zakupu nie podaje cen godzinowych na dziś.", True, True, 1440, False, None),
    "pv_forecast_missing": ("Ceny i plan", "Brak prognozy PV", "Po 18:00 brak godzinowej prognozy PV na jutro (Solcast / Forecast.Solar).", True, True, 1440, False, None),
    "weak_pv": ("Ceny i plan", "Słaba prognoza PV na jutro", "Prognoza PV na jutro poniżej progu (z informacją o planowanym ładowaniu z sieci).", True, True, 1440, False,
                ("próg", "kWh", 3.0, 0.5, 50.0, 0.5)),
    "load_above": ("Ceny i plan", "Zużycie dziś ponad prognozę", "Prognoza bieżąca zużycia (tempo dnia) wyższa niż prognoza dnia o więcej niż próg.", True, True, 1440, False,
                   ("próg", "%", 30.0, 10.0, 200.0, 5.0)),
    "proposal": ("Ceny i plan", "Codzienna propozycja harmonogramu", "Propozycja z 16:00 (co by się zmieniło w godzinach).", True, False, 0, False, None),
    "auto_apply": ("Ceny i plan", "Auto-stosowanie zmieniło harmonogram", "Które godziny zmieniono (z możliwością cofnięcia).", True, True, 0, False, None),
    "plan_floor": ("Ceny i plan", "Plan: bateria dojdzie do progu", "Plan 24 h przewiduje zejście SOC do progu odcięcia falownika w ciągu 16 h (dom pobierałby z sieci), mimo zaplanowanego ładowania i sprzedaży.", True, True, 720, False, None),
    "plan_error": ("Ceny i plan", "Plan niedostępny", "Planer nie mógł policzyć planu (np. brak SOC).", True, True, 360, False, None),
    "schedule_skipped": ("Ceny i plan", "Pominięty start harmonogramu", "Start sprzedaży/ładowania pominięty (SOC, cena, zabezpieczenie).", False, True, 60, False, None),
    # --- działanie
    "sale": ("Działanie", "Sprzedaż z baterii: start i koniec", "Harmonogram rozpoczął albo zakończył sprzedaż.", False, True, 0, False, None),
    "grid_charge": ("Działanie", "Ładowanie z sieci: start i koniec", "Harmonogram włączył albo wyłączył ładowanie z sieci.", False, True, 0, False, None),
    "price_reaction": ("Działanie", "Reakcja na niską cenę", "Eksport wstrzymany przy niskiej/ujemnej cenie RCE i wznowiony.", False, True, 0, False, None),
    "storm": ("Działanie", "Tryb burzowy", "Włączenie i automatyczne wyłączenie trybu burzowego.", True, True, 5, False, None),
    # --- urządzenia (zakładka „Urządzenia”; przy każdym urządzeniu można też wyłączyć jego powiadomienia)
    "device_cycle": ("Urządzenia", "Koniec cyklu urządzenia", "Pralka, zmywarka, suszarka… skończyła — czas, kWh i koszt cyklu.", True, True, 0, False, None),
    "device_anomaly": ("Urządzenia", "Nietypowa praca urządzenia", "Ciągła praca dłużej niż limit urządzenia albo zużycie dnia ponad 2× typowe.", True, True, 360, False, None),
    "device_hint": ("Urządzenia", "Uruchom teraz (urządzenia elastyczne)", "Nadwyżka PV albo najtańsza godzina — dobry moment na pralkę, bojler, auto… (raz na dobę na urządzenie).", True, True, 0, False, None),
    "device_plan": ("Urządzenia", "Plan dla elastycznych urządzeń", "Wieczorem: najlepsze okno na jutro dla każdego elastycznego urządzenia.", True, False, 0, False, None),
    "devices_unknown": ("Urządzenia", "Nierozpoznany odbiornik", "Powtarzalny pobór w „reszcie domu” o tej samej godzinie — warto dodać takie urządzenie.", True, False, 10080, False, None),
    "island_overload": ("Urządzenia", "Duży pobór przy zaniku sieci", "W czasie zaniku sieci pobór domu przekracza próg — lista urządzeń, które obciążają baterię.", True, True, 15, True,
                        ("próg", "kW", 5.0, 0.5, 30.0, 0.5)),
    # --- podsumowania (godziny w części „Harmonogram podsumowań”)
    "summary_daily": ("Podsumowania", "Podsumowanie dnia", "Bilans zł, energia, SOC min/max, co zrobił harmonogram, jutro: PV i plan.", True, True, 0, False, None),
    "summary_weekly": ("Podsumowania", "Podsumowanie tygodnia", "Sumy tygodnia, porównanie z poprzednim, najlepszy/najgorszy dzień, sprawność.", True, True, 0, False, None),
    "summary_monthly": ("Podsumowania", "Raport miesięczny", "Raport za poprzedni miesiąc z porównaniem do wcześniejszego.", True, True, 0, False, None),
}
GROUPS = ("Bateria", "Falownik", "Ceny i plan", "Działanie", "Urządzenia", "Podsumowania")
DEFAULT_SCHED = {
    "quiet": {"on": False, "start": "22:00", "end": "07:00"},
    "daily": {"time": "21:00"},
    "weekly": {"weekday": 6, "time": "20:00"},        # 0 = poniedziałek … 6 = niedziela
    "monthly": {"day": 1, "time": "08:00"},
}
_HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _kind_default(key: str) -> dict[str, Any]:
    g, _n, _d, on, phone, cd, quiet_ok, thr = CATALOG[key]
    out = {"on": on, "phone": phone, "cooldown": cd, "quiet_ok": quiet_ok}
    if thr:
        out["thr"] = thr[2]
    return out


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _hm(v: Any, default: str) -> str:
    s = str(v or "").strip()[:5]
    return s if _HM.match(s) else default


def effective(raw: dict | None) -> dict[str, Any]:
    """Ustawienia użytkownika nałożone na domyślne; śmieci i nieznane klucze są pomijane."""
    raw = raw if isinstance(raw, dict) else {}
    kinds_raw = raw.get("kinds") if isinstance(raw.get("kinds"), dict) else {}
    kinds: dict[str, dict] = {}
    for key, spec in CATALOG.items():
        k = _kind_default(key)
        r = kinds_raw.get(key) if isinstance(kinds_raw.get(key), dict) else {}
        for b in ("on", "phone", "quiet_ok"):
            if isinstance(r.get(b), bool):
                k[b] = r[b]
        cd = _num(r.get("cooldown"))
        if cd is not None and int(cd) in COOLDOWNS:
            k["cooldown"] = int(cd)
        thr = spec[7]
        if thr:
            t = _num(r.get("thr"))
            if t is not None:
                k["thr"] = min(thr[4], max(thr[3], t))
        kinds[key] = k
    sched_raw = raw.get("sched") if isinstance(raw.get("sched"), dict) else {}
    q = sched_raw.get("quiet") if isinstance(sched_raw.get("quiet"), dict) else {}
    d = sched_raw.get("daily") if isinstance(sched_raw.get("daily"), dict) else {}
    w = sched_raw.get("weekly") if isinstance(sched_raw.get("weekly"), dict) else {}
    m = sched_raw.get("monthly") if isinstance(sched_raw.get("monthly"), dict) else {}
    wd = _num(w.get("weekday"))
    md = _num(m.get("day"))
    sched = {
        "quiet": {"on": bool(q.get("on")) if isinstance(q.get("on"), bool) else DEFAULT_SCHED["quiet"]["on"],
                  "start": _hm(q.get("start"), DEFAULT_SCHED["quiet"]["start"]),
                  "end": _hm(q.get("end"), DEFAULT_SCHED["quiet"]["end"])},
        "daily": {"time": _hm(d.get("time"), DEFAULT_SCHED["daily"]["time"])},
        "weekly": {"weekday": int(wd) if wd is not None and 0 <= wd <= 6 else DEFAULT_SCHED["weekly"]["weekday"],
                   "time": _hm(w.get("time"), DEFAULT_SCHED["weekly"]["time"])},
        "monthly": {"day": int(md) if md is not None and 1 <= md <= 28 else DEFAULT_SCHED["monthly"]["day"],
                    "time": _hm(m.get("time"), DEFAULT_SCHED["monthly"]["time"])},
    }
    return {"kinds": kinds, "sched": sched}


def kind(cfg: dict, key: str) -> dict[str, Any]:
    """Ustawienia jednego rodzaju (nieznany rodzaj, np. „test” → włączony, na telefon, bez limitu)."""
    k = (cfg.get("kinds") or {}).get(key)
    if k is None:
        return _kind_default(key) if key in CATALOG else {"on": True, "phone": True, "cooldown": 0, "quiet_ok": True}
    return k


def threshold(cfg: dict, key: str) -> float | None:
    k = kind(cfg, key)
    spec = CATALOG.get(key)
    return k.get("thr", spec[7][2] if spec and spec[7] else None)


def in_quiet(cfg: dict, hour: int, minute: int) -> bool:
    """Czy godzina hh:mm wypada w ciszy nocnej (okno może przechodzić przez północ)."""
    q = (cfg.get("sched") or {}).get("quiet") or {}
    if not q.get("on"):
        return False
    s = int(q["start"][:2]) * 60 + int(q["start"][3:5])
    e = int(q["end"][:2]) * 60 + int(q["end"][3:5])
    t = hour * 60 + minute
    if s == e:
        return False
    return s <= t < e if s < e else (t >= s or t < e)


def catalog_payload() -> list[dict[str, Any]]:
    """Opis rodzajów dla karty (kolejność = kolejność wyświetlania)."""
    out = []
    for key, (g, n, d, on, phone, cd, quiet_ok, thr) in CATALOG.items():
        item = {"key": key, "group": g, "name": n, "desc": d,
                "default": {"on": on, "phone": phone, "cooldown": cd, "quiet_ok": quiet_ok}}
        if thr:
            item["thr"] = {"label": thr[0], "unit": thr[1], "default": thr[2], "min": thr[3], "max": thr[4], "step": thr[5]}
        out.append(item)
    return out
