REPO = __import__("pathlib").Path(__file__).resolve().parents[2].as_posix()  # katalog główny repozytorium
import asyncio, sys, types, importlib
from datetime import datetime, date, timedelta
sys.path.insert(0, ".")
import stubs
stubs.install()
sys.path.insert(0, REPO + "")
pkg = importlib.import_module("custom_components.bms_komp_dec")
from custom_components.bms_komp_dec import runtime as rtm, holidays_pl, reserve, ledger as ledm, automation, helpers, tariff, scheduler, sensor, binary_sensor, button, switch, number, time as time_mod, const
from custom_components.bms_komp_dec import load_forecast as lfm
TZ = stubs.TZ
PASS = FAIL = 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1
    else: FAIL += 1; print("FAIL:", name, extra)

def at(y, m, d, hh, mm=0, ss=0):
    stubs.CLOCK["now"] = datetime(y, m, d, hh, mm, ss, tzinfo=TZ)
    return stubs.CLOCK["now"]

# ---------------------------------------------------------------- święta
check("easter 2026", holidays_pl.easter_sunday(2026) == date(2026, 4, 5))
check("easter 2025", holidays_pl.easter_sunday(2025) == date(2025, 4, 20))
check("boze cialo 2026", date(2026, 6, 4) in holidays_pl.polish_holidays(2026))
check("wigilia 2025", holidays_pl.is_holiday(date(2025, 12, 24)))
check("wigilia 2024 nie", not holidays_pl.is_holiday(date(2024, 12, 24)))
check("13 swiat do 2024, 14 od 2025 (Wigilia)", len(holidays_pl.polish_holidays(2024)) == 13 and len(holidays_pl.polish_holidays(2025)) == 14)

# ---------------------------------------------------------------- taryfa
check("peak pon 10", tariff.is_g12w_peak(datetime(2026, 10, 26, 10, tzinfo=TZ)))
check("offpeak pon 14", not tariff.is_g12w_peak(datetime(2026, 10, 26, 14, tzinfo=TZ)))
check("offpeak sob", not tariff.is_g12w_peak(datetime(2026, 10, 24, 10, tzinfo=TZ)))
check("offpeak wielkanocny pon", not tariff.is_g12w_peak(datetime(2026, 4, 6, 10, tzinfo=TZ)))

# ---------------------------------------------------------------- rezerwa
pv = [0.0]*24
for h in range(8, 17): pv[h] = 2.0
r = reserve.compute_reserve(now_hour=17, capacity_kwh=10, floor_pct=15, load_hourly=[0.5]*24, pv_hourly=pv)
check("reserve evening", abs(r["pct"] - 85.0) < 0.2 and abs(r["need_kwh"] - 7.0) < 0.01, r)
r = reserve.compute_reserve(now_hour=10, capacity_kwh=10, floor_pct=15, load_hourly=[0.5]*24, pv_hourly=pv)
check("reserve daytime = floor", r["pct"] == 15.0 and r["need_kwh"] == 0, r)
r = reserve.compute_reserve(now_hour=20, capacity_kwh=10, floor_pct=10, load_hourly=None, pv_hourly=None)
check("reserve no forecast fallback", r["need_kwh"] > 0 and r["pct"] <= 95, r)
r = reserve.compute_reserve(now_hour=17, capacity_kwh=5, floor_pct=15, load_hourly=[2.0]*24, pv_hourly=pv)
check("reserve capped 95", r["pct"] == 95.0, r)

# ---------------------------------------------------------------- ledger
hass = stubs.FakeHass()
L = ledm.Ledger(hass)
t0 = at(2026, 10, 28, 12)
L.update(t0, -3600, 0.5, 0.8)
L.update(t0 + timedelta(seconds=10), -3600, 0.5, 0.8)   # 3.6 kW * 10 s = 0.01 kWh
d = L.days["2026-10-28"]
check("ledger export kwh", abs(d["export_kwh"] - 0.01) < 1e-9, d)
check("ledger revenue", abs(d["revenue"] - 0.005) < 1e-9)
L.update(t0 + timedelta(seconds=20), 7200, 0.5, 0.8)    # import 2 kW * 10 s
check("ledger cost", abs(L.days["2026-10-28"]["cost"] - (7200*10/3.6e6*0.8)) < 1e-9)
L.update(t0 + timedelta(seconds=400), -3600, 0.5, 0.8)  # przerwa > 120 s – pomijamy
check("ledger gap ignored", abs(L.days["2026-10-28"]["export_kwh"] - 0.01) < 1e-9)
L.update(t0 + timedelta(seconds=410), -3600, -0.1, 0.8)
check("ledger neg price", L.days["2026-10-28"]["neg_export_kwh"] > 0 and L.days["2026-10-28"]["revenue"] < 0.005)
check("ledger net/month/total", abs(L.day_net(date(2026,10,28)) - L.total_net()) < 1e-12 and L.month_net(date(2026,10,1)) == L.total_net())
check("ledger history", L.history()[0]["date"] == "2026-10-28")

