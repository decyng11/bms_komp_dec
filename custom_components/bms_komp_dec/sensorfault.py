"""Wykrywanie podejrzanych czujników: PV stoi na zerze mimo słonecznej prognozy albo SOC nie rusza się mimo przepływu mocy.

Moduł jest czysty (bez HA): dostaje próbki, trzyma stan w słowniku i zwraca listę usterek. Plan przy usterce PV nie ufa bieżącej
korekcie „na żywo” (zob. runtime/insights), żeby jeden martwy czujnik nie zaniżył prognozy na resztę dnia."""
from __future__ import annotations

from typing import Any

PV_ZERO_W = 20.0          # poniżej: PV „nie produkuje”
PV_ZERO_MIN = 90          # minut ciągłego zera w ciągu dnia, żeby uznać za usterkę
PV_DAY_FROM, PV_DAY_TO = 10, 15      # okno pewnego słońca (godziny lokalne)
PV_SUNNY_KWH = 4.0        # prognoza dnia, od której zero PV jest podejrzane
SOC_FLOW_W = 300.0        # moc baterii uznawana za realny przepływ
SOC_STUCK_MIN = 180       # minut przepływu bez zmiany SOC


def new_state() -> dict[str, Any]:
    return {"pv_zero_since": None, "soc": None, "soc_since": None, "soc_flow_s": 0.0, "last": None}


def update(st: dict[str, Any], now_ts: float, hour: int, pv_w: float | None, soc: float | None,
           bat_w: float | None, fc_kwh: float | None) -> list[dict[str, str]]:
    """Jeden krok (wołany co kilkadziesiąt sekund). Zwraca aktywne usterki: [{kind, text}]."""
    dt = 0.0 if st.get("last") is None else max(0.0, min(now_ts - st["last"], 600.0))
    st["last"] = now_ts
    # --- PV = 0 w słoneczny dzień
    sunny = fc_kwh is not None and fc_kwh >= PV_SUNNY_KWH and PV_DAY_FROM <= hour < PV_DAY_TO
    if pv_w is not None and sunny and pv_w < PV_ZERO_W:
        st["pv_zero_since"] = st.get("pv_zero_since") or now_ts
    else:
        st["pv_zero_since"] = None
    # --- SOC nie zmienia się mimo przepływu
    if soc is not None:
        if st.get("soc") is None or abs(soc - st["soc"]) >= 0.5:
            st["soc"], st["soc_since"], st["soc_flow_s"] = soc, now_ts, 0.0
        elif bat_w is not None and abs(bat_w) >= SOC_FLOW_W:
            st["soc_flow_s"] = st.get("soc_flow_s", 0.0) + dt
    faults: list[dict[str, str]] = []
    if st.get("pv_zero_since") and now_ts - st["pv_zero_since"] >= PV_ZERO_MIN * 60:
        faults.append({"kind": "pv_zero", "text": f"Produkcja PV wynosi 0 od {int((now_ts - st['pv_zero_since']) // 60)} min, "
                       f"a prognoza na dziś to {fc_kwh:.1f} kWh. Sprawdź czujnik mocy PV albo falownik."})
    if st.get("soc_flow_s", 0.0) >= SOC_STUCK_MIN * 60:
        faults.append({"kind": "soc_stuck", "text": f"SOC stoi na {st['soc']:.0f}% od {int(st['soc_flow_s'] // 60)} min mimo przepływu mocy "
                       "baterii. Sprawdź czujnik SOC albo łączność z BMS."})
    return faults


def pv_untrusted(faults: list[dict[str, str]] | None) -> bool:
    return any(f.get("kind") == "pv_zero" for f in faults or [])
