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