# ---------------------------------------------------------------- ThrottledStore
ts = helpers.ThrottledStore(hass, 1, "k", 60)
n = {"v": 0}
for i in range(5): ts.request_save(lambda: {"v": i})
check("throttled: tylko 1 timer", ts._store.delay_calls == 1, ts._store.delay_calls)
ts._store.func()      # symulacja odpalenia timera
ts.request_save(lambda: {"v": 99})
check("throttled: po zapisie kolejny timer", ts._store.delay_calls == 2)

# ---------------------------------------------------------------- normalize_price
check("price MWh", helpers.normalize_price(450.0) == 0.45 and helpers.normalize_price(0.45) == 0.45 and helpers.normalize_price(-120.0) == -0.12)

# ---------------------------------------------------------------- środowisko runtime
class Tariff:
    def get_price(self, dt): return 0.7
    def sample(self): pass
class Opt:
    def __init__(self): self.config = {}; self.tariff = Tariff(); self.ref = 0.30; self.pv = None
    def profit_reference(self): return self.ref
    def pv_hourly_today(self): return self.pv
    def pv_scale_next_day(self): return 1.0
class Coord:
    def __init__(self, hass):
        self.hass = hass; self.config = dict(const.DEFAULT_CONFIG)
        self.data = {"energy_battery_charge_today": 1.0, "energy_pv_today": 10.0, "grid_power": -100.0, "soc": 80.0, "load_forecast": {}}
    def _raw(self, key):
        st = self.hass.states.get(self.config.get(key))
        return None if st is None or st.state in ("unknown", "unavailable", "") else st.state
    def get_float_opt(self, key):
        v = self._raw(key)
        try: return None if v is None else float(v)
        except ValueError: return None
    def get_str(self, key, default=""):
        v = self._raw(key); return default if v is None else v
def build(hass=None):
    hass = hass or stubs.FakeHass()
    S = hass.states
    c = Coord(hass)
    S.set(c.config["soc"], 80); S.set(c.config["grid_power"], -100)
    S.set("select.inverter_work_mode", "Zero Export To Load")
    S.set("number.inverter_export_surplus_power", 9700, {"max": 12000})
    S.set("number.inverter_battery_max_charging_current", 170, {"max": 185})
    S.set("select.inverter_time_of_use", "Week")
    S.set("sensor.rce_pse_cena", 0.60)
    for k, *_ in const.NUMBERS: S.set(f"number.bms_{k}", const.NUMBER_DEFAULTS[k])
    for k, _n, _i, d in const.SWITCHES: S.set(f"switch.bms_{k}", "on" if d else "off")
    for k, _n in const.TIMES: S.set(f"time.bms_{k}", "00:00:00")
    for k, *_ in const.BUTTONS: S.set(f"button.bms_{k}", "unknown")
    opt = Opt()
    rt = rtm.BmsRuntime(hass, c, opt)
    c.runtime = rt
    rtm.VERIFY_FIRST_WAIT_S = 0; rtm.VERIFY_SECOND_WAIT_S = 0
    return hass, c, opt, rt
def calls(hass, domain=None):
    return [c for c in hass.services.calls if domain is None or c[0] == domain]

async def settle(hass):
    await asyncio.gather(*hass.tasks, return_exceptions=True)


