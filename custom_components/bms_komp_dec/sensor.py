"""Sensors for EMS komp-dec."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.util import dt as dt_util

from .direct import is_inverter_entry
from .const import (
    CONF_BATTERY_CAPACITY_KWH, CONF_PRICE_BUY_ENTITY, CONF_PRICE_SELL_ENTITY, DEFAULT_BATTERY_CAPACITY_KWH,
    DEFAULT_PRICE_BUY_ENTITY, DEFAULT_PRICE_SELL_ENTITY,
)
from .const import DOMAIN, RUNTIME_SENSORS, SENSORS
from . import accuracy as acc
from . import money as money_mod
from . import inverter_ctl as ictl
from .entity import BmsBaseEntity
from .monitor import FAULT_NOTE, fault_text
from .tariff import get_profile, next_offpeak_window


async def async_setup_entry(hass, entry, async_add_entities):
    if is_inverter_entry(entry):                      # falownik dodany bezpośrednio (tryb bezpośredni)
        from .direct.p_sensor import async_setup_entry as _direct_setup
        return await _direct_setup(hass, entry, async_add_entities)
    await _async_setup_bms_entry(hass, entry, async_add_entities)


async def _async_setup_bms_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [BmsSensor(coordinator, k, n, u, i) for k, n, u, i, _src in SENSORS]
    entities.append(BmsLoadForecastSensor(coordinator))
    entities.extend(BmsRuntimeSensor(coordinator, k, n, u, i) for k, n, u, i in RUNTIME_SENSORS)
    async_add_entities(entities)


def _r3(v):
    try:
        return None if v is None else round(float(v), 3)
    except (TypeError, ValueError):
        return None


class BmsSensor(BmsBaseEntity, SensorEntity):
    def __init__(self, coordinator, key, name, unit, icon):
        super().__init__(key, name, domain="sensor")
        self.coordinator = coordinator
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        if unit == "W":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif unit == "kWh":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif unit == "%":
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_state_class = SensorStateClass.MEASUREMENT

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._key)


class BmsLoadForecastSensor(BmsBaseEntity, SensorEntity):
    """Prognoza zużycia domu na jutro + wszystkie metryki modelu."""

    # Duże atrybuty (listy prognoz) nie powinny trafiać do bazy rekordera co 10 s.
    _unrecorded_attributes = frozenset({
        "days", "forecast_7d", "hourly_forecast", "hourly_forecast_today", "hourly_today", "seasonal_factors", "history_14d",
        "confidence_interval", "temperature_correction", "forecast_split",
    })

    def __init__(self, coordinator):
        super().__init__("load_forecast", "EMS Prognoza zużycia domu", domain="sensor")
        self.coordinator = coordinator
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_icon = "mdi:chart-bar"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    def _data(self) -> dict:
        return (self.coordinator.data or {}).get("load_forecast") or {}

    @property
    def native_value(self):
        return self._data().get("tomorrow_forecast")

    @property
    def extra_state_attributes(self):
        d = self._data()
        return {
            "days": d.get("days", []),
            "history_14d": d.get("history_14d", []),
            "forecast_bias": d.get("forecast_bias"),
            "history_days": d.get("history_days", 0),
            "forecast_7d": d.get("forecast_7d", []),
            "mape_14d": d.get("mape_14d"),
            "confidence_interval": d.get("confidence_interval"),
            "hourly_forecast": d.get("hourly_forecast"),
            "hourly_forecast_today": d.get("hourly_forecast_today"),
            "hourly_today": d.get("hourly_today"),
            "hourly_today_hour": d.get("hourly_today_hour"),
            "temperature_correction": d.get("temperature_correction"),
            "seasonal_factors": d.get("seasonal_factors"),
            "profiles_days": d.get("profiles_days"),
            "forecast_split": d.get("forecast_split"),
        }


class BmsRuntimeSensor(BmsBaseEntity, SensorEntity):
    """Dziennik decyzji, bilans PLN i dynamiczna rezerwa SOC (liczone przez BmsRuntime)."""

    _unrecorded_attributes = frozenset({
        "entries", "history", "cheap_start", "cheap_end", "usable_kwh", "inverter_floor_source", "inverter_floor_hourly",
        "tariff_peaks", "tariff_label", "tariff_night", "tariff_midday", "battery_sign_source",
        "ctl_work_mode", "ctl_charge_current", "ctl_export_surplus", "ctl_tou", "inverter_prefix",
        "curve", "proposals", "days", "watches", "alarms", "recent_notifications",
        "prices_sell_today", "prices_sell_tomorrow", "prices_buy_today", "prices_buy_tomorrow",
        "price_sell_entity", "price_buy_entity", "price_sell_source", "price_buy_source", "tariff_mode", "tariff_dynamic",
        "pv_forecast_source", "pv_hourly_today", "pv_hourly_tomorrow", "pv_daily", "assumptions",
        "devices", "power_total", "accuracy",
    })

    def __init__(self, coordinator, key, name, unit, icon):
        super().__init__(key, name, domain="sensor")
        self.coordinator = coordinator
        self._attr_icon = icon
        if unit:
            self._attr_native_unit_of_measurement = unit
        if unit == "PLN":
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_suggested_display_precision = 2

    @property
    def _rt(self):
        return getattr(self.coordinator, "runtime", None)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))
        rt = self._rt
        if rt is not None and self._key == "decision_log":
            self.async_on_remove(rt.log.add_listener(self._on_log))

    def _on_log(self) -> None:
        if self.hass is not None:
            self.async_write_ha_state()

    @property
    def native_value(self):
        rt = self._rt
        if rt is None:
            return None
        today = dt_util.now().date()
        if self._key == "decision_log":
            return rt.log.latest_text
        if self._key == "profit_today":
            return round(rt.ledger.day_net(today), 2)
        if self._key == "profit_month":
            return round(rt.ledger.month_net(today), 2)
        if self._key == "profit_total":
            return round(rt.ledger.total_net(), 2)
        if self._key == "reserve_soc":
            return rt.reserve()["pct"]
        if self._key == "plan_curve":
            plan = rt.plan()
            if not plan:
                return "brak"
            return "błąd" if plan.get("error") else str(plan.get("mode") or "normal")
        if self._key == "battery_health":
            return self._health(rt).get("eff_30d")
        if self._key == "monthly_report":
            return rt.report_cached().get("net")
        if self._key == "monitor_status":
            st = rt.state
            return len(st.get("alarms_active") or {}) + (1 if st.get("low_soc_active") else 0)
        if self._key == "devices":
            return len(rt.devices.devices)
        if self._key == "savings":
            return rt.insights.savings()["month"]["vs_nobat"]
        if self._key == "forecast_accuracy":
            return rt.insights.accuracy(getattr(rt.coordinator, "load_forecast", None))["pv"]["mape"]
        return None

    @staticmethod
    def _health(rt) -> dict:
        cap = float(rt.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
        return rt.stats.summary(cap)

    def _floor_attrs(self, rt) -> dict:
        """Próg odcięcia falownika, użyteczna energia i najbliższe tanie okno — dla karty."""
        out: dict = {}
        now = dt_util.now()
        fl = None
        try:
            inv = rt.inverter_floor()
            fl = float(inv["hourly"][now.hour])
            out["inverter_floor"] = round(fl, 1)
            out["inverter_floor_source"] = inv.get("source")
            out["inverter_floor_hourly"] = [round(float(x), 1) for x in inv["hourly"][:24]]   # dla symulacji na karcie (próg zmienia się z programami ToU)
        except Exception:  # noqa: BLE001
            pass
        try:
            soc = rt.optimizer._read_soc()
            if fl is not None and soc is not None:
                cap = float(rt.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))
                out["usable_kwh"] = round(max(0.0, (soc - fl) / 100.0 * cap), 2)
        except Exception:  # noqa: BLE001
            pass
        try:
            w = next_offpeak_window(now)
            if w:
                out["cheap_start"], out["cheap_end"], out["cheap_now"] = w[0].isoformat(), w[1].isoformat(), w[2]
        except Exception:  # noqa: BLE001
            pass
        try:
            prof = get_profile()
            out["tariff_peaks"] = prof.as_text()
            out["tariff_label"] = prof.label()
            nw, mw = prof.night_window(), prof.midday_window()
            out["tariff_night"] = f"{nw[0]}-{nw[1]}" if nw else None
            out["tariff_midday"] = f"{mw[0]}-{mw[1]}" if mw else None
            out["tariff_weekend_offpeak"] = prof.weekend_offpeak
            out["tariff_holiday_offpeak"] = prof.holiday_offpeak
        except Exception:  # noqa: BLE001
            pass
        try:
            bs = rt.battery_sign()
            out["battery_charge_sign"] = bs["sign"]
            out["battery_sign_source"] = bs["source"]
        except Exception:  # noqa: BLE001
            pass
        try:
            for role, name in (("work_mode", "ctl_work_mode"), ("charge_current", "ctl_charge_current"),
                               ("export_surplus", "ctl_export_surplus"), ("tou_select", "ctl_tou")):
                out[name] = rt.eid(role)
            out["inverter_prefix"] = ictl.prefix_of(out["ctl_work_mode"])
            out["grid_charging_on"] = rt.grid_charging_on()
        except Exception:  # noqa: BLE001
            pass
        try:
            cc = rt.eid("charge_current")
            out["normal_charge_a"] = ictl.normal_charge_current(rt.hass, cc, rt.state.get("normal_charge_current"))
            ex = rt.eid("export_surplus")
            out["sell_power_w"] = ictl.power_setting(rt.hass, ex, "sell_export_power_w", 6000.0)
            out["surplus_power_w"] = ictl.power_setting(rt.hass, ex, "surplus_power_w", 9700.0)
        except Exception:  # noqa: BLE001
            pass
        return out

    @staticmethod
    def _price_attrs(rt) -> dict:
        """Ceny godzinowe, których używa planer (karta pokazuje dokładnie te same), i tryb taryfy."""
        out: dict = {}
        try:
            opt = rt.optimizer
            today = dt_util.now().date()
            tom = today + timedelta(days=1)
            r4 = lambda arr: [round(float(v), 4) if isinstance(v, (int, float)) else None for v in arr] if arr else None  # noqa: E731
            sell = opt.rce_arrays()
            out["prices_sell_today"] = r4(sell.get(today.isoformat()))
            out["prices_sell_tomorrow"] = r4(sell.get(tom.isoformat()))
            out["price_sell_entity"] = opt.config.get(CONF_PRICE_SELL_ENTITY, DEFAULT_PRICE_SELL_ENTITY)
            rep_s = opt.rce_report() or {}
            out["price_sell_source"] = (rep_s.get("today") or {}).get("source")
            prof = get_profile()
            out["tariff_mode"] = prof.mode
            out["tariff_dynamic"] = prof.dynamic_for(today)
            out["price_buy_entity"] = opt.config.get(CONF_PRICE_BUY_ENTITY, DEFAULT_PRICE_BUY_ENTITY)
            if prof.mode != "zone":
                out["prices_buy_today"] = r4(opt.buy_hourly_for(today))
                out["prices_buy_tomorrow"] = r4(opt.buy_hourly_for(tom))
                out["price_buy_source"] = ((opt.buy_report() or {}).get("today") or {}).get("source")
        except Exception:  # noqa: BLE001
            pass
        return out

    @staticmethod
    def _pv_attrs(rt) -> dict:
        """Prognoza PV dla karty — ta sama, której używa planer (Solcast albo Forecast.Solar)."""
        try:
            return rt.optimizer.pv_card_payload()
        except Exception:  # noqa: BLE001
            return {}

    @property
    def extra_state_attributes(self):
        rt = self._rt
        if rt is None:
            return None
        if self._key == "decision_log":
            return {"entries": rt.log.last(80), "count": len(rt.log.entries)}
        if self._key == "profit_today":
            day = rt.ledger.days.get(dt_util.now().date().isoformat()) or {}
            return {
                "history": rt.ledger.history(31),
                "export_kwh": round(day.get("export_kwh", 0.0), 2),
                "import_kwh": round(day.get("import_kwh", 0.0), 2),
                "revenue": round(day.get("revenue", 0.0), 2),
                "cost": round(day.get("cost", 0.0), 2),
                "neg_export_kwh": round(day.get("neg_export_kwh", 0.0), 2),
                "sums": {sc: rt.ledger.sums(dt_util.now().date(), sc) for sc in ("day", "month", "total")},
                "extras": money_mod.bundle(rt.ledger, rt.stats, dt_util.now().date()),
            }
        if self._key == "reserve_soc":
            res = rt.reserve()
            return {"need_kwh": res["need_kwh"], "until_hour": res["until_hour"],
                    "enabled": res["enabled"], "sell_threshold": round(rt.sell_soc_threshold(), 1),
                    "price_buy": _r3(rt.buy_price()), "price_sell": _r3(rt.sell_price()),
                    **self._floor_attrs(rt), **self._price_attrs(rt), **self._pv_attrs(rt),
                    "capacity_kwh": float(rt.optimizer.config.get(CONF_BATTERY_CAPACITY_KWH, DEFAULT_BATTERY_CAPACITY_KWH))}
        if self._key == "plan_curve":
            plan = rt.plan() or {}
            return {"mode": plan.get("mode"), "generated_at": plan.get("generated_at"), "error": plan.get("error"),
                    "curve": plan.get("curve"), "proposals": plan.get("proposals"), "assumptions": plan.get("assumptions")}
        if self._key == "battery_health":
            return self._health(rt)
        if self._key == "monthly_report":
            return dict(rt.report_cached())
        if self._key == "monitor_status":
            st = rt.state
            return {
                "alarms": [{"entity_id": e, "state": v, "text": fault_text(v)} for e, v in (st.get("alarms_active") or {}).items()],
                "low_soc_active": bool(st.get("low_soc_active")),
                "fault_note": FAULT_NOTE,
                "storm_until": st.get("storm_until"),
                "vacation_since": st.get("vacation_since"),
                "watches": rt.watch.list(),
                "accuracy": acc.summary(st.get("accuracy") or []),
                "recent_notifications": [e for e in rt.log.last(200) if e.get("kind") == "notify"][-10:],
            }
        if self._key == "devices":
            live = rt.devices.live()
            return {"devices": live, "power_total": round(sum(x["power"] or 0.0 for x in live), 1)}
        if self._key == "savings":
            sv = rt.insights.savings()
            return {"today_vs_nobat": sv["today"]["vs_nobat"], "today_vs_simple": sv["today"]["vs_simple"],
                    "month_vs_simple": sv["month"]["vs_simple"], "year_vs_nobat": sv["year"]["vs_nobat"],
                    "year_vs_simple": sv["year"]["vs_simple"], "month_cost": sv["month"]["actual"],
                    "days_counted": sv["total"]["days"], "since": sv["since"]}
        if self._key == "forecast_accuracy":
            ac = rt.insights.accuracy(getattr(rt.coordinator, "load_forecast", None))
            return {"pv_bias": ac["pv"]["bias"], "pv_days": ac["pv"]["n"], "load_mape": ac["load"]["mape"],
                    "load_bias": ac["load"]["bias"], "soc_plan_error": ac["soc"]["mae"],
                    "pv_correction": ac["pv_correction"]["factor"]}
        return None
