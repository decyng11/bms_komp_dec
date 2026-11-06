"""Zgłoszenia w Ustawienia → Naprawy (rejestr problemów Home Assistanta).

Co minutę sprawdzamy kilka warunków. Problem pojawia się dopiero, gdy trwa dłużej niż jego próg (żeby chwilowy brak
odczytu nie straszył), a znika sam, gdy minie. Treść jest w translations/*.json (sekcja „issues”)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .const import CONF_GRID_POWER, DOMAIN
from .helpers import switch_on

_LOGGER = logging.getLogger(__name__)

# id → (opóźnienie w sekundach, poziom)
ISSUES: dict[str, tuple[int, str]] = {
    "inverter_no_data": (600, "error"),
    "price_missing": (1800, "warning"),
    "pv_forecast_missing": (7200, "warning"),
    "auto_apply_no_write": (60, "error"),
}


def _ir():
    from homeassistant.helpers import issue_registry as ir
    return ir


class Repairs:
    def __init__(self, rt) -> None:
        self.rt = rt
        self.hass = rt.hass
        self._since: dict[str, float] = {}
        self.active: set[str] = set()
        self._first = True

    def conditions(self) -> dict[str, tuple[bool, dict[str, str]]]:
        rt = self.rt
        out: dict[str, tuple[bool, dict[str, str]]] = {}
        # brak danych z falownika: ani SOC, ani mocy sieci
        lost = rt.soc() is None and rt.coordinator.get_float_opt(CONF_GRID_POWER) is None
        out["inverter_no_data"] = (lost, {})
        # cena sprzedaży (RCE / Pstryk / inna)
        out["price_missing"] = (rt.sell_price() is None, {"entity": str(self._price_entity() or "—")})
        # prognoza PV godzinowa (dziś i jutro) — tylko gdy jest jakiekolwiek źródło do sprawdzenia
        pv_missing = False
        try:
            pvp = rt.optimizer.pv_card_payload()
            pv_missing = not pvp.get("pv_hourly_today") and not pvp.get("pv_hourly_tomorrow")
        except Exception:  # noqa: BLE001
            pv_missing = False
        out["pv_forecast_missing"] = (pv_missing, {})
        # auto-stosowanie włączone, a falownik (połączony bezpośrednio) ma wyłączony zapis
        blocked: list[tuple[str, str]] = []
        if switch_on(self.hass, "auto_apply", False) and not switch_on(self.hass, "auto_apply_dry_run", False):
            try:
                from .health import _direct_write_blocked  # noqa: PLC0415 — health importuje runtime
                blocked = _direct_write_blocked(self.hass, [rt.eid(r) for r in ("work_mode", "charge_current", "export_surplus", "tou_select")])
            except Exception:  # noqa: BLE001
                blocked = []
        out["auto_apply_no_write"] = (bool(blocked), {"inverter": ", ".join(dict.fromkeys(n for _e, n in blocked)) or "—"})
        return out

    def _price_entity(self) -> str | None:
        try:
            from .const import CONF_PRICE_SELL_ENTITY, DEFAULT_PRICE_SELL_ENTITY
            return self.rt.optimizer.config.get(CONF_PRICE_SELL_ENTITY, DEFAULT_PRICE_SELL_ENTITY)
        except Exception:  # noqa: BLE001
            return None

    async def tick(self, now: datetime) -> None:
        ir = _ir()
        ts = now.timestamp()
        for iid, (cond, ph) in self.conditions().items():
            delay, level = ISSUES[iid]
            if cond:
                since = self._since.setdefault(iid, ts)
                if ts - since >= delay and iid not in self.active:
                    ir.async_create_issue(self.hass, DOMAIN, iid, is_fixable=False, is_persistent=False,
                                          severity=ir.IssueSeverity.ERROR if level == "error" else ir.IssueSeverity.WARNING,
                                          translation_key=iid, translation_placeholders=ph)
                    self.active.add(iid)
                    self.rt.log.add("notify", f"Naprawy HA: zgłoszono „{iid}”", "warn")
            else:
                self._since.pop(iid, None)
                # po restarcie HA rejestr może trzymać stare zgłoszenie — przy pierwszym sprawdzeniu kasujemy wszystkie nieaktualne
                if iid in self.active or self._first:
                    ir.async_delete_issue(self.hass, DOMAIN, iid)
                    self.active.discard(iid)
        self._first = False

    def status(self) -> dict[str, Any]:
        return {"active": sorted(self.active), "pending": {k: round(v) for k, v in self._since.items() if k not in self.active}}
