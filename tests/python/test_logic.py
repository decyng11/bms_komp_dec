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

async def main():
    # ---------- sprzedaż: start + stop (jednorazowo, przełącznik się wyłącza)
    hass, c, opt, rt = build()
    S = hass.states
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("time.bms_bateria_sprzedaz_stop", "20:00:00")
    S.set("switch.bms_bateria_sprzedaz_1", "on")
    now = at(2026, 10, 28, 17, 0, 0)
    res = await rt.process_rules(now)
    check("start fired", any(r.get("fired") for r in res["results"]), res)
    check("start: Export First", S.get("select.inverter_work_mode").state == "Export First")
    check("start: 6000", float(S.get("number.inverter_export_surplus_power").state) == 6000)
    check("switch nadal on po starcie", S.get("switch.bms_bateria_sprzedaz_1").state == "on")
    # drugi tick w 30 s – bez dublowania
    n_before = len(hass.services.calls)
    await rt.process_rules(at(2026, 10, 28, 17, 0, 30))
    check("brak dubla w 90 s", len(hass.services.calls) == n_before)
    await settle(hass)
    now = at(2026, 10, 28, 20, 0, 0)
    res = await rt.process_rules(now)
    check("stop: Zero Export", S.get("select.inverter_work_mode").state == "Zero Export To Load")
    check("stop wyłącza przełącznik (jednorazowy)", S.get("switch.bms_bateria_sprzedaz_1").state == "off")
    await settle(hass)
    check("log weryfikacji ok", any(e["kind"] == "verify" and e["level"] == "ok" for e in rt.log.entries))

    # ---------- tryb cykliczny: przełącznik zostaje
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("time.bms_bateria_sprzedaz_stop", "20:00:00")
    S.set("switch.bms_bateria_sprzedaz_1", "on"); S.set("switch.bms_recurring_schedule", "on")
    await rt.process_rules(at(2026, 10, 28, 17, 0, 0))
    await rt.process_rules(at(2026, 10, 28, 20, 0, 0))
    check("cykliczny: przełącznik zostaje on", S.get("switch.bms_bateria_sprzedaz_1").state == "on")
    await settle(hass)

    # ---------- dni tygodnia
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("time.bms_bateria_sprzedaz_stop", "20:00:00")
    S.set("switch.bms_bateria_sprzedaz_1", "on"); S.set("switch.bms_dzien_sr", "off")   # 2026-10-28 = środa
    res = await rt.process_rules(at(2026, 10, 28, 17, 0, 0))
    check("środa wyłączona: start pominięty", not res["results"] and S.get("select.inverter_work_mode").state == "Zero Export To Load")
    check("środa: wpis w dzienniku", any("harmonogram wyłączony" in e["msg"] for e in rt.log.entries))
    # stop mimo wyłączonego dnia – jeśli start był (symulacja)
    rt.fired["bateria_sprzedaz_start"] = now = at(2026, 10, 28, 16, 59)
    S.set("select.inverter_work_mode", "Export First")
    await rt.process_rules(at(2026, 10, 28, 20, 0, 0))
    check("stop działa mimo wyłączonego dnia", S.get("select.inverter_work_mode").state == "Zero Export To Load")
    await settle(hass)

    # ---------- święta jak niedziela
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("switch.bms_bateria_sprzedaz_1", "on")
    S.set("switch.bms_dzien_nd", "off")      # niedziela wyłączona
    res = await rt.process_rules(at(2026, 11, 11, 17, 0, 0))   # środa 11.11 – Święto Niepodległości
    check("święto = niedziela -> pominięte", not res["results"])
    S.set("switch.bms_holidays_as_sunday", "off")
    res = await rt.process_rules(at(2026, 11, 11, 17, 0, 30))
    check("święto bez reguły -> środa aktywna", any(r.get("fired") for r in res["results"]), res)
    await settle(hass)

    # ---------- zakazy sprzedaży
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("switch.bms_bateria_sprzedaz_1", "on")
    S.set(c.config["grid_power"], 3000)
    res = await rt.process_rules(at(2026, 10, 28, 17, 0, 0))
    check("import > limit blokuje start", not res["results"] and S.get("select.inverter_work_mode").state != "Export First")
    S.set(c.config["grid_power"], "unavailable")
    c.data["grid_power"] = None
    res = await rt.process_rules(at(2026, 10, 28, 17, 0, 30))
    check("nieznana moc sieci blokuje start (scheduler)", not res["results"])
    S.set(c.config["grid_power"], -100); c.data["grid_power"] = -100
    c.data["energy_battery_charge_today"] = 12.0; c.data["energy_pv_today"] = 3.0
    res = await rt.process_rules(at(2026, 10, 28, 17, 1, 0)) # inna minuta – nie dopasuje czasu
    S.set("time.bms_bateria_sprzedaz_start", "17:02:00")
    res = await rt.process_rules(at(2026, 10, 28, 17, 2, 0))
    check("arbitraż blokuje start", not res["results"] and rt.arbitrage_status()[0])
    # ręczny przycisk też blokuje
    try:
        await rt.run_command("sprzedaz_6000w", source="ręcznie"); ok = False
    except stubs.HomeAssistantError: ok = True
    check("ręczny przycisk: zakaz arbitrażu", ok)
    # ręczny przycisk przy nieznanej sieci – dozwolony (jak oryginał)
    c.data["energy_battery_charge_today"] = 1.0; c.data["energy_pv_today"] = 10.0
    S.set(c.config["grid_power"], "unavailable"); c.data["grid_power"] = None
    await rt.run_command("sprzedaz_6000w", source="ręcznie")
    check("ręczny przycisk: brak sieci nie blokuje", S.get("select.inverter_work_mode").state == "Export First")
    await settle(hass)

    # ---------- opłacalność
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("switch.bms_bateria_sprzedaz_1", "on")
    S.set("switch.bms_profit_check", "on"); S.set("sensor.rce_pse_cena", 0.20); opt.ref = 0.30
    res = await rt.process_rules(at(2026, 10, 28, 17, 0, 0))
    check("nieopłacalna sprzedaż pominięta", not res["results"] and rt.profit_status()["ok"] is False)
    S.set("sensor.rce_pse_cena", 700)        # PLN/MWh -> 0.70
    rt._profit_ref = None
    ps = rt.profit_status()
    check("opłacalność w PLN/MWh", ps["ok"] is True and abs(ps["net"] - (0.7*0.9-0.3)) < 1e-9, ps)
    res = await rt.process_rules(at(2026, 10, 28, 17, 0, 30))
    check("opłacalna sprzedaż startuje", any(r.get("fired") for r in res["results"]), res)
    S.set("sensor.rce_pse_cena", -0.05); rt._profit_ref = None
    check("cena ujemna = nieopłacalne", rt.profit_status()["ok"] is False)
    await settle(hass)

    # ---------- reakcja na ceny
    hass, c, opt, rt = build(); S = hass.states
    S.set("switch.bms_negative_price_reaction", "on")
    S.set("select.inverter_work_mode", "Export First")
    S.set("sensor.rce_pse_cena", -0.10)
    await rt.price_reaction_tick(at(2026, 10, 28, 12))
    check("ujemna cena: eksport wstrzymany", S.get("select.inverter_work_mode").state == "Zero Export To Load" and rt.state["price_reaction"]["active"])
    check("prev_mode zapamiętany", rt.state["price_reaction"]["prev_mode"] == "Export First")
    S.set("sensor.rce_pse_cena", 0.01)       # w histerezie (< 0+0.02) – bez wznowienia
    await rt.price_reaction_tick(at(2026, 10, 28, 12, 1))
    check("histereza: jeszcze aktywne", rt.state["price_reaction"]["active"])
    S.set("sensor.rce_pse_cena", 0.30)
    await rt.price_reaction_tick(at(2026, 10, 28, 12, 2))
    check("cena wróciła: sprzedaż wznowiona", S.get("select.inverter_work_mode").state == "Export First" and not rt.state["price_reaction"]["active"])
    await settle(hass)
    # stop z harmonogramu w czasie ograniczenia kasuje prev_mode
    hass, c, opt, rt = build(); S = hass.states
    S.set("switch.bms_negative_price_reaction", "on"); S.set("select.inverter_work_mode", "Export First")
    S.set("sensor.rce_pse_cena", -0.10)
    S.set("time.bms_bateria_sprzedaz_stop", "13:00:00"); S.set("switch.bms_bateria_sprzedaz_1", "on")
    await rt.price_reaction_tick(at(2026, 10, 28, 12))
    rt.fired["bateria_sprzedaz_start"] = at(2026, 10, 28, 11)
    await rt.process_rules(at(2026, 10, 28, 13, 0, 0))
    check("stop harmonogramu czyści prev_mode", rt.state["price_reaction"]["prev_mode"] is None)
    S.set("sensor.rce_pse_cena", 0.30)
    await rt.price_reaction_tick(at(2026, 10, 28, 13, 5))
    check("po stopie nie wznawiamy sprzedaży", S.get("select.inverter_work_mode").state == "Zero Export To Load")
    await settle(hass)

    # ---------- zabezpieczenia w trakcie sprzedaży
    hass, c, opt, rt = build(); S = hass.states
    S.set("select.inverter_work_mode", "Export First"); S.set(c.config["soc"], 15)
    await rt.enforce_guard(at(2026, 10, 28, 18))
    check("guard: SOC < min -> stop sprzedaży", S.get("select.inverter_work_mode").state == "Zero Export To Load")
    S.set("select.inverter_work_mode", "Export First")
    n_before = len(hass.services.calls)
    await rt.enforce_guard(at(2026, 10, 28, 18, 0, 30))
    check("guard: cooldown", len(hass.services.calls) == n_before)
    await rt.enforce_guard(at(2026, 10, 28, 18, 3, 0))
    check("guard: po cooldownie działa", S.get("select.inverter_work_mode").state == "Zero Export To Load")
    # odblokowanie ładowania przy niskim SOC
    S.set("number.inverter_battery_max_charging_current", 0); S.set(c.config["soc"], 3)
    await rt.enforce_guard(at(2026, 10, 28, 19))
    check("guard: odblokowanie ładowania < min_soc_for_pv_export_stop", float(S.get("number.inverter_battery_max_charging_current").state) == 170)
    await settle(hass)

    # ---------- dynamiczna rezerwa w trakcie
    hass, c, opt, rt = build(); S = hass.states
    opt.pv = [0.0]*24
    for h in range(8, 17): opt.pv[h] = 2.0
    c.data["load_forecast"] = {"hourly_forecast": [0.5]*24}
    S.set("switch.bms_dynamic_reserve", "on")
    at(2026, 10, 28, 17)
    check("próg sprzedaży = rezerwa", abs(rt.sell_soc_threshold() - 85.0) < 0.5, rt.sell_soc_threshold())
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("switch.bms_bateria_sprzedaz_1", "on")
    res = await rt.process_rules(at(2026, 10, 28, 17, 0, 0))
    check("SOC 80 < rezerwa 85 -> pominięte", not res["results"])
    S.set(c.config["soc"], 90); rt._reserve_cache = None
    res = await rt.process_rules(at(2026, 10, 28, 17, 0, 30))
    check("SOC 90 >= rezerwa -> start", any(r.get("fired") for r in res["results"]), res)
    await settle(hass)

    # ---------- weryfikacja: ponowienie i błąd
    hass, c, opt, rt = build(); S = hass.states
    hass.services.ignore.add("number.inverter_export_surplus_power")      # falownik nie przyjmuje
    await rt.run_command("sprzedaz_6000w", source="test", enforce_guard=False)
    await settle(hass)
    errs = [e for e in rt.log.entries if e["kind"] == "verify" and e["level"] == "error"]
    warns = [e for e in rt.log.entries if e["kind"] == "verify" and e["level"] == "warn"]
    check("weryfikacja: ponowienie + błąd", len(errs) == 1 and len(warns) == 1, [e["msg"] for e in rt.log.entries])
    retry_calls = [c_ for c_ in hass.services.calls if c_[2].get("entity_id") == "number.inverter_export_surplus_power"]
    check("weryfikacja: dokładnie 1 ponowienie", len(retry_calls) == 2)
    # nowsza komenda unieważnia starą weryfikację
    hass, c, opt, rt = build(); S = hass.states
    rtm.VERIFY_FIRST_WAIT_S = 0.05
    await rt.run_command("sprzedaz_6000w", source="a", enforce_guard=False)
    await rt.run_command("nadwyzka_9700w", source="b")
    await settle(hass)
    check("stara weryfikacja przerwana (gen)", not any(e["kind"] == "verify" and e["level"] in ("warn", "error") for e in rt.log.entries))
    rtm.VERIFY_FIRST_WAIT_S = 0
    # number z max < wartość – nie jest błędem
    hass, c, opt, rt = build(); S = hass.states
    S.set("number.inverter_export_surplus_power", 5000, {"max": 6000})
    hass.services.ignore.add("number.inverter_export_surplus_power")
    S.set("number.inverter_export_surplus_power", 9000, {"max": 9000})
    bad = rt._mismatches([("number", "number.inverter_export_surplus_power", 9700)])
    check("clamp do max nie jest rozbieżnością", not bad)

    # ---------- snapshot dobowy
    hass, c, opt, rt = build()
    rt.update_daily_snapshot(at(2026, 10, 28, 12))
    c.data["energy_battery_charge_today"] = 4.0; c.data["energy_pv_today"] = 20.0
    rt.update_daily_snapshot(at(2026, 10, 28, 23, 59))
    c.data["energy_battery_charge_today"] = 0.1; c.data["energy_pv_today"] = 0.0     # reset licznika po północy
    rt.update_daily_snapshot(at(2026, 10, 29, 0, 0, 30))
    check("snapshot wczoraj", rt.state["yesterday_charge"] == 4.0 and rt.state["yesterday_pv"] == 20.0 and rt.state["yesterday_date"] == "2026-10-28", rt.state)
    cc, pp = rt.charge_2d()
    check("bilans 2-dniowy", abs(cc - 4.1) < 1e-9 and abs(pp - 20.0) < 1e-9, (cc, pp))
    at(2026, 10, 31, 12)
    cc, pp = rt.charge_2d()
    check("stary snapshot ignorowany", abs(cc - 0.1) < 1e-9 and abs(pp - 0.0) < 1e-9)

    # ---------- test_schedule dry-run nie wykonuje komend
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("switch.bms_bateria_sprzedaz_1", "on")
    res = await rt.process_rules(at(2026, 10, 28, 17, 0, 0), dry_run=True)
    check("dry-run bez komend", res["results"] and res["results"][0]["dry_run"] and not hass.services.calls)

    # ---------- automatyczne stosowanie
    hass, c, opt, rt = build(); S = hass.states
    S.set("time.bms_bateria_sprzedaz_start", "17:00:00"); S.set("time.bms_bateria_sprzedaz_stop", "19:00:00")
    S.set("time.bms_start_grid_charge", "22:00:00"); S.set("time.bms_stop_grid_charge", "04:00:00")
    S.set("switch.bms_auto_apply", "on")
    result = {"proposals": {
        "bateria_sprzedaz_start": {"proposed": "18:00", "current": "17:00", "confidence": "high", "skip": False},
        "bateria_sprzedaz_stop": {"proposed": "20:00", "current": "19:00", "confidence": "high", "skip": False},
        "start_grid_charge": {"proposed": "23:00", "current": "22:00", "confidence": "medium", "skip": False},
        "stop_grid_charge": {"proposed": "05:00", "current": "04:00", "confidence": "medium", "skip": False},
        "pv_export_start": {"proposed": "10:00", "current": "—", "confidence": "low", "skip": False},
    }}
    out = await automation.async_auto_apply(rt, hass, result)
    check("auto: para sprzedaży zastosowana", out["applied"].get("bateria_sprzedaz_start") == "18:00" and out["applied"].get("bateria_sprzedaz_stop") == "20:00", out)
    check("auto: ładowanie przez północ dozwolone", out["applied"].get("start_grid_charge") == "23:00" and out["applied"].get("stop_grid_charge") == "05:00", out)
    check("auto: niska pewność pominięta", "pv_export_start" not in out["applied"])
    check("auto: stan zapisany do cofnięcia", rt.state["last_applied"]["bateria_sprzedaz_start"] == "17:00")
    check("auto: czas w encji", S.get("time.bms_bateria_sprzedaz_start").state == "18:00:00")
    undo = await automation.async_undo_auto_apply(rt, hass)
    check("cofnięcie", S.get("time.bms_bateria_sprzedaz_start").state == "17:00:00" and undo["applied"] == 4, undo)
    # limit przesunięcia
    S.set("number.bms_auto_apply_max_shift_h", 1)
    result2 = {"proposals": {"bateria_sprzedaz_start": {"proposed": "18:30", "current": "17:00", "confidence": "high", "skip": False}}}
    out = await automation.async_auto_apply(rt, hass, result2)
    check("auto: limit przesunięcia", not out["applied"] and any("przesunięcie" in s for s in out["skipped"]), out)
    # zajęty system
    S.set("select.inverter_work_mode", "Export First")
    out = await automation.async_auto_apply(rt, hass, result)
    check("auto: wstrzymane gdy trwa sprzedaż", not out["applied"] and any("trwa sprzedaż" in s for s in out["skipped"]))
    # walidacja apply_times
    applied, skipped = await automation.apply_times(hass, {"nie_ma": "10:00", "pv_export_start": "25:00", "pv_export_stop": "10:30"})
    check("apply_times walidacja", applied == 1 and len(skipped) == 2, skipped)

    # ---------- load_forecast: akumulator przeżywa restart
    hass = stubs.FakeHass()
    lf = lfm.LoadForecaster(hass, lambda: "sensor.x")
    lf._hourly_sample_date = date(2026, 10, 28); lf._hourly_accum = [0.1]*24
    lf._schedule_save()
    saved = lf._store._store.func()
    check("forecast: akumulator zapisany", saved["hourly_accum"]["date"] == "2026-10-28" and len(saved["hourly_accum"]["values"]) == 24)
    lf2 = lfm.LoadForecaster(hass, lambda: "sensor.x")
    lf2._load_from_storage(saved)
    check("forecast: akumulator odtworzony", lf2._hourly_sample_date == date(2026, 10, 28) and abs(sum(lf2._hourly_accum) - 2.4) < 1e-9)
    # rollover zapisuje profil z odtworzonego akumulatora
    lf2.days["2026-10-28"] = 2.4
    at(2026, 10, 29, 0, 0, 10)
    hass.states.set("sensor.bms_load_power", 500)
    lf2._loaded = True
    lf2._sample_hourly_power(stubs.CLOCK["now"])
    check("forecast: profil zapisany po restarcie", "2026-10-28" in lf2.profiles, lf2.profiles.keys())

    # ---------- load_forecast: prognoza „wydana” zamrożona, tempo dnia osobno
    hass = stubs.FakeHass()
    lf3 = lfm.LoadForecaster(hass, lambda: "sensor.x")
    lf3._loaded = True
    at(2026, 11, 1, 21, 0, 0)
    for i in range(1, 15):
        lf3.days[(date(2026, 11, 1) - timedelta(days=i)).isoformat()] = 10.0
    lf3.days["2026-11-01"] = 5.0
    lf3.forecast_history["2026-11-01"] = 9.6
    d1 = lf3.as_dict()["days"]
    today_item = [x for x in d1 if x["label"] == "Dziś"][0]
    check("forecast: Dziś = prognoza wydana (9.6), nie mieszana", today_item["forecast"] == 9.6 and today_item["forecast_source"] == "issued", today_item)
    check("forecast: tempo dnia osobno i niższe", isinstance(today_item.get("nowcast"), float) and today_item["nowcast"] < 9.0, today_item)
    at(2026, 11, 2, 1, 0, 0)
    d2 = lf3.as_dict()["days"]
    wcz = [x for x in d2 if x["label"] == "Wczoraj"][0]
    check("forecast: Wczoraj = ta sama liczba co Dziś przed północą", wcz["forecast"] == 9.6 and "nowcast" not in wcz, wcz)
    h14 = lf3.as_dict()["history_14d"]
    check("forecast: history_14d ma 14 dni z flagą święta", len(h14) == 14 and any(x["holiday"] for x in h14 if x["date"] == "2026-11-01"), h14[0])
    lf3.forecast_history.pop("2026-11-02", None)
    dz = [x for x in lf3.as_dict()["days"] if x["label"] == "Dziś"][0]
    check("forecast: brak wpisu -> model bez korekty na żywo", dz["forecast_source"] == "model" and isinstance(dz["forecast"], float), dz)

    # ---------- load_forecast: typ dnia, szybka reakcja, samokorekta
    from custom_components.bms_komp_dec import holidays_pl as _hp
    hass = stubs.FakeHass()
    lf4 = lfm.LoadForecaster(hass, lambda: "sensor.x")
    lf4._loaded = True
    at(2026, 11, 2, 1, 0, 0)
    today4 = date(2026, 11, 2)
    for i in range(1, 46):
        d = today4 - timedelta(days=i)
        lf4.days[d.isoformat()] = 5.0 if (d.weekday() >= 5 or d in _hp.polish_holidays(d.year)) else 10.0
    p_sat = lf4.predict(date(2026, 11, 7), today4)
    p_tue = lf4.predict(date(2026, 11, 3), today4)
    p_hol = lf4.predict(date(2026, 11, 11), today4)   # środa, Święto Niepodległości
    check("forecast: sobota ≈ dzień wolny (5)", abs(p_sat - 5.0) < 0.6, p_sat)
    check("forecast: wtorek ≈ dzień roboczy (10)", abs(p_tue - 10.0) < 0.6, p_tue)
    check("forecast: święto w środku tygodnia liczone jak dzień wolny", abs(p_hol - 5.0) < 0.8, p_hol)
    # szybka reakcja: dwa ostatnie dni wolne wyraźnie niższe niż wcześniej
    lf5 = lfm.LoadForecaster(hass, lambda: "sensor.x"); lf5._loaded = True
    for i in range(1, 46):
        d = today4 - timedelta(days=i)
        off = d.weekday() >= 5 or d in _hp.polish_holidays(d.year)
        lf5.days[d.isoformat()] = (10.0 if off else 10.0)
    lf5.days["2026-10-31"] = 5.0; lf5.days["2026-11-01"] = 5.0
    p_fast = lf5.predict(date(2026, 11, 7), today4)
    check("forecast: po dwóch niskich dniach wolnych prognoza spada wyraźnie", p_fast < 8.0, p_fast)
    # samokorekta obciążenia
    lf6 = lfm.LoadForecaster(hass, lambda: "sensor.x"); lf6._loaded = True
    lf6._model_core = lambda t, td: 10.0
    for i in range(1, 15):
        lf6.days[(today4 - timedelta(days=i)).isoformat()] = 7.5
    check("forecast: korekta obciążenia 0.875", abs(lf6._bias_factor(today4) - 0.875) < 1e-3, lf6._bias_factor(today4))
    check("forecast: jutro skorygowane, wstecz bez korekty", lf6.predict(date(2026, 11, 3), today4) == 8.75 and lf6.predict(date(2026, 11, 1), today4) == 10.0)
    lf6.days.update({(today4 - timedelta(days=i)).isoformat(): 3.0 for i in range(1, 15)})
    check("forecast: korekta ograniczona do 0.75", abs(lf6._bias_factor(today4) - 0.75) < 1e-3, lf6._bias_factor(today4))
    lf7 = lfm.LoadForecaster(hass, lambda: "sensor.x"); lf7._loaded = True
    lf7._model_core = lambda t, td: 10.0
    for i in range(1, 4):
        lf7.days[(today4 - timedelta(days=i)).isoformat()] = 5.0
    check("forecast: za mało próbek — brak korekty", lf7._bias_factor(today4) == 1.0)

    # ---------- scheduler.suggest smoke
    hass, c, opt0, rt = build(); S = hass.states
    cfg = dict(const.SCHEDULER_DEFAULTS)
    c.load_forecast = types.SimpleNamespace(predict=lambda a, b: 8.0)
    sched = scheduler.ScheduleOptimizer(hass, c, cfg)
    at(2026, 10, 28, 16)
    rce = [{"start": f"2026-10-28T{h:02d}:00:00+01:00", "rce_pln": 400 + (300 if 17 <= h < 20 else 0) + (200 if 7 <= h < 10 else 0)} for h in range(24)]
    S.set("sensor.rce_pse_cena", 0.6, {"prices": rce})
    S.set("sensor.solcast_pv_forecast_forecast_today", 20, {})
    S.set("sensor.solcast_pv_forecast_forecast_tomorrow", 5, {})
    S.set(c.config["soc"], 80)
    out = await sched.suggest()
    props = out["proposals"]
    check("suggest: zwraca propozycje", "bateria_sprzedaz_start_2" in props, out.get("error"))
    p2 = props["bateria_sprzedaz_start_2"]
    check("suggest: okno wieczorne 17–20", p2["proposed"] and p2["proposed"].startswith("17") or p2["skip"], p2)
    S.set(c.config["soc"], "unknown")
    out = await sched.suggest()
    check("suggest: SOC nieznany -> błąd, nie 0%", "error" in out and out["proposals"] == {})
    S.set(c.config["soc"], 80)
    S.set("switch.bms_profit_check", "on"); S.set("sensor.rce_pse_cena", 0.6, {"prices": [{"start": f"2026-10-28T{h:02d}:00:00+01:00", "rce_pln": 100} for h in range(24)]})
    out = await sched.suggest()
    check("suggest: opłacalność odrzuca okna", all(out["proposals"][k]["skip"] for k in ("bateria_sprzedaz_start", "bateria_sprzedaz_start_2")), {k: out["proposals"][k]["reason"] for k in ("bateria_sprzedaz_start", "bateria_sprzedaz_start_2")})


    # ---------- harmonogram: scenariusze
    def mk(soc=40, now=(2026, 10, 28, 16), pvt=None, pvtm=None, price=None, price_tm=None, load=8.0, **nums):
        hass, c, opt0, rt = build(); S = hass.states
        for k, v in nums.items(): S.set(f"number.bms_{k}", v)
        c.data = {"load_forecast": {"tomorrow_forecast": load}, "energy_battery_charge_today": 0.0, "energy_pv_today": 20.0}
        sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS))
        at(*now)
        d0, d1 = date(*now[:3]), date(*now[:3]) + timedelta(days=1)
        def arr(d, f): return [{"start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "rce_pln": f(h)} for h in range(24)]
        S.set("sensor.rce_pse_cena", 0.6, {"prices": arr(d0, price or (lambda h: 300)) + arr(d1, price_tm or (lambda h: 300))})
        def solc(d, f): return {"detailedHourly": [{"period_start": f"{d.isoformat()}T{h:02d}:00:00+01:00", "pv_estimate": f(h)} for h in range(24)]}
        S.set("sensor.solcast_pv_forecast_forecast_today", 20, solc(d0, pvt or (lambda h: 3.0 if 9 <= h < 15 else 0.0)))
        S.set("sensor.solcast_pv_forecast_forecast_tomorrow", 18, solc(d1, pvtm or (lambda h: 3.0 if 9 <= h < 15 else 0.0)))
        S.set(c.config["soc"], soc)
        return hass, c, sched, rt
    def hm(x): return int(x[:2]) * 60 + int(x[3:5])

    # 1) niski SOC wieczorem -> ładowanie nocne kończy się 06:00, nie w przeszłości, bez 00:00
    hass, c, sched, rt = mk(soc=30)
    out = await sched.suggest(); P = out["proposals"]
    gs, ge = P["start_grid_charge"], P["stop_grid_charge"]
    check("harm: ładowanie zaproponowane", not gs["skip"] and gs["proposed"] and ge["proposed"] == "06:00", (gs, ge))
    check("harm: start nie 00:00", gs["proposed"] != "00:00")
    check("harm: zestaw 2 ładowania pominięty", P["start_grid_charge_2"]["skip"])
    # 2) wysoki SOC -> brak ładowania
    hass, c, sched, rt = mk(soc=95)
    P = (await sched.suggest())["proposals"]
    check("harm: pełna bateria -> bez ładowania z sieci", P["start_grid_charge"]["skip"], P["start_grid_charge"])
    # 3) sprzedaż wieczorna: okno w przyszłości, w szczycie, najdroższe
    hass, c, sched, rt = mk(soc=90, now=(2026, 10, 28, 16), load=2.0, price=lambda h: 300 + (400 if 18 <= h < 21 else 0))
    P = (await sched.suggest())["proposals"]
    s2, e2 = P["bateria_sprzedaz_start_2"], P["bateria_sprzedaz_stop_2"]
    check("harm: okno wieczorne w przyszłości i w szczycie", not s2["skip"] and 17 <= int(s2["proposed"][:2]) and hm(e2["proposed"]) <= 22 * 60 and hm(s2["proposed"]) >= 17 * 60, (s2, e2))
    check("harm: okno obejmuje najdroższe godziny", 18 <= int(s2["proposed"][:2]) < 21, s2)
    # 4) po godz. 22 -> okno wieczorne na jutro, nie w przeszłości
    hass, c, sched, rt = mk(soc=90, now=(2026, 10, 28, 23), price_tm=lambda h: 300 + (400 if 18 <= h < 21 else 0))
    P = (await sched.suggest())["proposals"]
    check("harm: po 22 propozycja dotyczy jutra", P["bateria_sprzedaz_start_2"]["skip"] or "jutro" in P["bateria_sprzedaz_start_2"]["reason"], P["bateria_sprzedaz_start_2"])
    P = (await sched.suggest())["proposals"]
    check("harm: ceny jutra z atrybutów encji 'dziś'", "brak cen RCE" not in P["bateria_sprzedaz_start"]["reason"], P["bateria_sprzedaz_start"])
    # 5) niski SOC -> sprzedaż pominięta (poniżej progu)
    hass, c, sched, rt = mk(soc=35, price=lambda h: 300 + (400 if 18 <= h < 21 else 0))
    P = (await sched.suggest())["proposals"]
    check("harm: niski SOC -> bez sprzedaży", P["bateria_sprzedaz_start_2"]["skip"], P["bateria_sprzedaz_start_2"])
    # 6) bilans 2-dniowy już zablokowany -> sprzedaż pominięta
    hass, c, sched, rt = mk(soc=90, price=lambda h: 300 + (400 if 18 <= h < 21 else 0))
    c.data["energy_battery_charge_today"] = 12.0; c.data["energy_pv_today"] = 5.0
    P = (await sched.suggest())["proposals"]
    check("harm: arbitraż blokuje sprzedaż", P["bateria_sprzedaz_start_2"]["skip"] and "bilans" in P["bateria_sprzedaz_start_2"]["reason"].lower(), P["bateria_sprzedaz_start_2"])
    # 7) płaskie ceny -> brak sprzedaży i brak blokady PV
    hass, c, sched, rt = mk(soc=90)
    P = (await sched.suggest())["proposals"]
    check("harm: płaskie ceny -> sprzedaż pominięta", P["bateria_sprzedaz_start_2"]["skip"], P["bateria_sprzedaz_start_2"])
    check("harm: płaskie ceny -> blokada PV pominięta", P["pv_export_start"]["skip"], P["pv_export_start"])
    # 8) blokada PV: drogie godziny w środku dnia, dużo PV później
    pvt = lambda h: 4.0 if 9 <= h < 17 else 0.0
    hass, c, sched, rt = mk(soc=60, now=(2026, 10, 28, 6), pvt=pvt, price=lambda h: 200 + (500 if 10 <= h < 12 else 0))
    P = (await sched.suggest())["proposals"]
    ps = P["pv_export_start"]
    check("harm: blokada PV w drogich godzinach", not ps["skip"] and ps["proposed"] == "10:00" and P["pv_export_stop"]["proposed"] == "12:00", (ps, P["pv_export_stop"]))
    # 9) blokada PV pominięta, gdy po niej brak nadwyżki na dopełnienie baterii
    pvt2 = lambda h: 4.0 if 10 <= h < 12 else (0.3 if 12 <= h < 16 else 0.0)
    hass, c, sched, rt = mk(soc=40, now=(2026, 10, 28, 6), pvt=pvt2, price=lambda h: 200 + (500 if 10 <= h < 12 else 0))
    P = (await sched.suggest())["proposals"]
    check("harm: blokada PV pominięta bez nadwyżki", P["pv_export_start"]["skip"], P["pv_export_start"])
    # 9b) sprzedaż nie może zostawić domu bez energii do świtu (zużycie 8 kWh/dobę, bateria 10 kWh)
    hass, c, sched, rt = mk(soc=90, now=(2026, 10, 28, 16), price=lambda h: 300 + (400 if 18 <= h < 21 else 0))
    P = (await sched.suggest())["proposals"]
    check("harm: noc — sprzedaż pominięta, gdy nie starczy do świtu", P["bateria_sprzedaz_start_2"]["skip"] and "przed świtem" in P["bateria_sprzedaz_start_2"]["reason"], P["bateria_sprzedaz_start_2"]["reason"])
    # 9c) propozycja podaje, do kiedy trwa noc
    hass, c, sched, rt = mk(soc=90, now=(2026, 10, 28, 16), load=2.0, price=lambda h: 300 + (400 if 18 <= h < 21 else 0))
    P = (await sched.suggest())["proposals"]
    check("harm: uzasadnienie zawiera świt", "Do świtu" in P["bateria_sprzedaz_start_2"]["reason"], P["bateria_sprzedaz_start_2"]["reason"])
    # 9d) wschód/zachód z HA przycinają prognozę PV (Solcast o świcie/zmierzchu nie liczy się)
    stubs.SUN["rise"], stubs.SUN["set"] = 7.0, 16.0
    hass, c, sched, rt = mk(soc=60, now=(2026, 10, 28, 6), pvt=lambda h: 0.5 if (h in (5, 6, 17, 18) or 9 <= h < 15) else 0.0)
    ctx = sched._build_context(stubs.CLOCK["now"], 60.0)
    check("słońce: PV przed wschodem i po zachodzie = 0", all(ctx["pv"][0][h] == 0.0 for h in (5, 6, 16, 17, 18)), ctx["pv"][0])
    check("słońce: godziny PV mieszczą się między wschodem a zachodem", ctx["pv_act"][0] and min(ctx["pv_act"][0]) >= 7 and max(ctx["pv_act"][0]) <= 15, ctx["pv_act"][0])
    out = await sched.suggest()
    check("słońce: suggest zwraca wschód i zachód", out["sunrise_today"] == "07:00" and out["sunset_today"] == "16:00", (out.get("sunrise_today"), out.get("sunset_today")))
    stubs.SUN["rise"] = stubs.SUN["set"] = None
    # 9e) zimowa prognoza (szczyt 0,9 kWh): godziny PV są rozpoznane, nie „za mało godzin z PV > 1 kWh”
    hass, c, sched, rt = mk(soc=60, now=(2026, 10, 28, 6), pvt=lambda h: 0.9 if h == 12 else (0.5 if 9 <= h < 15 else 0.0), price=lambda h: 200 + (500 if 10 <= h < 12 else 0))
    P = (await sched.suggest())["proposals"]
    check("zima: małe PV nie jest ignorowane", "za mało godzin" not in P["pv_export_start"]["reason"], P["pv_export_start"]["reason"])
    # 9f) cena „jutro” nie może być kopią „dziś” (lista bez znaczników czasu w encji dzisiejszej)
    hass, c, sched, rt = mk(soc=90, now=(2026, 10, 28, 16))
    hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": [{"rce_pln": 300 + (400 if 18 <= h < 21 else 0)} for h in range(24)]})
    arrs = sched._read_rce_arrays()
    check("RCE: brak znaczników czasu -> dziś jest, jutro nie jest kopią", len(arrs) == 1 and "2026-10-28" in arrs, list(arrs))
    hass.states.set("sensor.rce_pse_cena", 0.6, {"prices": [{"dtime": f"2026-10-28T{h:02d}:00:00+01:00", "rce_pln": 300 + 5 * h} for h in range(24)] + [{"dtime": f"2026-10-29T{h:02d}:00:00+01:00", "rce_pln": 500 - 3 * h} for h in range(24)]})
    arrs = sched._read_rce_arrays()
    check("RCE: klucz dtime obsługiwany, jutro != dziś", len(arrs) == 2 and arrs["2026-10-28"] != arrs["2026-10-29"], list(arrs))
    # 9g) o 05:xx planujemy nadchodzącą noc, nie „po południu”
    hass, c, sched, rt = mk(soc=25, now=(2026, 10, 28, 5), pvt=lambda h: 0.0)
    P = (await sched.suggest())["proposals"]
    check("harm: o 05:00 propozycja ładowania na nadchodzącą noc", not P["start_grid_charge"]["skip"] and P["start_grid_charge"]["proposed"] is not None and P["stop_grid_charge"]["proposed"] == "06:00", P["start_grid_charge"])
    # 9h) słaby dzień jutro + droga taryfa dzienna -> cel nocnego ładowania obejmuje szczyt
    hass, c, sched, rt = mk(soc=20, now=(2026, 10, 28, 17), pvt=lambda h: 0.0, pvtm=lambda h: 1.0 if 10 <= h < 14 else 0.0, load=10.0)
    sched.tariff.prices["peak"], sched.tariff.prices["off_peak"] = 1.292, 0.676
    P = (await sched.suggest())["proposals"]
    check("harm: słaby dzień -> cel obejmuje szczyt taryfy", "obejmuje też szczyt" in P["start_grid_charge"]["reason"], P["start_grid_charge"]["reason"])
    sched.tariff.prices["peak"] = 0.5
    P = (await sched.suggest())["proposals"]
    check("harm: gdy szczyt nie jest droższy od nocy -> bez dopłaty do szczytu", "obejmuje też szczyt" not in P["start_grid_charge"]["reason"], P["start_grid_charge"]["reason"])
    # 10) wszystkie propozycje: start != stop, godziny w formacie HH:MM
    hass, c, sched, rt = mk(soc=30, price=lambda h: 300 + (400 if 18 <= h < 21 else 0))
    P = (await sched.suggest())["proposals"]
    ok = all(v["skip"] or (v["proposed"] and len(v["proposed"]) == 5) for v in P.values())
    check("harm: format godzin", ok, P)

    # ---------- encje – import i podstawowe właściwości
    hass, c, opt, rt = build()
    bs = binary_sensor.BmsBinarySensor(c, "dzien_swiateczny", "x", "i"); bs.hass = hass
    at(2026, 11, 11, 12)
    check("binary: dzień świąteczny", bs.is_on is True and bs.extra_state_attributes["nazwa"] == "Święto Niepodległości")
    rs = sensor.BmsRuntimeSensor(c, "profit_today", "x", "PLN", "i"); rs.hass = hass
    check("sensor profit_today", rs.native_value == 0.0 and "history" in rs.extra_state_attributes)
    ls = sensor.BmsRuntimeSensor(c, "decision_log", "x", None, "i"); ls.hass = hass
    rt.log.add("system", "x" * 400)
    check("sensor log: stan <= 255", len(ls.native_value) <= 255 and ls.extra_state_attributes["entries"])
    sw = switch.BmsSwitch("dzien_pn", "n", "i", True)
    check("switch default", sw.is_on is True)
    nb = number.BmsNumber("min_sell_margin", "n", 0, 5, 0.01, "PLN/kWh")
    check("number default", abs(nb.native_value - 0.15) < 1e-9)

asyncio.run(main())
print(f"PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
