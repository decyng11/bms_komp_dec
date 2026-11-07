"""Statystyki baterii i dzienne liczniki: sprawność cyklu, szacunek pojemności, dane do raportu miesięcznego.

• Dzienne liczniki (PV, zużycie, import/eksport, ładowanie/rozładowanie baterii, SOC na początku i końcu doby)
  zapisujemy w osobnym magazynie — księga zysków (ledger) przechowuje tylko przepływy z/do sieci.
• Sprawność cyklu doby = (oddana energia + zmiana zmagazynowanej energii) / pobrana energia. Liczymy tylko doby
  z wyraźnym ładowaniem (≥ 2 kWh); wartości spoza 50–105% odrzucamy jako błąd odczytu.
• Pojemność: całkujemy moc baterii w ciągłych odcinkach ładowania (zmiana SOC ≥ 15 pkt, bez końcówki > 95%),
  co daje orientacyjny szacunek pojemności użytecznej. To ESTYMACJA (SOC jest całkowity, a falownik zaokrągla),
  więc pokazujemy medianę z wielu odcinków i nie traktujemy jej jako pomiaru zdrowia baterii.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .helpers import ThrottledStore

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "bms_komp_dec_battery_stats"
KEEP_DAYS = 400
MIN_CHARGE_KWH = 2.0
EFF_RANGE = (0.5, 1.05)
MAX_GAP_S = 150
MIN_CHARGE_W = 200.0
END_GAP_S = 300
MIN_DELTA_SOC = 15.0
MAX_END_SOC = 95.0
CAP_KEEP = 40
CELL_CHARGE_EFF = 0.97            # część energii wprowadzonej, która faktycznie zostaje w ogniwach

_FIELDS = ("pv", "load", "imp", "exp", "chg", "dis")


def _f(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


class BatteryStats:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = ThrottledStore(hass, 1, STORAGE_KEY, delay=300)
        self.days: dict[str, dict[str, float]] = {}
        self.caps: list[dict[str, Any]] = []
        self._iv: dict[str, Any] | None = None          # trwający odcinek ładowania
        self._last_ts: float | None = None

    async def async_load(self) -> None:
        try:
            data = await self._store.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS stats: błąd wczytywania: %s", err)
            return
        if not isinstance(data, dict):
            return
        for k, v in (data.get("days") or {}).items():
            if isinstance(v, dict):
                self.days[str(k)] = {f: x for f, x in ((f, _f(v.get(f))) for f in (*_FIELDS, "soc0", "soc1", "t1h")) if x is not None}
        if isinstance(data.get("caps"), list):
            self.caps = [c for c in data["caps"] if isinstance(c, dict) and _f(c.get("cap")) is not None][-CAP_KEEP:]

    def _data(self) -> dict[str, Any]:
        return {"days": self.days, "caps": self.caps[-CAP_KEEP:]}

    # ------------------------------------------------------------- dzienne liczniki
    def update_day(self, now: datetime, data: dict[str, Any], soc: float | None) -> None:
        """Wołane z koordynatora (co ~10 s). Liczniki „dziś” rosną w ciągu doby — trzymamy największą wartość."""
        loc = dt_util.as_local(now)
        key = loc.date().isoformat()
        hm = loc.hour + loc.minute / 60.0
        src = {"pv": "energy_pv_today", "load": "energy_load_today", "imp": "energy_grid_import_today",
               "exp": "energy_grid_export_today", "chg": "energy_battery_charge_today",
               "dis": "energy_battery_discharge_today"}
        day = self.days.get(key)
        if day is None:
            day = self.days[key] = {}
        changed = False
        # SOC na początku doby ma sens tylko, gdy złapaliśmy go tuż po północy (po restarcie w ciągu dnia go nie ma
        # i taka doba nie wchodzi do sprawności); „koniec doby” = ostatni odczyt, wraz z godziną tego odczytu.
        if soc is not None:
            if "soc0" not in day and hm < 0.25:
                day["soc0"] = float(soc)
                changed = True
            if day.get("soc1") != float(soc):
                day["soc1"] = float(soc)
                changed = True
            if abs(day.get("t1h", -1) - hm) > 0.01:
                day["t1h"] = round(hm, 3)
                changed = True
        # tuż po północy licznik „dziś” bywa jeszcze wczorajszy (falownik zeruje go z opóźnieniem)
        if hm >= 5 / 60.0:
            for f, k in src.items():
                v = _f(data.get(k))
                if v is not None and v >= 0 and v >= day.get(f, 0.0) - 1e-9 and v != day.get(f):
                    day[f] = v
                    changed = True
        if changed:
            self._store.request_save(self._data)
            if len(self.days) > KEEP_DAYS + 5:
                for k in sorted(self.days)[: len(self.days) - KEEP_DAYS]:
                    self.days.pop(k, None)

    # ------------------------------------------------------------------- sprawność
    @staticmethod
    def day_eff(day: dict[str, float], cap_kwh: float) -> float | None:
        chg, dis = day.get("chg"), day.get("dis")
        if chg is None or dis is None or chg < MIN_CHARGE_KWH or "soc0" not in day or "soc1" not in day:
            return None
        if day.get("t1h", 0.0) < 23.5:          # doba niepełna (np. HA był wyłączony pod koniec dnia)
            return None
        stored = (day["soc1"] - day["soc0"]) / 100.0 * cap_kwh
        eff = (dis + stored) / chg
        return eff if EFF_RANGE[0] <= eff <= EFF_RANGE[1] else None

    def efficiency(self, cap_kwh: float, days: int | None = None, today: date | None = None) -> tuple[float | None, int]:
        """(sprawność ważona energią, liczba użytych dób) z ostatnich `days` dób (bez bieżącej, niepełnej)."""
        today = today or dt_util.now().date()
        num = den = 0.0
        used = 0
        for k in sorted(self.days, reverse=True):
            if k >= today.isoformat():
                continue
            if days is not None and (today - date.fromisoformat(k)).days > days:
                break
            d = self.days[k]
            e = self.day_eff(d, cap_kwh)
            if e is None:
                continue
            num += d["dis"] + (d["soc1"] - d["soc0"]) / 100.0 * cap_kwh
            den += d["chg"]
            used += 1
        return (num / den if den > 0 else None), used

    def period_efficiency(self, prefix: str, cap_kwh: float) -> tuple[float | None, int]:
        """Sprawność cyklu z dób o danym prefiksie daty (np. „2026-10-”) — do raportu miesięcznego."""
        num = den = 0.0
        used = 0
        for k, d in self.days.items():
            if not k.startswith(prefix) or self.day_eff(d, cap_kwh) is None:
                continue
            num += d["dis"] + (d["soc1"] - d["soc0"]) / 100.0 * cap_kwh
            den += d["chg"]
            used += 1
        return (num / den if den > 0 else None), used

    # --------------------------------------------------------------------- pojemność
    def add_power(self, now: datetime, soc: float | None, power_w: float | None, charge_sign: int) -> None:
        """Całkuje energię ładowania w ciągłych odcinkach (charge_sign = znak mocy przy ładowaniu)."""
        ts = now.timestamp()
        prev, self._last_ts = self._last_ts, ts
        if soc is None or power_w is None:
            self._close(ts, soc)
            return
        p = power_w * (1 if charge_sign >= 0 else -1)          # dodatnia = ładowanie
        gap = prev is not None and ts - prev > MAX_GAP_S
        if p >= MIN_CHARGE_W and not gap:
            if self._iv is None:
                self._iv = {"soc0": float(soc), "e": 0.0, "t0": ts, "last_p": ts}
            elif prev is not None:
                self._iv["e"] += p * (ts - prev) / 3_600_000.0
                self._iv["last_p"] = ts
            self._iv["soc1"] = float(soc)
        elif self._iv is not None and (gap or ts - self._iv["last_p"] > END_GAP_S):
            self._close(ts, soc)

    def _close(self, ts: float, soc: float | None) -> None:
        iv, self._iv = self._iv, None
        if not iv:
            return
        soc1 = iv.get("soc1")
        if soc1 is None:
            return
        d = soc1 - iv["soc0"]
        if d >= MIN_DELTA_SOC and soc1 <= MAX_END_SOC and iv["e"] > 0.2:
            cap = iv["e"] * CELL_CHARGE_EFF / (d / 100.0)
            self.caps.append({"t": int(ts), "cap": round(cap, 2), "dsoc": round(d, 1), "e": round(iv["e"], 2)})
            del self.caps[:-CAP_KEEP]
            self._store.request_save(self._data)

    def capacity_estimate(self) -> tuple[float | None, int]:
        vals = [float(c["cap"]) for c in self.caps[-15:] if _f(c.get("cap")) is not None]
        if len(vals) < 3:
            return None, len(vals)
        return round(statistics.median(vals), 2), len(vals)

    # ----------------------------------------------------------------------- podsumowanie
    def summary(self, cap_kwh: float) -> dict[str, Any]:
        e7, n7 = self.efficiency(cap_kwh, 7)
        e30, n30 = self.efficiency(cap_kwh, 30)
        e90, n90 = self.efficiency(cap_kwh, 90)
        est, n_est = self.capacity_estimate()
        trend = None
        if e30 is not None and e90 is not None and n90 >= 15 and n30 >= 5:
            trend = round((e30 - e90) * 100.0, 1)                 # pkt proc.: ostatnie 30 dni względem 90
        out: dict[str, Any] = {
            "eff_7d": None if e7 is None else round(e7 * 100.0, 1), "days_7d": n7,
            "eff_30d": None if e30 is None else round(e30 * 100.0, 1), "days_30d": n30,
            "eff_90d": None if e90 is None else round(e90 * 100.0, 1), "days_90d": n90,
            "eff_trend_pp": trend,
            "capacity_est_kwh": est, "capacity_samples": n_est,
            "capacity_configured_kwh": round(cap_kwh, 2),
            "soh_est_pct": None if est is None or cap_kwh <= 0 else round(est / cap_kwh * 100.0, 0),
        }
        return out