from custom_components.bms_komp_dec import inverter_floor as invf, tariff as tar
async def main():
    from datetime import date, timedelta
    def arr(d, f): return [{"start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "rce_pln": f(h)} for h in range(24)]
    async def mk(now, soc, shutdown=None, progs=None, tou="Week", manual=None, pvt=None, load=8.0, prices=(1.29, 0.92), nums=None):
        hass, c, opt0, rt = build(); S = hass.states
        c.data = {"load_forecast": {"tomorrow_forecast": load}, "energy_battery_charge_today": 0.0, "energy_pv_today": 3.0}
        sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS))
        sched.tariff.prices = {"peak": prices[0], "off_peak": prices[1]}
        at(*now); d0 = date(*now[:3]); d1 = d0 + timedelta(days=1)
        price = lambda h: 250 if 10 <= h < 15 else (700 if 17 <= h < 21 else 450)
        S.set("sensor.rce_pse_cena", 0.6, {"prices": arr(d0, price) + arr(d1, price)})
        def solc(d, f): return {"detailedHourly": [{"period_start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "pv_estimate": f(h)} for h in range(24)]}
        S.set("sensor.solcast_pv_forecast_forecast_today", 4, solc(d0, pvt or (lambda h: 0.6 if 9 <= h < 15 else 0.0)))
        S.set("sensor.solcast_pv_forecast_forecast_tomorrow", 4, solc(d1, pvt or (lambda h: 0.6 if 9 <= h < 15 else 0.0)))
        S.set(c.config["soc"], soc)
        if shutdown is not None: S.set("number.inverter_battery_shutdown_soc", shutdown)
        if progs:
            S.set("select.inverter_time_of_use", tou)
            for i,(tm,sc,ch) in enumerate(progs,1):
                S.set(f"time.inverter_program_{i}_time", tm); S.set(f"number.inverter_program_{i}_soc", sc); S.set(f"select.inverter_program_{i}_charging", ch)
        if manual is not None: S.set("number.bms_inverter_floor_soc", manual)
        for k,v in (nums or {}).items(): S.set(f"number.bms_{k}", v)
        return hass, c, sched

    # --- profil progu
    hass, c, sched = await mk((2026,11,3,10), 50, shutdown=25)
    p = invf.floor_profile(hass)
    check("floor: SOC wyłączenia 25 -> płasko 25", p["hourly"] == [25.0]*24 and p["shutdown"] == 25, p["source"])
    hass, c, sched = await mk((2026,11,3,10), 50, shutdown=20, progs=[("00:00:00",30,"Disabled"),("06:00:00",25,"Disabled"),("13:00:00",40,"Allow Grid")])
    p = invf.floor_profile(hass)
    check("floor: programy TOU nakładają próg (max z shutdown)", p["hourly"][3]==30 and p["hourly"][8]==25 and p["hourly"][14]==40 and p["hourly"][23]==40, p["hourly"])
    hass, c, sched = await mk((2026,11,3,10), 50, shutdown=20, progs=[("00:00:00",100,"Disabled")])
    check("floor: program SOC 100 (blokada rozładowania) nie jest progiem planowania", invf.floor_profile(hass)["hourly"][5] == 20)
    hass, c, sched = await mk((2026,11,3,10), 50, shutdown=20, progs=[("00:00:00",30,"Disabled")], tou="Disabled")
    check("floor: TOU wyłączone -> tylko SOC wyłączenia", invf.floor_profile(hass)["hourly"][5] == 20)
    hass, c, sched = await mk((2026,11,3,10), 50, shutdown=25, manual=22)
    check("floor: ręczne ustawienie ma pierwszeństwo", invf.floor_profile(hass)["hourly"] == [22.0]*24)
    hass, c, sched = await mk((2026,11,3,10), 50)
    check("floor: brak encji falownika -> 0", invf.floor_profile(hass)["hourly"] == [0.0]*24)

    # --- _run: SOC poniżej progu nie rośnie sztucznie
    hass, c, sched = await mk((2026,11,3,23), 20, shutdown=25)
    ctx = sched._build_context(stubs.CLOCK["now"], 20.0)
    soc_end, low = sched._run(ctx, 20.0, 24, 28)
    check("run: SOC 20% < próg 25% — bateria nie 'rośnie' do progu", soc_end <= 20.0 + 1e-6, soc_end)
    ctx2 = sched._build_context(stubs.CLOCK["now"], 60.0)
    s2, _ = sched._run(ctx2, 60.0, 24, 30)
    check("run: SOC nie schodzi poniżej progu falownika", s2 >= 25.0 - 1e-6, s2)

    # --- ładowanie nocne: dawniej 'wystarczy', teraz uwzględnia próg 25%
    import re as _re
    kwh = {}
    for sd in (None, 25):
        hass, c, sched = await mk((2026,11,2,21), 35, shutdown=sd)
        P = (await sched.suggest())["proposals"]["start_grid_charge"]
        print("   noc, próg", sd, "->", "SKIP" if P["skip"] else P["proposed"], "|", P["reason"][:200])
        m = _re.search(r"cel (\d+)%", P["reason"]); kwh[sd] = float(m.group(1)) if m else 0.0
        if sd is not None: check("noc: SOC 35%, próg 25% -> proponuje ładowanie", not P["skip"] and P["proposed"], P["reason"])
    # dawniej planer porównywał SOC z początku nocy z SOC potrzebnym na koniec nocy (bez nocnego zużycia) i pomijał ładowanie;
    # teraz uwzględnia zużycie nocne w obu przypadkach, a wyższy próg falownika podnosi cel ładowania (45% zamiast 35%)
    check("noc: bez progu falownika też ładuje (zużycie nocne), a wyższy próg → wyższy cel", kwh[None] > 0 and kwh[25] > kwh[None], kwh)
    hass, c, sched = await mk((2026,11,2,21), 80, shutdown=25)
    P = (await sched.suggest())["proposals"]["start_grid_charge"]
    check("noc: wysoki SOC 80% -> pomiń", P["skip"], P["reason"])

    # --- ładowanie dzienne 13–15
    hass, c, sched = await mk((2026,11,3,10), 30, shutdown=25)
    out = (await sched.suggest())["proposals"]
    m1, m2 = out["start_grid_charge_2"], out["stop_grid_charge_2"]
    print("   południe:", m1["proposed"], m2["proposed"], "|", m1["reason"][:260])
    check("dzień: wt 10:00 SOC 30% próg 25% -> propozycja 13–15 (zestaw 2)", (not m1["skip"]) and m2["proposed"] == "15:00" and m1["proposed"] in ("13:00","14:00"), m1["reason"])
    check("dzień: komunikat o wyłączonym zestawie 2", "wyłączony" in m1["reason"])
    hass, c, sched = await mk((2026,11,3,10), 95, shutdown=25)
    m1 = (await sched.suggest())["proposals"]["start_grid_charge_2"]
    check("dzień: wysoki SOC -> pomiń", m1["skip"], m1["reason"])
    hass, c, sched = await mk((2026,11,7,10), 30, shutdown=25)
    m1 = (await sched.suggest())["proposals"]["start_grid_charge_2"]
    check("dzień: sobota -> pomiń (całą dobę tanio)", m1["skip"] and "całą dobę" in m1["reason"], m1["reason"])
    hass, c, sched = await mk((2026,11,3,14,30), 30, shutdown=25)
    m1 = (await sched.suggest())["proposals"]["start_grid_charge_2"]
    check("dzień: 14:30 -> pomiń (okno się kończy)", m1["skip"], m1["reason"])
    hass, c, sched = await mk((2026,11,3,13,10), 30, shutdown=25)
    m1 = (await sched.suggest())["proposals"]["start_grid_charge_2"]
    check("dzień: 13:10 -> start od 14:00", (not m1["skip"]) and m1["proposed"] == "14:00", m1)
    hass, c, sched = await mk((2026,11,3,10), 30, shutdown=25, prices=(1.0, 0.95))
    m1 = (await sched.suggest())["proposals"]["start_grid_charge_2"]
    check("dzień: mała różnica cen -> pomiń", m1["skip"], m1["reason"])
    hass, c, sched = await mk((2026,11,3,10), 30, shutdown=25)
    hass.states.set("switch.bms_ladowanie_z_sieci_2", "on")
    m1 = (await sched.suggest())["proposals"]["start_grid_charge_2"]
    check("dzień: zestaw 2 włączony -> bez ostrzeżenia", (not m1["skip"]) and "wyłączony" not in m1["reason"], m1["reason"])

    # --- sprzedaż uwzględnia próg
    hass, c, sched = await mk((2026,11,3,16), 60, shutdown=40)
    P = (await sched.suggest())["proposals"]["bateria_sprzedaz_start_2"]
    print("   sprzedaż próg 40:", "SKIP" if P["skip"] else P["proposed"], "|", P["reason"][:160])

    # --- tariff helper
    w = tar.next_offpeak_window(stubs.CLOCK["now"].replace(hour=10, minute=5))
    check("taryfa: wt 10:05 -> najbliższe tanie okno 13–15", w and w[0].hour == 13 and w[1].hour == 15 and not w[2], w)
    w = tar.next_offpeak_window(stubs.CLOCK["now"].replace(hour=14, minute=5))
    check("taryfa: wt 14:05 -> trwa teraz do 15", w and w[2] and w[1].hour == 15, w)
    w = tar.next_offpeak_window(stubs.CLOCK["now"].replace(hour=16))
    check("taryfa: wt 16:00 -> noc 22–06", w and w[0].hour == 22 and w[1].hour == 6, w)
    print(f"PASS={PASS} FAIL={FAIL}")
asyncio.run(main())
