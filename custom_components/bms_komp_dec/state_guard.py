"""Naprawa uszkodzonego zapisu stanu (.storage/bms_komp_dec_runtime) przy wczytywaniu.

Plik mógł zostać zmieniony ręcznie, uciąć się przy awarii zasilania albo pochodzić ze starszej wersji. Zły typ jednej wartości
nie może zatrzymać startu ani po cichu wyłączać funkcji (wyjątek w każdym ticku co 30 s). Znane klucze mają oczekiwany typ;
niezgodna wartość wraca do domyślnej, a nazwy naprawionych kluczy trafiają do dziennika."""
from __future__ import annotations

import math
from typing import Any

# słowniki o płaskich wartościach (liczby, napisy, bool, None) — pole z listą/słownikiem w środku oznacza uszkodzenie
FLAT_DICTS = ("price_reaction", "notified", "alarms_active", "soc_day", "soc_prev", "temp_alarm", "grid_outage", "high_import",
              "gc_stall", "notify_once", "summary_sent", "hint_done", "battery_sign_votes", "gc_catchup", "surplus", "grid_limit",
              "grid_batt", "live_apply")
# słowniki o dowolnej zawartości
DICTS = ("accuracy_fc", "last_applied", "notify_cfg", "grid_target_plan", "auto_skip", "sale_plan", "sale_actual", "sale_power_plan", "dev_ctl",
         "plan_sig", "dev_done", "rejected_props", "analysis_cfg", "zeroed", "day_reviews", "arb_proof", "pv_caution", "deeds", "fleet", "pricefeed", "fullcharge", "plan_snaps", "advice_applied")
LISTS = ("accuracy", "watches", "overrides", "auto_enabled", "auto_disabled", "auto_hist", "inbox", "settings_log")
FLOATS = ("today_charge", "today_pv", "yesterday_charge", "yesterday_pv")
INTS = ("inbox_seq", "settings_log_seq")
STRS = ("accuracy_done", "today_date", "yesterday_date", "report_sent", "sale_report_done", "pv_streak_day", "review_done")
NUMS = ("normal_charge_current", "storm_until", "vacation_since")     # liczba albo None
BOOLS = ("low_soc_active",)
DICT_OR_NONE = ("control_test", "profile")


def _scalar(v: Any) -> bool:
    if isinstance(v, float):
        return math.isfinite(v)
    return v is None or isinstance(v, (str, int, bool))


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def sanitize(state: dict[str, Any]) -> list[str]:
    """Poprawia `state` w miejscu; zwraca nazwy kluczy, które trzeba było zresetować."""
    fixed: list[str] = []

    def reset(k: str, val: Any) -> None:
        state[k] = val
        fixed.append(k)

    for k in FLAT_DICTS:
        if k in state and not (isinstance(state[k], dict) and all(isinstance(x, str) for x in state[k]) and all(_scalar(x) for x in state[k].values())):
            reset(k, {"pos": 0, "neg": 0} if k == "battery_sign_votes" else ({"active": False, "prev_mode": None} if k == "price_reaction" else {}))
    for k in DICTS:
        if k in state and not isinstance(state[k], dict):
            reset(k, {})
    for k in LISTS:
        if k in state and not isinstance(state[k], list):
            reset(k, [])
    for k in FLOATS:
        if k in state and not _num(state[k]):
            reset(k, 0.0)
    for k in INTS:
        if k in state and not (isinstance(state[k], int) and not isinstance(state[k], bool)):
            reset(k, int(state[k]) if _num(state[k]) else 0)
    for k in STRS:
        if k in state and state[k] is not None and not isinstance(state[k], str):
            reset(k, None)
    for k in NUMS:
        if k in state and state[k] is not None and not _num(state[k]):
            reset(k, None)
    for k in BOOLS:
        if k in state and not isinstance(state[k], bool):
            reset(k, False)
    for k in DICT_OR_NONE:
        if k in state and state[k] is not None and not isinstance(state[k], dict):
            reset(k, None)
    # wpisy list muszą być słownikami (watch.py, overrides.py, inbox.py, historia auto-stosowania czytają je przez .get)
    for k in ("watches", "overrides", "auto_hist", "inbox", "settings_log"):
        lst = state.get(k)
        if isinstance(lst, list) and any(not isinstance(x, dict) for x in lst):
            state[k] = [x for x in lst if isinstance(x, dict)]
            fixed.append(k)
    for k in ("auto_enabled", "auto_disabled"):
        lst = state.get(k)
        if isinstance(lst, list) and any(not isinstance(x, str) for x in lst):
            state[k] = [x for x in lst if isinstance(x, str)]
            fixed.append(k)
    # wpisy skrzynki: pola czytane jako napis/liczba (autoodczyt używa ich jako kluczy zbiorów i w arytmetyce)
    inbox = state.get("inbox")
    if isinstance(inbox, list):
        good = [e for e in inbox if isinstance(e, dict) and isinstance(e.get("kind"), str) and _num(e.get("ts", 0))
                and (e.get("level") is None or isinstance(e.get("level"), str))]
        if len(good) != len(inbox):
            state["inbox"] = good
            fixed.append("inbox")
    # SOC dnia i wczorajszy: min/max muszą być liczbami (jest na nich float())
    for k in ("soc_day", "soc_prev"):
        d = state.get(k)
        if isinstance(d, dict) and d and not (isinstance(d.get("date"), str) and _num(d.get("min")) and _num(d.get("max"))):
            reset(k, {})
    # prognoza dnia do oceny trafności
    fc = state.get("accuracy_fc")
    if isinstance(fc, dict) and fc and not (isinstance(fc.get("date"), str)
                                           and all(fc.get(x) is None or _num(fc.get(x)) for x in ("load", "pv"))):
        reset("accuracy_fc", {})
    # oceny planu po dobie: klucz = data, wartość musi dać się wyświetlić (inaczej karta by się wywróciła)
    revs = state.get("day_reviews")
    if isinstance(revs, dict):
        from .review import valid
        good = {k: v for k, v in revs.items() if isinstance(k, str) and valid(v)}
        if len(good) != len(revs):
            state["day_reviews"] = good
            fixed.append("day_reviews")
    arb = state.get("arb_proof")
    if isinstance(arb, dict):
        from .arbproof import clean as arb_clean
        good_arb = arb_clean(arb)
        if good_arb != arb:
            state["arb_proof"] = good_arb
            fixed.append("arb_proof")
    cps = state.get("custom_profiles")
    if cps is not None:
        from .profiles import clean_custom
        good_cp = clean_custom(cps)
        if good_cp != cps:
            state["custom_profiles"] = good_cp
            fixed.append("custom_profiles")
    if state.get("profile_plan") is not None:
        from .profiles import clean_plan
        good_pl = clean_plan(state.get("profile_plan"))
        if good_pl != state.get("profile_plan"):
            state["profile_plan"] = good_pl
            fixed.append("profile_plan")
    pvc = state.get("pv_caution")
    if isinstance(pvc, dict) and pvc:
        from .pvcaution import clean_state as pvc_clean
        good_pvc = pvc_clean(pvc)
        if good_pvc != pvc:
            state["pv_caution"] = good_pvc
            fixed.append("pv_caution")
    acc = state.get("accuracy")
    if isinstance(acc, list) and any(not isinstance(x, dict) for x in acc):
        state["accuracy"] = [x for x in acc if isinstance(x, dict)]
        fixed.append("accuracy")
    return fixed
