"""Eksport i import ustawień EMS do pliku JSON (kopia, przeniesienie na inną instalację).

Moduł jest czysty (bez HA): zbiera wartości przełączników i liczb, własne profile, ustawienia powiadomień i analiz, a przy imporcie
sprawdza każdą wartość (typ, zakres) i zwraca listę zmian do zatwierdzenia. Nie eksportuje trybu próbnego marki (nowa instalacja
może mieć inną markę falownika) ani niczego, co jest sekretem (adresy, tokeny)."""
from __future__ import annotations

import json
from typing import Any, Callable

from . import analysis as analysis_mod
from . import profiles as prof_mod

FORMAT = "bms_komp_dec_settings"
SKIP_KEYS = frozenset({"brand_test_mode"})
MAX_BYTES = 200_000


def value_keys() -> list[str]:
    return [k for k in list(prof_mod.SW_LABEL) + list(prof_mod.NUM_META) if k not in SKIP_KEYS]


def build(read: Callable[[str], Any], state: dict[str, Any], app_version: str, stamp: str) -> dict[str, Any]:
    vals = {}
    for k in value_keys():
        v = read(k)
        if v is not None:
            vals[k] = v
    nc = state.get("notify_cfg")
    return {"format": FORMAT, "schema": 1, "app_version": app_version, "exported_at": stamp, "values": vals,
            "custom_profiles": prof_mod.clean_custom(state.get("custom_profiles")),
            "notify_cfg": nc if isinstance(nc, dict) else {},
            "analysis_cfg": analysis_mod.clean_cfg(state.get("analysis_cfg"))}


def parse(data: Any) -> dict[str, Any]:
    """Przyjmuje słownik albo tekst JSON; ValueError z polskim opisem, gdy to nie jest plik ustawień EMS."""
    if isinstance(data, (str, bytes)):
        if len(data) > MAX_BYTES:
            raise ValueError("Plik jest za duży na plik ustawień EMS")
        try:
            data = json.loads(data)
        except ValueError as err:
            raise ValueError("To nie jest poprawny plik JSON") from err
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("To nie jest plik ustawień EMS komp-dec")
    if data.get("schema") != 1:
        raise ValueError("Plik pochodzi z nowszej wersji formatu — zaktualizuj integrację")
    if len(json.dumps(data)) > MAX_BYTES:
        raise ValueError("Plik jest za duży na plik ustawień EMS")
    return data


def plan(data: dict[str, Any], read: Callable[[str], Any], state: dict[str, Any]) -> dict[str, Any]:
    """Co zmieni import: lista zmian wartości (tylko różne od bieżących), pominięte klucze oraz zmiany w profilach/powiadomieniach/analizach."""
    changes, skipped = [], []
    raw = data.get("values") if isinstance(data.get("values"), dict) else {}
    allowed = set(value_keys())
    for k, v in raw.items():
        if not isinstance(k, str) or k not in allowed:
            skipped.append(str(k)[:60])
            continue
        cv = prof_mod.check_value(k, v)
        if cv is None:
            skipped.append(k)
            continue
        cur = read(k)
        if cur is not None and prof_mod.same(cur, cv):
            continue
        changes.append({"key": k, "label": prof_mod.label(k), "now": prof_mod.fmt(k, cur) if cur is not None else "—", "to": prof_mod.fmt(k, cv), "value": cv})
    prof = prof_mod.clean_custom(data.get("custom_profiles"))
    nc = data.get("notify_cfg") if isinstance(data.get("notify_cfg"), dict) else None
    an = analysis_mod.clean_cfg(data.get("analysis_cfg")) if isinstance(data.get("analysis_cfg"), dict) else None
    extras = []
    if prof and prof != prof_mod.clean_custom(state.get("custom_profiles")):
        extras.append(f"własne profile: {len(prof)}")
    if nc and nc != (state.get("notify_cfg") or {}):
        extras.append("ustawienia powiadomień")
    if an and an != analysis_mod.clean_cfg(state.get("analysis_cfg")):
        extras.append("ustawienia analiz")
    return {"changes": changes, "skipped": skipped, "extras": extras, "profiles": prof, "notify_cfg": nc, "analysis_cfg": an}
