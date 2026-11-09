"""Dodatkowe urządzenia (odbiorniki z pomiarem mocy W i/lub energii kWh).

Integracja liczy dla każdego urządzenia: zużycie dzienne i godzinowe, koszt (kWh × bieżąca cena zakupu), skąd
pochodziła energia (PV / bateria / sieć — szacunek z bilansu domu w danej chwili), pobór w czuwaniu (najniższa moc
w nocy), cykle pracy (pralka, zmywarka…), nietypowo długą pracę, podpowiedzi „uruchom teraz”, plan dla urządzeń
elastycznych, nierozpoznane odbiorniki w „reszcie domu” oraz prognozę zużycia z podziałem na duże urządzenia.
Konfigurację i dane trzyma we własnym magazynie HA (działa bez otwartej karty).
"""
from __future__ import annotations

import logging
import math
import re
import statistics
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from homeassistant.util import dt as dt_util

from .helpers import ThrottledStore

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "bms_komp_dec_devices"
STORAGE_VERSION = 1
MAX_DEVICES = 40
KEEP_HOURLY_DAYS = 62
KEEP_DAILY_DAYS = 400
KEEP_CYCLES = 300
MAX_STEP_S = 120.0                 # dłuższa przerwa w odczytach (restart) nie jest całkowana
MAX_KWH_STEP = 20.0                # skok licznika większy niż 20 kWh w jednym kroku = błąd odczytu
BIG_SHARE = 0.15                   # „duże” urządzenie: co najmniej 15% zużycia domu (30 dni)
SPLIT_MIN_DAYS = 14
POWER_WINDOW_S = 300.0             # okno do szacowania mocy z licznika kWh                # tyle dni danych urządzeń, zanim prognoza z podziałem może zastąpić zwykłą
STANDBY_HOURS = (1, 5)             # czuwanie = najniższa moc między 1:00 a 5:00
HDD_BASE = 18.0

# klucz: (grupa, nazwa, ikona, czynnik prognozy, elastyczne, cykle, czuwanie, próg pracy W, koniec cyklu [min], maks. praca [h])
CATEGORIES: dict[str, tuple] = {
    # ogrzewanie i chłodzenie
    "heat_pump": ("Ogrzewanie i chłodzenie", "Pompa ciepła (CO)", "🌡️", "temp", False, False, True, 150, 10, 0),
    "heat_pump_dhw": ("Ogrzewanie i chłodzenie", "Pompa ciepła — ciepła woda", "🚿", "flat", True, False, True, 150, 10, 0),
    "boiler": ("Ogrzewanie i chłodzenie", "Bojler / grzałka", "♨️", "flat", True, False, False, 300, 5, 8),
    "floor_heating": ("Ogrzewanie i chłodzenie", "Ogrzewanie podłogowe elektryczne", "🔥", "temp", False, False, False, 200, 10, 0),
    "heater": ("Ogrzewanie i chłodzenie", "Grzejnik / promiennik", "🔥", "temp", False, False, False, 200, 10, 0),
    "circ_pump": ("Ogrzewanie i chłodzenie", "Pompy obiegowe / sterownik kotła", "🔄", "temp", False, False, True, 10, 10, 0),
    "ac": ("Ogrzewanie i chłodzenie", "Klimatyzacja", "❄️", "temp", False, False, True, 150, 10, 0),
    "ventilation": ("Ogrzewanie i chłodzenie", "Rekuperacja / wentylacja", "🌬️", "flat", False, False, False, 10, 10, 0),
    "dehumidifier": ("Ogrzewanie i chłodzenie", "Osuszacz", "💧", "flat", True, False, True, 50, 10, 0),
    # transport
    "ev": ("Transport", "Ładowarka samochodu elektrycznego", "🚗", "weekday", True, True, True, 1000, 10, 14),
    "ebike": ("Transport", "Rower / hulajnoga", "🚲", "weekday", True, True, True, 30, 10, 10),
    # kuchnia
    "fridge": ("Kuchnia", "Lodówka", "🧊", "flat", False, False, False, 30, 5, 3),
    "freezer": ("Kuchnia", "Zamrażarka", "🧊", "flat", False, False, False, 30, 5, 3),
    "induction": ("Kuchnia", "Płyta indukcyjna", "🍳", "weekday", False, True, True, 100, 10, 4),
    "oven": ("Kuchnia", "Piekarnik", "🥧", "weekday", False, True, True, 100, 10, 4),
    "dishwasher": ("Kuchnia", "Zmywarka", "🍽️", "weekday", True, True, True, 10, 15, 5),
    "kettle": ("Kuchnia", "Czajnik", "☕", "flat", False, True, True, 500, 2, 1),
    "coffee": ("Kuchnia", "Ekspres do kawy", "☕", "flat", False, True, True, 50, 5, 2),
    "microwave": ("Kuchnia", "Mikrofalówka", "📡", "flat", False, True, True, 100, 2, 1),
    # pranie
    "washer": ("Pranie", "Pralka", "🧺", "weekday", True, True, True, 10, 10, 5),
    "dryer": ("Pranie", "Suszarka", "🌀", "weekday", True, True, True, 50, 10, 5),
    # woda i basen
    "water_pump": ("Woda i basen", "Hydrofor / pompa wody", "🚰", "flat", False, False, True, 100, 3, 1),
    "septic": ("Woda i basen", "Oczyszczalnia / przepompownia", "🪣", "flat", False, False, False, 20, 5, 0),
    "pool_pump": ("Woda i basen", "Pompa basenowa", "🏊", "flat", True, False, True, 100, 10, 0),
    "pool_heat": ("Woda i basen", "Podgrzew basenu / spa", "🛁", "temp", True, False, True, 300, 10, 0),
    "irrigation": ("Woda i basen", "Nawadnianie", "🌱", "flat", True, False, True, 30, 5, 4),
    # elektronika
    "server": ("Elektronika", "Serwer / komputer", "🖥️", "flat", False, False, False, 10, 10, 0),
    "network": ("Elektronika", "Sieć / router", "📶", "flat", False, False, False, 2, 10, 0),
    "tv": ("Elektronika", "TV / RTV", "📺", "weekday", False, False, True, 30, 5, 10),
    # oświetlenie
    "light_in": ("Oświetlenie", "Oświetlenie wewnątrz", "💡", "flat", False, False, True, 5, 5, 0),
    "light_out": ("Oświetlenie", "Oświetlenie na zewnątrz", "🔦", "flat", False, False, True, 5, 5, 0),
    # warsztat i ogród
    "tools": ("Warsztat i ogród", "Narzędzia", "🛠️", "weekday", True, True, True, 50, 5, 6),
    "compressor": ("Warsztat i ogród", "Sprężarka", "🛠️", "weekday", True, True, True, 200, 5, 2),
    "mower": ("Warsztat i ogród", "Kosiarka (ładowanie)", "🌿", "weekday", True, True, True, 20, 10, 10),
    # inne
    "other": ("Inne", "Inne", "🔌", "flat", False, False, True, 20, 10, 0),
}
GROUPS = ("Ogrzewanie i chłodzenie", "Transport", "Kuchnia", "Pranie", "Woda i basen", "Elektronika", "Oświetlenie",
          "Warsztat i ogród", "Inne")
