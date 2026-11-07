"""Godzinowy dziennik energii, oszczędności (3 warianty) i trafność prognoz.

Co ~10 s (razem z księgą PLN) całkujemy moce z koordynatora do koszyków godzinowych: zużycie domu, PV, import,
eksport, ładowanie i rozładowanie baterii oraz średnie ceny zakupu i sprzedaży. Z tego liczymy dla każdego dnia
koszt energii w trzech wariantach:
  • „rzeczywistość” — import × cena zakupu − eksport × cena sprzedaży (to, co faktycznie przepłynęło przez licznik),
  • „bez baterii” — dom bierze z sieci to, czego nie pokryje PV, a nadwyżkę PV oddaje,
  • „bateria bez planera” — prosta autokonsumpcja: bateria ładuje się tylko z nadwyżki PV i oddaje do domu
    (bez ładowania z sieci i bez sprzedaży), z tymi samymi limitami mocy, sprawnością i progiem rozładowania.
Wyniki są liczone od dnia instalacji tej wersji (wstecz nie ma danych godzinowych).

Trafność prognoz: rano zapisujemy prognozę PV na dziś (surową, bez korekty) i plan SOC, a po północy dopisujemy
wykonanie. Zużycie bierzemy z historii modelu zużycia (prognoza wydana dzień wcześniej i rzeczywiste kWh).
Z ostatnich 14 dni liczymy współczynnik korekty prognozy PV (0,7–1,2), którego używa planer.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .helpers import ThrottledStore

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "bms_komp_dec_insights"
STORAGE_VERSION = 1
KEEP_HOURS_DAYS = 62          # koszyki godzinowe
KEEP_DAYS = 400               # wyniki dzienne (oszczędności)
KEEP_FC_DAYS = 90             # prognoza vs wykonanie
MAX_GAP_S = 120.0             # dłuższa przerwa w odczytach (restart) nie jest całkowana
MAX_POWER_W = 100000.0
MIN_HOURS_COMPLETE = 20       # dzień z co najmniej tyloma godzinami danych liczy się do sum
SNAPSHOT_HOUR = 6             # od tej godziny zapisujemy poranną prognozę PV i plan SOC

PV_CORR_DAYS = 14
PV_CORR_MIN_DAYS = 5
PV_CORR_MIN_FC = 1.0          # dni z prognozą < 1 kWh nie liczą się do korekty (za duży szum)
PV_CORR_LO, PV_CORR_HI = 0.7, 1.2

# indeksy w koszyku godzinowym
LOAD, PV, IMP, EXP, BCH, BDIS, BUY_S, BUY_T, SELL_S, SELL_T, SOC = range(11)
_BUCKET_LEN = 11


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _blank_bucket() -> list:
    return [0.0] * 10 + [None]


def _hour_key(t: datetime) -> str:
    loc = dt_util.as_local(t)
    return f"{loc.date().isoformat()}T{loc.hour:02d}"


# ------------------------------------------------------------------ obliczenia (czyste funkcje, testowalne)
def hour_prices(b: list) -> tuple[float | None, float | None]:
    buy = b[BUY_S] / b[BUY_T] if b[BUY_T] > 0 else None
    sell = b[SELL_S] / b[SELL_T] if b[SELL_T] > 0 else None
    return buy, sell


def day_costs(buckets: list[list | None], *, cap_kwh: float, eff: float, floor_pct: float,
              max_chg_kw: float, max_dis_kw: float, soc0: float | None) -> dict[str, Any] | None:
    """Koszt dnia w trzech wariantach (zł). buckets: 24 koszyki (None = brak danych w tej godzinie)."""
    have = [b for b in buckets if b is not None and (b[LOAD] > 0 or b[PV] > 0 or b[IMP] > 0 or b[EXP] > 0)]
    if not have:
        return None
    buys = [p for p in (hour_prices(b)[0] for b in have) if p is not None]
    sells = [p for p in (hour_prices(b)[1] for b in have) if p is not None]
    if not buys:
        return None
    buy_avg = sum(buys) / len(buys)
    sell_avg = sum(sells) / len(sells) if sells else 0.0
    cap = max(0.1, float(cap_kwh))
    k = math.sqrt(min(1.0, max(0.5, eff)))         # sprawność cyklu rozłożona po równo na ładowanie i rozładowanie
    e_min = cap * min(100.0, max(0.0, floor_pct)) / 100.0
    e = cap * min(100.0, max(0.0, soc0 if soc0 is not None else 50.0)) / 100.0
    e = max(e_min, min(cap, e))
    out = {"actual": 0.0, "nobat": 0.0, "simple": 0.0, "hours": 0,
           "load_kwh": 0.0, "pv_kwh": 0.0, "import_kwh": 0.0, "export_kwh": 0.0,
           "nobat_import_kwh": 0.0, "simple_import_kwh": 0.0}
    for b in buckets:
        if b is None:
            continue
        buy, sell = hour_prices(b)
        buy = buy_avg if buy is None else buy
        sell = sell_avg if sell is None else sell
        load, pv = max(0.0, b[LOAD]), max(0.0, b[PV])
        out["hours"] += 1
        out["load_kwh"] += load
        out["pv_kwh"] += pv
        out["import_kwh"] += b[IMP]
        out["export_kwh"] += b[EXP]
        # rzeczywistość
        out["actual"] += b[IMP] * buy - b[EXP] * sell
        # bez baterii
        net = load - pv
        imp0, exp0 = max(0.0, net), max(0.0, -net)
        out["nobat"] += imp0 * buy - exp0 * sell
        out["nobat_import_kwh"] += imp0
        # bateria bez planera (autokonsumpcja)
        if net < 0:
            c = min(-net, max_chg_kw, max(0.0, (cap - e) / k))
            e += c * k
            imp1, exp1 = 0.0, -net - c
        else:
            d = min(net, max_dis_kw, max(0.0, (e - e_min) * k))
            e -= d / k
            imp1, exp1 = net - d, 0.0
        out["simple"] += imp1 * buy - exp1 * sell
        out["simple_import_kwh"] += imp1
    for key in list(out):
        if isinstance(out[key], float):
            out[key] = round(out[key], 3)
    out["complete"] = out["hours"] >= MIN_HOURS_COMPLETE
    return out


def pv_correction(fc: dict[str, dict], today: date) -> dict[str, Any]:
    """Współczynnik korekty prognozy PV z ostatnich dni: Σ wykonanie / Σ prognoza, ściągnięty do 1 przy małej
    liczbie dni, ograniczony do 0,7–1,2."""
    days = []
    for i in range(1, PV_CORR_DAYS + 1):
        rec = fc.get((today - timedelta(days=i)).isoformat()) or {}
        f_, a_ = _f(rec.get("pv_fc")), _f(rec.get("pv_act"))
        if f_ is None or a_ is None or f_ < PV_CORR_MIN_FC or a_ < 0:
            continue
        days.append((f_, a_))
    if len(days) < PV_CORR_MIN_DAYS:
        return {"factor": 1.0, "days": len(days), "ratio": None}
    ratio = sum(a for _f_, a in days) / sum(f_ for f_, _a in days)
    weight = min(1.0, len(days) / 10.0)
    factor = 1.0 + (ratio - 1.0) * weight
    factor = min(PV_CORR_HI, max(PV_CORR_LO, factor))
    return {"factor": round(factor, 3), "days": len(days), "ratio": round(ratio, 3)}


def _mape(pairs: list[tuple[float, float]], min_actual: float) -> float | None:
    vals = [abs(f_ - a) / a for f_, a in pairs if a >= min_actual]
    return round(100.0 * sum(vals) / len(vals), 1) if vals else None


def _bias(pairs: list[tuple[float, float]]) -> float | None:
    sf = sum(f_ for f_, _a in pairs)
    sa = sum(a for _f_, a in pairs)
    return round(100.0 * (sf - sa) / sa, 1) if sa > 0 else None


class Insights:
    def __init__(self, hass) -> None:
        self.hass = hass
        self._store = ThrottledStore(hass, STORAGE_VERSION, STORAGE_KEY, delay=300)
        self.hours: dict[str, list] = {}
        self.days: dict[str, dict[str, Any]] = {}
        self.fc: dict[str, dict[str, Any]] = {}
        self.counters: dict[str, dict[str, float]] = {}   # dzień → najwyższy odczyt liczników dnia (PV, zużycie)
        self._last_ts: float | None = None
        self._cur_day: str | None = None
        self._params: dict[str, Any] = {}

    # ------------------------------------------------------------ zapis
    async def async_load(self) -> None:
        try:
            raw = await self._store.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("EMS insights: błąd wczytywania: %s", err)
            return
        if not isinstance(raw, dict):
            return
        for k, v in (raw.get("hours") or {}).items():
            if isinstance(v, list) and len(v) == _BUCKET_LEN:
                b = [(_f(x) or 0.0) for x in v[:10]] + [_f(v[10])]
                self.hours[str(k)] = b
        for k, v in (raw.get("days") or {}).items():
            if isinstance(v, dict):
                self.days[str(k)] = v
        for k, v in (raw.get("fc") or {}).items():
            if isinstance(v, dict):
                self.fc[str(k)] = v
        for k, v in (raw.get("counters") or {}).items():
            if isinstance(v, dict):
                self.counters[str(k)] = {a: float(b) for a, b in v.items() if _f(b) is not None}
        self._cur_day = raw.get("cur_day") if isinstance(raw.get("cur_day"), str) else None

    def _payload(self) -> dict[str, Any]:
        return {"hours": {k: [round(x, 4) if isinstance(x, float) else x for x in v] for k, v in self.hours.items()},
                "days": self.days, "fc": self.fc, "counters": self.counters, "cur_day": self._cur_day}

    def save(self) -> None:
        self._store.request_save(self._payload)

    # ------------------------------------------------------------ pomiar (co ~10 s)
    def set_params(self, **kw: Any) -> None:
        """Parametry baterii do symulacji (pojemność, sprawność, próg, moce) — aktualizowane przez runtime."""
        self._params.update(kw)

    def update(self, now: datetime, data: dict[str, Any], buy: float | None, sell: float | None,
               charge_sign: int, soc: float | None) -> None:
        ts = now.timestamp()
        prev, self._last_ts = self._last_ts, ts
        day = dt_util.as_local(now).date().isoformat()
        if self._cur_day is None:
            self._cur_day = day
        elif day != self._cur_day:
            self._close_day(self._cur_day)
            self._cur_day = day
            self._prune(dt_util.as_local(now).date())
        # liczniki dnia (najwyższy odczyt) — do wykonania PV i zużycia. Przez pierwsze 15 min doby falownik bywa
        # jeszcze z wczorajszym stanem licznika (zeruje go według własnego zegara) — wtedy go nie czytamy.
        loc = dt_util.as_local(now)
        if not (loc.hour == 0 and loc.minute < 15):
            cnt = self.counters.setdefault(day, {})
            for key, name in (("energy_pv_today", "pv"), ("energy_load_today", "load")):
                v = _f(data.get(key))
                if v is not None and v >= 0 and v > cnt.get(name, -1.0):
                    cnt[name] = v
        b = self.hours.setdefault(_hour_key(now), _blank_bucket())
        if soc is not None:
            b[SOC] = round(float(soc), 1)
        if prev is None:
            return
        dt_s = ts - prev
        if dt_s <= 0 or dt_s > MAX_GAP_S:
            return
        f = dt_s / 3_600_000.0
        load, pv = _f(data.get("load_power")), _f(data.get("pv_power"))
        grid, bat = _f(data.get("grid_power")), _f(data.get("battery_power"))
        if load is not None and 0 <= load < MAX_POWER_W:
            b[LOAD] += load * f
        if pv is not None and 0 <= pv < MAX_POWER_W:
            b[PV] += pv * f
        if grid is not None and abs(grid) < MAX_POWER_W:
            if grid > 0:
                b[IMP] += grid * f
            else:
                b[EXP] += -grid * f
        if bat is not None and abs(bat) < MAX_POWER_W:
            p = bat * (1 if charge_sign >= 0 else -1)
            if p > 0:
                b[BCH] += p * f
            else:
                b[BDIS] += -p * f
        if buy is not None and math.isfinite(buy):
            b[BUY_S] += buy * dt_s
            b[BUY_T] += dt_s
        if sell is not None and math.isfinite(sell):
            b[SELL_S] += sell * dt_s
            b[SELL_T] += dt_s
        self.save()

    def _buckets(self, d: str) -> list[list | None]:
        return [self.hours.get(f"{d}T{h:02d}") for h in range(24)]

    def _soc0(self, d: str) -> float | None:
        prev = (date.fromisoformat(d) - timedelta(days=1)).isoformat()
        b = self.hours.get(f"{prev}T23")
        if b is not None and b[SOC] is not None:
            return b[SOC]
        for h in range(24):
            b = self.hours.get(f"{d}T{h:02d}")
            if b is not None and b[SOC] is not None:
                return b[SOC]
        return None

    def compute_day(self, d: str) -> dict[str, Any] | None:
        p = self._params
        return day_costs(self._buckets(d), cap_kwh=float(p.get("cap", 10.0)), eff=float(p.get("eff", 0.9)),
                         floor_pct=float(p.get("floor", 10.0)), max_chg_kw=float(p.get("max_chg_kw", 5.0)),
                         max_dis_kw=float(p.get("max_dis_kw", 5.0)), soc0=self._soc0(d))

    def _close_day(self, d: str) -> None:
        try:
            res = self.compute_day(d)
            if res is not None:
                self.days[d] = res
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("EMS insights: dzień %s: %s", d, err)
        rec = self.fc.get(d)
        if rec is not None:
            cnt = self.counters.get(d) or {}
            buckets = self._buckets(d)
            pv_sum = sum(b[PV] for b in buckets if b is not None)
            rec["pv_act"] = round(cnt["pv"], 2) if "pv" in cnt else (round(pv_sum, 2) if pv_sum > 0 else None)
            rec["soc_act"] = [None if b is None else b[SOC] for b in buckets]
        self.save()

    def _prune(self, today: date) -> None:
        cut_h = (today - timedelta(days=KEEP_HOURS_DAYS)).isoformat()
        for k in [k for k in self.hours if k[:10] < cut_h]:
            self.hours.pop(k, None)
        cut_d = (today - timedelta(days=KEEP_DAYS)).isoformat()
        for k in [k for k in self.days if k < cut_d]:
            self.days.pop(k, None)
        cut_f = (today - timedelta(days=KEEP_FC_DAYS)).isoformat()
        for k in [k for k in self.fc if k < cut_f]:
            self.fc.pop(k, None)
        for k in [k for k in self.counters if k < cut_f]:
            self.counters.pop(k, None)

    # ------------------------------------------------------------ prognoza poranna
    def snapshot(self, now: datetime, pv_kwh: float | None, pv_hourly: list | None, plan: dict | None) -> bool:
        """Raz dziennie (od 6:00): prognoza PV na dziś (surowa) i plan SOC na pozostałe godziny dnia."""
        loc = dt_util.as_local(now)
        d = loc.date().isoformat()
        if loc.hour < SNAPSHOT_HOUR or "pv_fc" in (self.fc.get(d) or {}):
            return False
        rec = self.fc.setdefault(d, {})
        rec["at"] = loc.hour
        rec["pv_fc"] = None if pv_kwh is None else round(float(pv_kwh), 2)
        rec["pv_fc_h"] = [None if _f(v) is None else round(float(v), 3) for v in pv_hourly] if isinstance(pv_hourly, list) else None
        soc_plan: list[float | None] = [None] * 24
        cur = (plan or {}).get("curve") or {}
        try:
            t0 = dt_util.as_local(datetime.fromisoformat(str(cur.get("start"))))
            for i, v in enumerate(cur.get("soc") or []):
                t = t0 + timedelta(hours=i)
                # trace[i] = SOC na KONIEC godziny zaczynającej się o t → porównujemy z odczytem SOC z końca tej godziny
                if t.date() == loc.date() and _f(v) is not None:
                    soc_plan[t.hour] = round(float(v), 1)
        except (TypeError, ValueError):
            pass
        rec["soc_plan"] = soc_plan if any(v is not None for v in soc_plan) else None
        self.save()
        return True

    # ------------------------------------------------------------ korekta PV
    def pv_correction(self, today: date | None = None) -> dict[str, Any]:
        return pv_correction(self.fc, today or dt_util.now().date())

    # ------------------------------------------------------------ dane dla karty / sensorów
    def savings(self, today: date | None = None) -> dict[str, Any]:
        today = today or dt_util.now().date()
        tk = today.isoformat()
        rows = dict(self.days)
        cur = self.compute_day(tk)
        if cur is not None:
            rows[tk] = dict(cur, partial=True)

        def agg(keys: list[str]) -> dict[str, Any]:
            sel = [rows[k] for k in keys if k in rows and (rows[k].get("complete") or rows[k].get("partial"))]
            a = sum(r["actual"] for r in sel)
            n = sum(r["nobat"] for r in sel)
            s = sum(r["simple"] for r in sel)
            return {"days": len(sel), "actual": round(a, 2), "nobat": round(n, 2), "simple": round(s, 2),
                    "vs_nobat": round(n - a, 2), "vs_simple": round(s - a, 2)}

        all_keys = sorted(rows)
        month = [k for k in all_keys if k[:7] == tk[:7]]
        year = [k for k in all_keys if k[:4] == tk[:4]]
        last30 = [(today - timedelta(days=i)).isoformat() for i in range(30)]
        daily = []
        for k in sorted(k for k in rows if k >= (today - timedelta(days=60)).isoformat()):
            r = rows[k]
            daily.append({"date": k, "actual": r["actual"], "nobat": r["nobat"], "simple": r["simple"],
                          "complete": bool(r.get("complete")), "partial": bool(r.get("partial")),
                          "load_kwh": r.get("load_kwh"), "pv_kwh": r.get("pv_kwh")})
        months: dict[str, list[str]] = {}
        for k in all_keys:
            months.setdefault(k[:7], []).append(k)
        return {
            "today": agg([tk]), "month": agg(month), "year": agg(year), "last30": agg(last30), "total": agg(all_keys),
            "daily": daily,
            "months": [dict(agg(v), month=m) for m, v in sorted(months.items())][-13:],
            "since": all_keys[0] if all_keys else None,
            "params": {k: self._params.get(k) for k in ("cap", "eff", "floor", "max_chg_kw", "max_dis_kw")},
        }

    def accuracy(self, lf, today: date | None = None, n: int = 30) -> dict[str, Any]:
        today = today or dt_util.now().date()
        rows = []
        pv_pairs, load_pairs, soc_err = [], [], []
        lf_days = dict(getattr(lf, "days", {}) or {}) if lf is not None else {}
        lf_issued = dict(getattr(lf, "forecast_history", {}) or {}) if lf is not None else {}
        for i in range(n, 0, -1):
            d = (today - timedelta(days=i)).isoformat()
            rec = self.fc.get(d) or {}
            pv_f, pv_a = _f(rec.get("pv_fc")), _f(rec.get("pv_act"))
            ld_f, ld_a = _f(lf_issued.get(d)), _f(lf_days.get(d))
            err = None
            sp, sa = rec.get("soc_plan"), rec.get("soc_act")
            if isinstance(sp, list) and isinstance(sa, list):
                diffs = [abs(float(p) - float(a)) for p, a in zip(sp, sa) if _f(p) is not None and _f(a) is not None]
                if len(diffs) >= 4:
                    err = round(sum(diffs) / len(diffs), 1)
                    soc_err.append(err)
            if pv_f is not None and pv_a is not None:
                pv_pairs.append((pv_f, pv_a))
            if ld_f is not None and ld_a is not None:
                load_pairs.append((ld_f, ld_a))
            if any(x is not None for x in (pv_f, pv_a, ld_f, ld_a, err)):
                rows.append({"date": d, "pv_fc": pv_f, "pv_act": pv_a, "load_fc": ld_f, "load_act": ld_a, "soc_mae": err})
        corr = self.pv_correction(today)
        return {
            "days": rows,
            "pv": {"mape": _mape(pv_pairs, 0.5), "bias": _bias(pv_pairs), "n": len(pv_pairs)},
            "load": {"mape": _mape(load_pairs, 0.5), "bias": _bias(load_pairs), "n": len(load_pairs)},
            "soc": {"mae": round(sum(soc_err) / len(soc_err), 1) if soc_err else None, "n": len(soc_err)},
            "pv_correction": corr,
            "today": self.fc.get(today.isoformat()),
        }
