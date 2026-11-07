"""0.8.6: niski SOC — margines nad progiem falownika (z encji), pilne ładowanie od bieżącej godziny, sprzedaż nie zjeżdża pod margines."""
import asyncio, sys
from datetime import date, timedelta
sys.path.insert(0, ".")
from common import *   # noqa
import common
T = tariff; SCH = scheduler
def dt_util_now():
    return stubs.CLOCK['now']


def hourly(d, f):
    return [{"time": f"{d.isoformat()}T{h:02d}:00:00+01:00", "price": f(h)} for h in range(24)]


async def env(now, soc, floor=20, pv=0.6, load=7.7):
    hass, c, opt0, rt = build(); S = hass.states
    c.data = {"load_forecast": {"tomorrow_forecast": load}, "energy_battery_charge_today": 0.0, "energy_pv_today": 0.0}
    cfg = dict(const.SCHEDULER_DEFAULTS)
    cfg.update({"tariff_mode": "auto", "battery_capacity_kwh": 12.6, "max_charge_power_w": 3000, "target_soc_grid_charge": 90,
                "price_buy_entity": "sensor.energy_hub_aktualna_cena_g12w"})
    at(*now); d0 = date(*now[:3]); d1 = d0 + timedelta(days=1)
    g = lambda d: (lambda h: 1.29 if (d.weekday() < 5 and (6 <= h < 13 or 15 <= h < 22)) else 0.68)
    S.set("sensor.energy_hub_aktualna_cena_g12w", g(d0)(now[3]), {"prices": hourly(d0, g(d0)) + hourly(d1, g(d1))})
    rce = lambda h: 1760 if h == 18 else (300 if 10 <= h < 15 else 600)
    S.set("sensor.rce_pse_cena", 0.6, {"prices": arr(d0, rce) + arr(d1, lambda h: rce(h) + 10)})
    def solc(d, f): return {"detailedHourly": [{"period_start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "pv_estimate": f(h)} for h in range(24)]}
    S.set("sensor.solcast_pv_forecast_forecast_today", 30, solc(d0, lambda h: pv * 4 if 8 <= h < 16 else 0.0))
    S.set("sensor.solcast_pv_forecast_forecast_tomorrow", 30, solc(d1, lambda h: pv * 4 if 8 <= h < 16 else 0.0))
    S.set(c.config["soc"], soc)
    S.set("number.inverter_battery_shutdown_soc", floor, {"min": 5, "max": 80})
    sched = SCH.ScheduleOptimizer(hass, c, cfg)
    sched.tariff.prices = {"peak": 1.29, "off_peak": 0.68}
    T.set_profile(T.make_profile(cfg, prices_fn=sched.buy_hourly_for, eff_fn=lambda: 0.9, source="test"))
    return hass, c, sched, rt


def charge(plan):
    p = (plan.get("proposals") or {})
    s, e = p.get("start_grid_charge") or {}, p.get("stop_grid_charge") or {}
    return s.get("proposed"), e.get("proposed"), bool(s.get("skip")), s.get("reason") or ""


async def main():
    # --- dzisiejsza sytuacja: sobota 03:25, SOC 26%, próg 20% (z encji) → pilnie, start od bieżącej godziny
    hass, c, sched, rt = await env((2026, 11, 7, 3, 25), 26, floor=20)
    s0, e0, skip0, why0 = charge(await sched.suggest())
    check("SOC 26% / próg 20% (6 pkt nad progiem): jeszcze nie pilnie — jak dotąd 05:00", s0 == "05:00" and "startuje od razu" not in why0, (s0, why0[:120]))
    hass, c, sched, rt = await env((2026, 11, 7, 3, 25), 25, floor=20)
    s, e, skip, why = charge(await sched.suggest())
    check("SOC 25% / próg 20%: ładowanie startuje od bieżącej godziny (03:00), nie 05:00", s == "03:00" and not skip, (s, e, skip, why[:160]))
    check("uzasadnienie mówi o pilności", "startuje od razu" in why, why[:200])

    # --- zrzut użytkownika: sobota 05:18, SOC 25% — ostatnia godzina okna; plan nie może „planować następnej nocy” (SOC 66%)
    for lbl, when in (("sobota", (2026, 11, 7, 5, 18)), ("dzień roboczy", (2026, 11, 9, 5, 18))):
        hass, c, sched, rt = await env(when, 25, floor=20)
        sx, ex, skx, whyx = charge(await sched.suggest())
        check(f"{lbl} 05:18, SOC 25% / próg 20%: ładowanie 05:00–06:00, bez „bateria wystarczy do rana”", sx == "05:00" and ex == "06:00" and not skx and "wystarczy" not in whyx, (sx, ex, skx, whyx[:160]))
        hass, c, sched, rt = await env(when, 60, floor=20)
        sx, ex, skx, whyx = charge(await sched.suggest())
        check(f"{lbl} 05:18, SOC 60%: bez pilnego ładowania (jak dotąd)", "startuje od razu" not in whyx, (sx, whyx[:100]))

    # --- ten sam SOC, ale próg z encji 10% → nie pilnie (26 > 10+5), zwykła logika (nie od 03:00)
    hass, c, sched, rt = await env((2026, 11, 7, 3, 25), 26, floor=10)
    s2, e2, skip2, why2 = charge(await sched.suggest())
    check("SOC 26% / próg 10%: nie pilnie (brak „startuje od razu”)", "startuje od razu" not in why2, (s2, why2[:160]))

    # --- próg 30% z encji: SOC 33% jest już pilny (33 <= 30+5)
    hass, c, sched, rt = await env((2026, 11, 7, 3, 25), 33, floor=30)
    s3, e3, skip3, why3 = charge(await sched.suggest())
    check("próg z encji 30%: SOC 33% → pilnie od bieżącej godziny", (s3 == "03:00" and "startuje od razu" in why3) or skip3, (s3, skip3, why3[:160]))

    # --- SOC wysoki → zachowanie jak dotąd, bez „startuje od razu”
    hass, c, sched, rt = await env((2026, 11, 7, 3, 25), 60, floor=20)
    s4, e4, skip4, why4 = charge(await sched.suggest())
    check("SOC 60%: brak pilnego ładowania", "startuje od razu" not in why4, (s4, why4[:120]))

    # --- margines w „night_floor”: próg 20% + margines świtu 10 pkt = 30%
    hass, c, sched, rt = await env((2026, 11, 7, 12, 0), 80, floor=20)
    ctx = sched._build_context(dt_util_now(), 80.0)
    check("night_floor = próg falownika z encji + margines świtu (≥ 30%)", ctx["night_floor"] >= 30.0, ctx["night_floor"])
    hass, c, sched, rt = await env((2026, 11, 7, 12, 0), 80, floor=10)
    ctx = sched._build_context(dt_util_now(), 80.0)
    check("próg 10% w encji → night_floor 20% (nie na sztywno 30%)", 20.0 <= ctx["night_floor"] < 30.0, ctx["night_floor"])

    print(f"LOWSOC PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)

asyncio.run(main())