DRIVERS = ("temp", "weekday", "flat")
_ID_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_EID_RE = re.compile(r"^sensor\.[a-z0-9_]+$")
_SWITCH_RE = re.compile(r"^(switch|input_boolean)\.[a-z0-9_]+$")
CTL_MODES = ("off", "pv", "cheap")
_POWER_UNITS = {"w": 1.0, "kw": 1000.0, "mw": 1_000_000.0}
_ENERGY_UNITS = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0}


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _clamp(v: Any, lo: float, hi: float, default: float) -> float:
    x = _f(v)
    return default if x is None else min(hi, max(lo, x))


def category_payload() -> list[dict[str, Any]]:
    out = []
    for k, (g, n, ic, drv, flex, cyc, stby, thr, endm, maxh) in CATEGORIES.items():
        out.append({"key": k, "group": g, "name": n, "icon": ic,
                    "default": {"driver": drv, "flexible": flex, "cycles": cyc, "standby": stby,
                                "cycle_w": thr, "cycle_end_min": endm, "max_run_h": maxh}})
    return out


def sanitize_device(raw: Any) -> dict[str, Any] | None:
    """Jedno urządzenie z karty → bezpieczny słownik; None, gdy nie ma ani encji mocy, ani energii."""
    if not isinstance(raw, dict):
        return None
    cat = str(raw.get("category") or "other")
    if cat not in CATEGORIES:
        cat = "other"
    g, name_d, ic, drv, flex, cyc, stby, thr, endm, maxh = CATEGORIES[cat]
    pe = str(raw.get("power_eid") or "").strip()
    ee = str(raw.get("energy_eid") or "").strip()
    pe = pe if _EID_RE.match(pe) else ""
    ee = ee if _EID_RE.match(ee) else ""
    if not pe and not ee:
        return None
    did = str(raw.get("id") or "").strip().lower()
    if not _ID_RE.match(did):
        did = "d" + uuid.uuid4().hex[:10]
    name = re.sub(r"\s+", " ", str(raw.get("name") or name_d)).strip()[:40] or name_d
    icon = str(raw.get("icon") or ic).strip()[:4] or ic
    driver = str(raw.get("driver") or drv)
    if driver not in DRIVERS:
        driver = drv

    def b(key: str, default: bool) -> bool:
        v = raw.get(key)
        return v if isinstance(v, bool) else default

    sw = str(raw.get("switch_eid") or "").strip()
    ctl = str(raw.get("ctl_mode") or "off")

    return {
        "id": did, "name": name, "icon": icon, "category": cat,
        "power_eid": pe, "energy_eid": ee,
        "room": re.sub(r"\s+", " ", str(raw.get("room") or "")).strip()[:30],
        "driver": driver, "flexible": b("flexible", flex), "cycles": b("cycles", cyc), "standby": b("standby", stby),
        "cycle_w": _clamp(raw.get("cycle_w"), 1.0, 20000.0, float(thr)),
        "cycle_end_min": _clamp(raw.get("cycle_end_min"), 1.0, 120.0, float(endm)),
        "max_run_h": _clamp(raw.get("max_run_h"), 0.0, 48.0, float(maxh)),
        "notify_cycle": b("notify_cycle", cyc), "notify_anomaly": b("notify_anomaly", True), "notify_hint": b("notify_hint", flex),
        # sterowanie (opcjonalne): przełącznik urządzenia i tryb — działa tylko przy włączonym switch.bms_device_control
        "switch_eid": sw if _SWITCH_RE.match(sw) else "",
        "ctl_mode": ctl if (ctl in CTL_MODES and _SWITCH_RE.match(sw)) else "off",
        "ctl_power_w": _clamp(raw.get("ctl_power_w"), 10.0, 30000.0, 1000.0),
        "ctl_soc": _clamp(raw.get("ctl_soc"), 0.0, 100.0, 90.0),
        "ctl_hours": _clamp(raw.get("ctl_hours"), 0.5, 12.0, 2.0),
        "ctl_max_h": _clamp(raw.get("ctl_max_h"), 0.0, 24.0, 0.0),
        "ctl_no_shed": b("ctl_no_shed", False) if _SWITCH_RE.match(sw) else False,   # nie wyłączaj przy niskim SOC (oszczędzanie energii)
    }


