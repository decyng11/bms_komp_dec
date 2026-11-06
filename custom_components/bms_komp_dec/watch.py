"""Kontrola wartości po zapisie parametru falownika (po stronie integracji, nie karty).

Poprzednio sprawdzanie „czy falownik naprawdę przyjął wartość” działało tylko, dopóki karta była otwarta
w przeglądarce. Teraz karta (lub automatyzacja) zgłasza zapis usługą `bms_komp_dec.watch_write`, a
integracja sama sprawdza wartość po 1, 3 i 6 minutach, zapisuje wynik i — przy rozbieżności — wysyła
powiadomienie. Przywrócenie poprzedniej wartości pozostaje decyzją użytkownika (bezpieczniej niż automat).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .helpers import state_str

_LOGGER = logging.getLogger(__name__)

CHECK_AFTER_S = (60, 180, 360)
KEEP_S = 24 * 3600
MAX_ITEMS = 30
DEFAULT_TOL = 0.5
_TIME_RE = re.compile(r"^\d\d:\d\d")
U16_OVERFLOW_MIN = 60000          # wartości bliskie 65535 przy małej oczekiwanej to typowe przepełnienie rejestru U16


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class WriteWatch:
    def __init__(self, rt) -> None:
        self.rt = rt

    @property
    def items(self) -> list[dict[str, Any]]:
        lst = self.rt.state.get("watches")
        if not isinstance(lst, list):
            lst = self.rt.state["watches"] = []
        return lst

    # -------------------------------------------------------------- API
    def add(self, entity_id: str, expected: Any, label: str | None = None, tolerance: float | None = None,
            previous: Any = None, source: str = "karta") -> dict[str, Any]:
        entity_id = str(entity_id or "").strip()[:120]
        if "." not in entity_id:
            raise ValueError("entity_id jest wymagane (np. number.inverter_zero_export_power)")
        exp_num = _num(expected)
        item = {
            "id": uuid.uuid4().hex[:10],
            "entity_id": entity_id,
            "label": str(label or entity_id)[:120],
            "expected": exp_num if exp_num is not None else str(expected)[:80],
            "tolerance": float(tolerance) if _num(tolerance) is not None and float(tolerance) >= 0 else DEFAULT_TOL,
            "previous": _num(previous) if _num(previous) is not None else (None if previous is None else str(previous)[:80]),
            "source": str(source)[:40],
            "t0": dt_util.now().timestamp(),
            "next": 0,                  # indeks następnej kontroli w CHECK_AFTER_S
            "status": "pending",        # pending | ok | drift | unavailable
            "checks": [],
        }
        self.items.append(item)
        if len(self.items) > MAX_ITEMS:
            del self.items[: len(self.items) - MAX_ITEMS]
        self.rt._save_state()  # noqa: SLF001
        self.rt.log.add("verify", f"Kontrola po zapisie: {item['label']} → {item['expected']} (sprawdzę po 1, 3 i 6 min)", "info")
        return self.public(item)

    def clear(self, watch_id: str | None = None) -> int:
        before = len(self.items)
        if watch_id:
            self.items[:] = [i for i in self.items if i.get("id") != watch_id]
        else:
            self.items[:] = [i for i in self.items if i.get("status") == "pending"]
        n = before - len(self.items)
        if n:
            self.rt._save_state()  # noqa: SLF001
        return n

    @staticmethod
    def public(item: dict[str, Any]) -> dict[str, Any]:
        return {k: item.get(k) for k in ("id", "entity_id", "label", "expected", "tolerance", "previous",
                                         "source", "t0", "status", "checks")}

    def list(self) -> list[dict[str, Any]]:
        return [self.public(i) for i in reversed(self.items)]

    # ------------------------------------------------------------ kontrola
    def _evaluate(self, item: dict[str, Any]) -> tuple[bool | None, Any, str]:
        """(zgodne?, odczyt, uwaga) — None gdy encja niedostępna."""
        raw = state_str(self.rt.hass, item["entity_id"])
        if raw is None:
            return None, None, "encja niedostępna"
        exp = item["expected"]
        if isinstance(exp, (int, float)):
            val = _num(raw)
            if val is None:
                return False, raw, "wartość nie jest liczbą"
            note = ""
            if val >= U16_OVERFLOW_MIN and exp < 1000:
                note = "wygląda na przepełnienie rejestru U16 (65536 − x) — wartość ujemna trafiła do rejestru bez znaku"
            return abs(val - float(exp)) <= float(item.get("tolerance", DEFAULT_TOL)), val, note
        a, b = str(raw).strip().lower(), str(exp).strip().lower()
        if _TIME_RE.match(a) and _TIME_RE.match(b):          # encje time: „07:30:00” == „07:30”
            return a[:5] == b[:5], raw, ""
        return a == b, raw, ""

    async def tick(self, now: datetime) -> None:
        now_ts = now.timestamp()
        dirty = False
        for item in list(self.items):
            if item.get("status") == "pending":
                age = now_ts - float(item.get("t0", now_ts))
                idx = int(item.get("next", 0))
                while idx < len(CHECK_AFTER_S) and age >= CHECK_AFTER_S[idx]:
                    ok, val, note = self._evaluate(item)
                    item["checks"].append({"t": int(now_ts), "after_s": CHECK_AFTER_S[idx],
                                           "value": val, "ok": ok, "note": note})
                    idx += 1
                    item["next"] = idx
                    dirty = True
                    if ok is False:
                        item["status"] = "drift"
                        await self._report_drift(item, val, note)
                        break
                    if ok is None:
                        item["status"] = "unavailable" if idx >= len(CHECK_AFTER_S) else "pending"
                if item["status"] == "pending" and idx >= len(CHECK_AFTER_S):
                    item["status"] = "ok"
                    self.rt.log.add("verify", f"Kontrola po zapisie: {item['label']} = {item['expected']} — wartość się utrzymała", "ok")
            elif now_ts - float(item.get("t0", now_ts)) > KEEP_S:
                self.items.remove(item)
                dirty = True
        if dirty:
            self.rt._save_state()  # noqa: SLF001

    async def _report_drift(self, item: dict[str, Any], val: Any, note: str) -> None:
        prev = item.get("previous")
        restore = f"\nPoprzednia wartość: {prev}. Przywróć ją w Diagnostyce (Dziennik → Cofnij)." if prev is not None else ""
        body = (f"{item['label']}: ustawiono {item['expected']}, a po {int(item['checks'][-1]['after_s'] // 60)} min "
                f"falownik raportuje {val}." + (f"\n{note}." if note else "") + restore)
        await self.rt.monitor.notifier.send(
            "drift", "⚠ BMS: parametr falownika zmienił wartość", body,
            key=f"drift:{item['entity_id']}", cooldown_s=1800, level="error")
