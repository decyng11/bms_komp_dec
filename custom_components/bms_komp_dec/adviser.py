"""Asystent konfiguracji: kilka prostych reguł porównujących USTAWIENIA z tym, co faktycznie działo się w ostatnich dniach.

Dla instalacji, którymi nikt na bieżąco się nie opiekuje. Nic nie zmienia — tylko podpowiada, z uzasadnieniem w liczbach.
Czyste funkcje, bez HA."""
from __future__ import annotations

import math
from typing import Any

RESERVE_GAP = 25.0       # rezerwa „za wysoka”: najniższy SOC z dni jest o tyle wyższy od rezerwy
MIN_SOC_DAYS = 7         # tyle dób z odczytem SOC potrzeba do oceny rezerwy
CAP_DEVIATION = 0.20     # pojemność zmierzona różni się od ustawionej o więcej niż 20%
CAP_MIN_SAMPLES = 5
MAX_ADVICE = 5


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _item(aid: str, level: str, title: str, text: str) -> dict[str, str]:
    return {"id": aid, "level": level, "title": title, "text": text}


def advise(facts: Any) -> list[dict[str, str]]:
    """facts: reserve_pct, soc_min, soc_days, cap_conf, cap_est, cap_samples, battery_price, sell_windows_on. Brak pola = reguła pomijana."""
    f = facts if isinstance(facts, dict) else {}
    out: list[dict[str, str]] = []
    res, smin, sd = _num(f.get("reserve_pct")), _num(f.get("soc_min")), _num(f.get("soc_days"))
    if res is not None and smin is not None and sd is not None and sd >= MIN_SOC_DAYS and res >= 20 and smin - res >= RESERVE_GAP:
        sug = res - 10.0
        out.append(_item("reserve_high", "info", "Rezerwa baterii nigdy nie była użyta",
                         f"Rezerwa jest ustawiona na {res:.0f}%, a przez ostatnie {sd:.0f} dób bateria nie spadła poniżej {smin:.0f}%. "
                         f"Jeśli chcesz, by plan częściej korzystał z baterii (np. do sprzedaży), możesz obniżyć rezerwę o 10 pkt, do {sug:.0f}%. "
                         "Zostaw ją, jeśli zależy Ci na zapasie na wypadek zaniku sieci."))
    ce, cc, cs = _num(f.get("cap_est")), _num(f.get("cap_conf")), _num(f.get("cap_samples"))
    if ce is not None and cc is not None and cc > 0 and cs is not None and cs >= CAP_MIN_SAMPLES and abs(ce / cc - 1.0) > CAP_DEVIATION:
        out.append(_item("capacity_mismatch", "warn", "Pojemność baterii w ustawieniach nie zgadza się z pomiarem",
                         f"W ustawieniach jest {cc:.1f} kWh, a z {cs:.0f} pomiarów wychodzi ok. {ce:.1f} kWh. "
                         "Błędna pojemność psuje plan (czas ładowania, ile można sprzedać) — sprawdź ją albo poczekaj na więcej pomiarów."))
    bp = _num(f.get("battery_price"))
    if bp is not None and bp <= 0 and f.get("sell_windows_on"):
        out.append(_item("wear_zero", "info", "Koszt zużycia baterii nie jest ustawiony",
                         "Przy cenie baterii 0 plan nie wlicza zużycia cykli, więc może sprzedawać także przy bardzo małym zysku. "
                         "Wpisz cenę baterii i liczbę cykli życia (Ustawienia → Liczby), żeby plan sprzedawał tylko wtedy, gdy się to opłaca."))
    return out[:MAX_ADVICE]