def sanitize_list(items: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in (items if isinstance(items, list) else [])[:MAX_DEVICES]:
        d = sanitize_device(raw)
        if d is None:
            continue
        while d["id"] in seen:
            d["id"] = "d" + uuid.uuid4().hex[:10]
        seen.add(d["id"])
        out.append(d)
    return out


def _unit_scaled(hass, eid: str, table: dict[str, float], default_unit: str) -> float | None:
    st = hass.states.get(eid) if eid else None
    if st is None or str(st.state).lower() in ("unknown", "unavailable", "none", ""):
        return None
    v = _f(st.state)
    if v is None:
        return None
    unit = str((st.attributes or {}).get("unit_of_measurement") or default_unit).strip().lower()
    return v * table.get(unit, 1.0)


def _blank() -> dict[str, Any]:
    return {"daily": {}, "hourly": {}, "cost": {}, "src": {}, "standby": {}, "cycles": [], "minprice": {},
            "last_e": None, "last_ts": None, "run": None}


class DeviceManager:
    """Konfiguracja urządzeń i ich dane (własny magazyn, zapis z opóźnieniem)."""

    def __init__(self, hass) -> None:
        self.hass = hass
        self._store = ThrottledStore(hass, STORAGE_VERSION, STORAGE_KEY, delay=60)
        self.devices: list[dict[str, Any]] = []
        self.data: dict[str, dict[str, Any]] = {}
        self.price_min: dict[str, float] = {}         # najniższa cena zakupu dnia (do oszczędności przesunięcia)
        self.state: dict[str, Any] = {}               # podpowiedzi / alarmy raz na dobę

    async def async_load(self) -> None:
        raw = await self._store.async_load()
        if not isinstance(raw, dict):
            return
        self.devices = sanitize_list(raw.get("devices"))
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        for d in self.devices:
            src = data.get(d["id"]) if isinstance(data.get(d["id"]), dict) else {}
            rec = _blank()
            for k in ("daily", "cost", "standby", "minprice"):
                if isinstance(src.get(k), dict):
                    rec[k] = {str(a): float(b) for a, b in src[k].items() if _f(b) is not None}
            for k in ("hourly", "src"):
                if isinstance(src.get(k), dict):
                    rec[k] = {str(a): [float(x or 0.0) for x in b][:24 if k == "hourly" else 3]
                              for a, b in src[k].items() if isinstance(b, list)}
            if isinstance(src.get("cycles"), list):
                rec["cycles"] = [c for c in src["cycles"] if isinstance(c, dict)][-KEEP_CYCLES:]
            self.data[d["id"]] = rec
        pm = raw.get("price_min")
        if isinstance(pm, dict):
            self.price_min = {str(a): float(b) for a, b in pm.items() if _f(b) is not None}

    def _payload(self) -> dict[str, Any]:
        data = {}
        for did, rec in self.data.items():
            data[did] = {k: rec[k] for k in ("daily", "hourly", "cost", "src", "standby", "cycles", "minprice")}
        return {"devices": self.devices, "data": data, "price_min": self.price_min}

    def save(self) -> None:
        self._store.request_save(self._payload)

    # ---------------------------------------------------------------- konfiguracja
    def set_devices(self, items: Any) -> list[dict[str, Any]]:
        new = sanitize_list(items)
        keep = {d["id"] for d in new}
        for did in [k for k in self.data if k not in keep]:
            self.data.pop(did, None)
        for d in new:
            old = next((o for o in self.devices if o["id"] == d["id"]), None)
            rec = self.data.setdefault(d["id"], _blank())
            if old and (old["energy_eid"] != d["energy_eid"] or old["power_eid"] != d["power_eid"]):
                rec["last_e"], rec["last_ts"], rec["run"] = None, None, None    # inna encja — nie łączymy liczników
        self.devices = new
        self.save()
        return new

    # ---------------------------------------------------------------- pomiar (co ~10 s)
    def update(self, now: datetime, house: dict[str, Any], buy_price: float | None) -> list[dict[str, Any]]:
        """Całkuje energię urządzeń; zwraca zdarzenia (koniec cyklu, nietypowa praca) do powiadomień."""
        events: list[dict[str, Any]] = []
        if not self.devices:
            return events
        loc = dt_util.as_local(now)
        day = loc.date().isoformat()
        ts = now.timestamp()
        if buy_price is not None and 0 < buy_price < 20:
            self.price_min[day] = min(self.price_min.get(day, buy_price), buy_price)
        shares = self._shares(house)
        changed = False
        for d in self.devices:
            rec = self.data.setdefault(d["id"], _blank())
            p = _unit_scaled(self.hass, d["power_eid"], _POWER_UNITS, "W") if d["power_eid"] else None
            e = _unit_scaled(self.hass, d["energy_eid"], _ENERGY_UNITS, "kWh") if d["energy_eid"] else None
            last_ts = rec.get("last_ts")
            dt_s = (ts - float(last_ts)) if isinstance(last_ts, (int, float)) else None
            rec["last_ts"] = ts
            delta = 0.0
            if e is not None:
                le = rec.get("last_e")
                rec["last_e"] = e
                if isinstance(le, (int, float)):
                    dd = e - float(le)
                    if dd < -0.001:                 # licznik dzienny wyzerowany (albo wymiana licznika)
                        dd = e if e < MAX_KWH_STEP else 0.0
                    delta = dd if 0.0 <= dd <= MAX_KWH_STEP else 0.0
            elif p is not None and dt_s is not None and 0 < dt_s <= MAX_STEP_S:
                delta = max(0.0, p) * dt_s / 3_600_000.0
            if p is None and e is not None:
                # moc z przyrostów licznika: średnia z ostatnich 5 min (licznik bywa odświeżany rzadziej niż co 10 s,
                # a moc z pojedynczego kroku dawałaby 0 W między odczytami i fałszywe końce cykli)
                win = [x for x in (rec.get("pw") or []) if ts - x[0] <= POWER_WINDOW_S]
                win.append((ts, delta))
                rec["pw"] = win
                span = ts - win[0][0]
                p = sum(x[1] for x in win) * 3_600_000.0 / span if span >= 60 else None
            if delta > 0:
                daily = rec["daily"]
                daily[day] = daily.get(day, 0.0) + delta
                hrs = rec["hourly"].setdefault(day, [0.0] * 24)
                hrs[loc.hour] += delta
                if buy_price is not None and 0 < buy_price < 20:
                    rec["cost"][day] = rec["cost"].get(day, 0.0) + delta * buy_price
                s = rec["src"].setdefault(day, [0.0, 0.0, 0.0])
                for i in range(3):
                    s[i] += delta * shares[i]
                changed = True
            if p is not None and d["standby"] and STANDBY_HOURS[0] <= loc.hour < STANDBY_HOURS[1]:
                cur = rec["standby"].get(day)
                if cur is None or p < cur:
                    rec["standby"][day] = round(max(0.0, p), 1)
                    changed = True
            events.extend(self._run_state(d, rec, p, ts, buy_price))
        if changed:
            self._prune(loc.date())
            self.save()
        return events

    @staticmethod
    def _shares(house: dict[str, Any]) -> tuple[float, float, float]:
        """(PV, bateria, sieć) — udział źródeł w zużyciu domu w tej chwili (bilans: PV najpierw, potem sieć, reszta bateria)."""
        load = _f(house.get("load_power")) or 0.0
        if load <= 1:
            return (0.0, 0.0, 1.0)
        pv = max(0.0, _f(house.get("pv_power")) or 0.0)
        grid = max(0.0, _f(house.get("grid_power")) or 0.0)
        pv_part = min(pv, load)
        grid_part = min(grid, load - pv_part)
        bat_part = max(0.0, load - pv_part - grid_part)
        return (pv_part / load, bat_part / load, grid_part / load)

    def _run_state(self, d: dict, rec: dict, p: float | None, ts: float, price: float | None) -> list[dict[str, Any]]:
        """Stan pracy: cykl (start, koniec po `cycle_end_min` poniżej progu) i zbyt długa ciągła praca."""
        if p is None:
            return []
        ev: list[dict[str, Any]] = []
        run = rec.get("run")
        on = p > d["cycle_w"]
        daily_total = sum(rec["daily"].values()) if rec["daily"] else 0.0
        if on:
            if run is None:
                rec["run"] = run = {"since": ts, "below": None, "e0": daily_total, "peak": p, "anom": False}
            run["below"] = None
            run["peak"] = max(float(run.get("peak") or 0.0), p)
            if d["max_run_h"] > 0 and not run.get("anom") and ts - float(run["since"]) > d["max_run_h"] * 3600.0:
                run["anom"] = True
                ev.append({"type": "anomaly", "device": d, "hours": (ts - float(run["since"])) / 3600.0, "power": p})
        elif run is not None:
            if run.get("below") is None:
                run["below"] = ts
            elif ts - float(run["below"]) >= d["cycle_end_min"] * 60.0:
                dur = float(run["below"]) - float(run["since"])
                kwh = max(0.0, daily_total - float(run.get("e0") or 0.0))
                rec["run"] = None
                if d["cycles"] and dur >= 180 and kwh >= 0.01:
                    cyc = {"start": datetime.fromtimestamp(float(run["since"]), timezone.utc).isoformat(),
                           "min": round(dur / 60.0, 1), "kwh": round(kwh, 3), "peak_w": round(float(run.get("peak") or 0.0)),
                           "cost": round(kwh * price, 3) if price is not None and 0 < price < 20 else None}
                    rec["cycles"].append(cyc)
                    rec["cycles"] = rec["cycles"][-KEEP_CYCLES:]
                    ev.append({"type": "cycle", "device": d, "cycle": cyc})
        return ev

    def _prune(self, today: date) -> None:
        cut_h = (today - timedelta(days=KEEP_HOURLY_DAYS)).isoformat()
        cut_d = (today - timedelta(days=KEEP_DAILY_DAYS)).isoformat()
        for rec in self.data.values():
            for k in [k for k in rec["hourly"] if k < cut_h]:
                rec["hourly"].pop(k, None)
            for key in ("daily", "cost", "src", "standby"):
                for k in [k for k in rec[key] if k < cut_d]:
                    rec[key].pop(k, None)
        for k in [k for k in self.price_min if k < cut_d]:
            self.price_min.pop(k, None)

    # ---------------------------------------------------------------- odczyty dla karty i analiz
    def live(self) -> list[dict[str, Any]]:
        today = dt_util.now().date().isoformat()
        out = []
        for d in self.devices:
            rec = self.data.get(d["id"]) or _blank()
            p = _unit_scaled(self.hass, d["power_eid"], _POWER_UNITS, "W") if d["power_eid"] else None
            out.append({"id": d["id"], "name": d["name"], "icon": d["icon"], "category": d["category"], "room": d["room"],
                        "power": None if p is None else round(p, 1), "today_kwh": round(rec["daily"].get(today, 0.0), 3),
                        "today_cost": round(rec["cost"].get(today, 0.0), 2), "running": rec.get("run") is not None})
        return out

    def _days_back(self, n: int, today: date) -> list[str]:
        return [(today - timedelta(days=i)).isoformat() for i in range(n)]

    def summary(self, house_days: dict[str, float] | None = None) -> list[dict[str, Any]]:
        """Podsumowanie urządzeń: kWh i koszt (dziś / 7 / 30 dni / miesiąc), czuwanie, cykle, źródła, oszczędność."""
        today = dt_util.now().date()
        d30 = self._days_back(30, today)
        house30 = sum((house_days or {}).get(k, 0.0) for k in d30)
        month = today.strftime("%Y-%m")
        out = []
        for d in self.devices:
            rec = self.data.get(d["id"]) or _blank()
            dl, cost = rec["daily"], rec["cost"]

            def tot(src: dict, keys: list[str]) -> float:
                return sum(src.get(k, 0.0) for k in keys)

            k30 = tot(dl, d30)
            c30 = tot(cost, d30)
            mk = sum(v for k, v in dl.items() if k.startswith(month))
            mc = sum(v for k, v in cost.items() if k.startswith(month))
            stb = [v for k, v in rec["standby"].items() if k in d30]
            standby_w = round(statistics.median(stb), 1) if len(stb) >= 3 else None
            cyc30 = [c for c in rec["cycles"] if str(c.get("start", ""))[:10] >= d30[-1]]
            src = [sum(rec["src"].get(k, [0, 0, 0])[i] for k in d30) for i in range(3)]
            ssum = sum(src)
            saving = None
            if d["flexible"]:
                sv = [cost.get(k, 0.0) - dl.get(k, 0.0) * self.price_min[k] for k in d30 if k in self.price_min and dl.get(k)]
                saving = round(max(0.0, sum(sv)), 2) if sv else None
            avg_price = c30 / k30 if k30 > 0.05 else None
            out.append({
                "id": d["id"],
                "today_kwh": round(dl.get(today.isoformat(), 0.0), 3), "today_cost": round(cost.get(today.isoformat(), 0.0), 2),
                "kwh_7d": round(tot(dl, d30[:7]), 2), "kwh_30d": round(k30, 2), "cost_30d": round(c30, 2),
                "kwh_month": round(mk, 2), "cost_month": round(mc, 2),
                "avg_price": None if avg_price is None else round(avg_price, 3),
                "share_house_30d": round(k30 / house30 * 100.0, 1) if house30 > 1 else None,
                "standby_w": standby_w,
                "standby_cost_year": None if standby_w is None or avg_price is None else round(standby_w / 1000.0 * 8760 * avg_price, 0),
                "cycles_30d": len(cyc30),
                "cycle_avg_kwh": round(_mean([c["kwh"] for c in cyc30]), 3) if cyc30 else None,
                "cycle_avg_cost": round(_mean([c["cost"] for c in cyc30 if c.get("cost") is not None]), 2) if any(c.get("cost") is not None for c in cyc30) else None,
                "cycle_avg_min": round(_mean([c["min"] for c in cyc30]), 0) if cyc30 else None,
                "src_pct": [round(x / ssum * 100.0) for x in src] if ssum > 0.05 else None,
                "saving_30d": saving,
                "days_with_data": len([k for k in dl if dl[k] > 0]),
            })
        return out

    def history(self) -> dict[str, Any]:
        """Dane do wykresów: dziennie (do 400 dni) i godzinowo (do 62 dni), koszt i źródła dziennie, ostatnie cykle."""
        return {d["id"]: {"daily": {k: round(v, 3) for k, v in (self.data.get(d["id"]) or _blank())["daily"].items()},
                          "hourly": {k: [round(x, 4) for x in v] for k, v in (self.data.get(d["id"]) or _blank())["hourly"].items()},
                          "cost": {k: round(v, 3) for k, v in (self.data.get(d["id"]) or _blank())["cost"].items()},
                          "src": {k: [round(x, 3) for x in v] for k, v in (self.data.get(d["id"]) or _blank())["src"].items()},
                          "cycles": (self.data.get(d["id"]) or _blank())["cycles"][-50:]}
                for d in self.devices}

    def top_now(self, n: int = 5) -> list[tuple[str, float]]:
        """Urządzenia o największym poborze teraz (do listy przy zaniku sieci)."""
        out = []
        for d in self.devices:
            p = _unit_scaled(self.hass, d["power_eid"], _POWER_UNITS, "W") if d["power_eid"] else None
            if p is not None and p > 20:
                out.append((d["name"], p))
        return sorted(out, key=lambda x: -x[1])[:n]

    # ---------------------------------------------------------------- „uruchom teraz”
    def hints(self, now: datetime, house: dict[str, Any], soc: float | None, cheap_now: bool) -> list[dict[str, Any]]:
        """Podpowiedzi dla elastycznych urządzeń: nadwyżka PV (eksport ≥ 1,5 kW przez 10 min przy SOC ≥ 90%) albo
        najtańsza godzina doby (taryfa dynamiczna). Raz na dobę na urządzenie i powód."""
        ev: list[dict[str, Any]] = []
        grid = _f(house.get("grid_power"))
        st = self.state.setdefault("surplus", {})
        if grid is not None and grid < -1500 and (soc or 0) >= 90:
            st.setdefault("since", now.timestamp())
        else:
            st.pop("since", None)
        surplus = "since" in st and now.timestamp() - float(st["since"]) >= 600
        if not (surplus or cheap_now):
            return ev
        day = dt_util.as_local(now).date().isoformat()
        done = self.state.setdefault("hint_done", {})
        for d in self.devices:
            if not d["flexible"] or not d["notify_hint"]:
                continue
            rec = self.data.get(d["id"]) or _blank()
            if rec.get("run") is not None:
                continue
            why = "surplus" if surplus else "cheap"
            key = f"{d['id']}:{why}"
            if done.get(key) == day:
                continue
            done[key] = day
            ev.append({"type": "hint", "device": d, "why": why, "export_w": -(grid or 0.0)})
        return ev

    # ---------------------------------------------------------------- plan dla elastycznych
    def typical(self, d: dict) -> tuple[float | None, float | None]:
        """(typowe kWh na dzień pracy, typowa moc kW) z 14 dni."""
        rec = self.data.get(d["id"]) or _blank()
        today = dt_util.now().date()
        vals = [rec["daily"].get(k, 0.0) for k in self._days_back(15, today)[1:]]
        vals = [v for v in vals if v > 0.2]
        kwh = statistics.median(vals) if len(vals) >= 3 else None
        peaks = [c.get("peak_w") for c in rec["cycles"][-20:] if _f(c.get("peak_w"))]
        kw = statistics.median(peaks) / 1000.0 if len(peaks) >= 3 else None
        if kw is None and kwh is not None:
            hrs = [h for k, v in rec["hourly"].items() for h in v if h > 0.05]
            kw = max(0.3, statistics.median(hrs)) if len(hrs) >= 5 else None
        return kwh, kw

    def flex_plan(self, curve: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Najlepsze okno w planie 24 h dla elastycznych urządzeń: najtańsza energia z uwzględnieniem nadwyżki PV
        (energia z nadwyżki kosztuje tyle, ile dałaby jej sprzedaż)."""
        if not curve or not curve.get("start") or not isinstance(curve.get("pv"), list):
            return []
        try:
            t0 = datetime.fromisoformat(str(curve["start"]))
        except ValueError:
            return []
        pv, load = curve.get("pv") or [], curve.get("load") or []
        buy, sell = curve.get("buy") or [], curve.get("sell") or []
        n = min(len(pv), len(load), len(buy))
        out = []
        for d in self.devices:
            if not d["flexible"]:
                continue
            kwh, kw = self.typical(d)
            if not kwh or not kw:
                continue
            hours = max(1, min(8, math.ceil(kwh / kw)))
            best = None
            for s in range(0, max(0, n - hours + 1)):
                cost = 0.0
                ok = True
                pv_used = 0.0
                for h in range(s, s + hours):
                    b = _f(buy[h])
                    if b is None:
                        ok = False
                        break
                    sl = _f(sell[h]) if h < len(sell) else None
                    sur = max(0.0, (_f(pv[h]) or 0.0) - (_f(load[h]) or 0.0))
                    e = kwh / hours
                    from_pv = min(e, sur)
                    pv_used += from_pv
                    cost += from_pv * max(0.0, sl if sl is not None else 0.0) + (e - from_pv) * b
                if ok and (best is None or cost < best[1] - 1e-9):
                    best = (s, cost, pv_used)
            if best is None:
                continue
            s, cost, pv_used = best
            start = t0 + timedelta(hours=s)
            out.append({"id": d["id"], "name": d["name"], "icon": d["icon"], "kwh": round(kwh, 2), "hours": hours,
                        "start": start.isoformat(), "end": (start + timedelta(hours=hours)).isoformat(),
                        "cost": round(cost, 2), "pv_kwh": round(pv_used, 2),
                        "why": "nadwyżka PV" if pv_used >= kwh * 0.5 else "najtańsze godziny"})
        return out

    # ---------------------------------------------------------------- nierozpoznany odbiornik
    def unknown_load(self, lf_profiles: dict[str, list[float]], lf_days: dict[str, float]) -> dict[str, Any] | None:
        """Powtarzalny skok w „reszcie domu” (dom − urządzenia): ta sama godzina w ≥ 5 z 7 ostatnich dni,
        o ≥ 1 kWh ponad medianę godzin tego dnia."""
        today = dt_util.now().date()
        hits: dict[int, list[float]] = {}
        used = 0
        for k in self._days_back(8, today)[1:]:
            prof, tot = lf_profiles.get(k), lf_days.get(k)
            if not isinstance(prof, list) or len(prof) != 24 or not tot:
                continue
            used += 1
            res = []
            for h in range(24):
                dev = sum(((self.data.get(d["id"]) or _blank())["hourly"].get(k) or [0.0] * 24)[h] for d in self.devices)
                res.append(max(0.0, prof[h] * tot - dev))
            med = statistics.median(res)
            for h in range(24):
                if res[h] >= med + 1.0:
                    hits.setdefault(h, []).append(res[h] - med)
        if used < 5:
            return None
        best = max(hits.items(), key=lambda x: (len(x[1]), sum(x[1])), default=None)
        if not best or len(best[1]) < 5:
            return None
        return {"hour": best[0], "kwh": round(statistics.median(best[1]), 2), "days": len(best[1]), "of": used}

    # ---------------------------------------------------------------- prognoza z podziałem
    def big_devices(self, house_days: dict[str, float]) -> list[dict[str, Any]]:
        today = dt_util.now().date()
        d30 = self._days_back(31, today)[1:]
        house = sum(house_days.get(k, 0.0) for k in d30)
        if house <= 1:
            return []
        out = []
        for d in self.devices:
            rec = self.data.get(d["id"]) or _blank()
            if sum(rec["daily"].get(k, 0.0) for k in d30) / house >= BIG_SHARE:
                out.append(d)
        return out

    def device_forecast(self, d: dict, target: date, temps: dict[str, float]) -> float | None:
        """Prognoza dnia dla urządzenia: temperatura (regresja kWh ~ stopniodni), dzień tygodnia albo średnia."""
        rec = self.data.get(d["id"]) or _blank()
        hist = []
        for i in range(1, 43):
            k = (target - timedelta(days=i)).isoformat()
            if k in rec["daily"]:
                hist.append((target - timedelta(days=i), rec["daily"][k]))
        if len(hist) < 7:
            return None
        if d["driver"] == "temp":
            pts = [(max(0.0, HDD_BASE - temps[x.isoformat()]), v) for x, v in hist if x.isoformat() in temps]
            t = temps.get(target.isoformat())
            if len(pts) >= 7 and t is not None:
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                mx, my = _mean(xs), _mean(ys)
                vx = sum((x - mx) ** 2 for x in xs)
                slope = sum((x - mx) * (y - my) for x, y in pts) / vx if vx > 1e-6 else 0.0
                slope = max(0.0, slope)
                return max(0.0, my + slope * (max(0.0, HDD_BASE - t) - mx))
        if d["driver"] == "weekday":
            same = [v for x, v in hist if x.weekday() == target.weekday()][:4]
            if len(same) >= 2:
                return _mean(same)
        recent = [v for _x, v in hist[:14]]
        return statistics.median(recent) if recent else None


def _mean(v: list[float]) -> float:
    return sum(v) / len(v) if v else 0.0


def forecast_split(dm: DeviceManager, lf, target: date, today: date) -> dict[str, Any] | None:
    """Prognoza dnia `target` = „reszta domu” (ten sam model co całość, liczony na dom − duże urządzenia)
    + prognoza każdego dużego urządzenia z jego własnego czynnika (temperatura / dzień tygodnia / średnia).

    Zastępuje zwykłą prognozę tylko wtedy, gdy na ostatnich 7 dniach (liczonych wstecz, bez wiedzy o przyszłości)
    myliła się mniej niż zwykły model. Wynik jest buforowany na 10 minut."""
    now_ts = dt_util.now().timestamp()
    sig = (target.isoformat(), today.isoformat(), len(lf.days), len(dm.devices))
    cached = dm.state.get("split_cache")
    if cached and cached[0] == sig and now_ts - cached[1] < 600:
        return cached[2]
    res = _forecast_split(dm, lf, target, today)
    dm.state["split_cache"] = (sig, now_ts, res)
    return res


def _forecast_split(dm: DeviceManager, lf, target: date, today: date) -> dict[str, Any] | None:
    if not dm.devices:
        return None
    big = dm.big_devices(lf.days)
    if not big:
        return {"use": False, "reason": "brak dużych urządzeń (≥ 15% zużycia domu)"}
    recs = [dm.data.get(d["id"]) or _blank() for d in big]
    days_ok = [k for k in lf.days if all(k in r["daily"] for r in recs)]
    if len(days_ok) < SPLIT_MIN_DAYS:
        return {"use": False, "reason": f"za mało danych urządzeń ({len(days_ok)} z {SPLIT_MIN_DAYS} dni)",
                "devices": [d["name"] for d in big]}
    residual = {k: max(0.0, lf.days[k] - sum(r["daily"][k] for r in recs)) for k in days_ok}
    temps = getattr(lf, "temperatures", {}) or {}

    def split_for(tgt: date, cut: date) -> tuple[float | None, list[dict[str, Any]]]:
        saved = lf.days
        try:
            lf.days = {k: v for k, v in residual.items()}
            base = lf._model_core(tgt, cut)  # noqa: SLF001
        finally:
            lf.days = saved
        if base is None:
            return None, []
        parts = []
        for d in big:
            v = dm.device_forecast(d, tgt, temps)
            if v is None:
                return None, []
            parts.append({"id": d["id"], "name": d["name"], "kwh": round(v, 2), "driver": d["driver"]})
        return base + sum(p["kwh"] for p in parts), parts

    errs_s, errs_t = [], []
    for i in range(1, 8):
        k = today - timedelta(days=i)
        actual = lf.days.get(k.isoformat())
        if not actual:
            continue
        ps, _ = split_for(k, k)
        pt = lf._model_core(k, k)  # noqa: SLF001
        if ps is None or pt is None:
            continue
        errs_s.append(abs(ps - actual))
        errs_t.append(abs(pt - actual))
    total, parts = split_for(target, today)
    if total is None:
        return {"use": False, "reason": "model reszty domu albo urządzeń nie ma jeszcze wyniku", "devices": [d["name"] for d in big]}
    mae_s = _mean(errs_s) if len(errs_s) >= 5 else None
    mae_t = _mean(errs_t) if len(errs_t) >= 5 else None
    use = mae_s is not None and mae_t is not None and mae_s < mae_t
    return {"use": use, "total": round(total, 2), "residual": round(total - sum(p["kwh"] for p in parts), 2), "parts": parts,
            "mae_split": None if mae_s is None else round(mae_s, 2), "mae_total": None if mae_t is None else round(mae_t, 2),
            "days": len(days_ok),
            "reason": ("dokładniejsza na ostatnich dniach" if use else "zwykły model był dokładniejszy na ostatnich dniach")
            if mae_s is not None else "za mało dni do porównania (potrzeba 5)"}
