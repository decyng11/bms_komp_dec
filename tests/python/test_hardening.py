"""Utwardzenie po audycie: bramka administratora na usługach zapisujących, walidacja wejść, naprawa uszkodzonego stanu,
kolizja okien ładowania i sprzedaży w autotestach."""
import asyncio, json, math, sys, types
sys.path.insert(0, ".")
import common
from common import *   # noqa
import custom_components.bms_komp_dec as I
from custom_components.bms_komp_dec import scheduler, const, health as hlt, state_guard as SG, analysis as AN
from custom_components.bms_komp_dec.battery_sign import SignLearner


class U:
    def __init__(self, a): self.is_admin = a


async def main():
    hass, c, opt, rt = build(); S = hass.states
    sched = scheduler.ScheduleOptimizer(hass, c, dict(const.SCHEDULER_DEFAULTS)); rt.optimizer = sched; c.runtime = rt
    hass.data = {I.DOMAIN: {"e1": c, "e1_optimizer": sched}}

    class Auth:
        async def async_get_user(self, uid): return U(uid == "admin") if uid else None
    hass.auth = Auth()
    I._get_runtime = lambda h: rt; I._get_optimizer = lambda h: sched; I._need_runtime = lambda h: rt
    I._register_services(hass)
    H = {n: h for (d, n), (h, _) in hass.services.handlers.items()}
    at(2026, 11, 19, 20, 30)
    call = lambda uid, **d: types.SimpleNamespace(data=d, context=types.SimpleNamespace(user_id=uid))

    async def denied(name, uid="guest", **d):
        try:
            await H[name](call(uid, **d)); return False
        except Exception as e:
            return type(e).__name__ == "Unauthorized"

    # ---- bramka administratora
    for name, d in (("apply_schedule_times", {"times": {"start_grid_charge": "02:00"}}), ("auto_apply_now", {}), ("undo_auto_apply", {}), ("test_schedule", {}),
                    ("inbox_action", {"action": "reject", "key": "start_grid_charge", "proposed": "02:00"})):
        check(f"nie-admin zablokowany: {name} {d.get('action', '')}", await denied(name, **d), name)
    hass.services.calls.clear()
    S.set("time.bms_start_grid_charge", "00:00:00")
    await denied("apply_schedule_times", times={"start_grid_charge": "02:00"})
    check("nie-admin nie zmienił godziny w encji time", S.get("time.bms_start_grid_charge").state == "00:00:00" and not [x for x in hass.services.calls if x[0] == "time"])
    r = await H["apply_schedule_times"](call("admin", times={"start_grid_charge": "02:00"}))
    check("administrator może zapisać godziny", r["applied"] == 1 and S.get("time.bms_start_grid_charge").state == "02:00:00", r)
    r = await H["apply_schedule_times"](call(None, times={"start_grid_charge": "03:00"}))
    check("automatyzacja (bez użytkownika) może zapisać godziny", r["applied"] == 1)
    # odczyty i oznaczanie przeczytanych zostają dla wszystkich
    for name, d in (("get_plan", {"force": True}), ("get_plan", {}), ("suggest_schedule", {}), ("devices_get", {}), ("insights_get", {}), ("analysis_get", {}), ("monthly_report", {}),
                    ("inbox_action", {"action": "read_all"}), ("inbox_action", {"action": "clear"})):
        try:
            await H[name](call("guest", **d)); ok = True
        except Exception as e:
            ok = type(e).__name__ != "Unauthorized"
        check(f"nie-admin nadal może: {name}", ok, name)

    # ---- walidacja wejść
    for y in (float("inf"), float("nan"), "x", [1], 10**30):
        try:
            await H["monthly_report"](call("admin", year=y, month=1)); ok = False
        except Exception as e:
            ok = type(e).__name__ == "HomeAssistantError"
        check(f"monthly_report(year={str(y)[:8]}) → czytelny błąd, nie surowy wyjątek", ok)
    for lim in (float("inf"), float("nan"), "x", [1], -5, 10**12, None, ""):
        try:
            r = await H["settings_log_get"](call("admin", limit=lim)); ok = isinstance(r["items"], list)
        except Exception as e:
            ok = False
        check(f"settings_log_get(limit={str(lim)[:8]}) bez wyjątku", ok)
    r = await H["analysis_set"](call("admin", g11=1e308, dyn_markup=float("inf"), invest_pv=-1, invest_batt=1e12, zone={"peak": 1e300, "off": 1}))
    json.dumps(r, allow_nan=False)
    check("analysis_set odrzuca wartości absurdalne (1e308, inf, ujemne, ponad limit)", not r.get("cfg", r).get("g11") and "dyn_markup" not in r.get("cfg", r) and "zone" not in r.get("cfg", r), r)
    r = await H["analysis_set"](call("admin", g11=1.1, invest_pv=30000))
    check("analysis_set przyjmuje rozsądne wartości", (r.get("cfg") or r).get("g11") == 1.1 and (r.get("cfg") or r).get("invest_pv") == 30000.0, r)

    # ---- naprawa uszkodzonego stanu
    st = {"battery_sign_votes": {"pos": "x", "neg": [1]}, "notified": {"a": [1]}, "watches": "źle", "overrides": [1, {"id": 1}, None], "soc_day": {"date": "2026-11-19", "min": "", "max": 5},
          "today_charge": "abc", "price_reaction": 5, "inbox": [{"kind": ["x"], "ts": 1}, {"kind": "a", "ts": 2, "level": "info"}, 7], "accuracy_fc": {"date": 1},
          "inbox_seq": float("nan"), "low_soc_active": "tak", "control_test": [1], "nieznany": [1, 2]}
    fixed = SG.sanitize(st)
    check("state_guard: zły typ wraca do domyślnego", st["battery_sign_votes"] == {"pos": 0, "neg": 0} and st["notified"] == {} and st["watches"] == [] and st["today_charge"] == 0.0
          and st["price_reaction"] == {"active": False, "prev_mode": None} and st["low_soc_active"] is False and st["control_test"] is None and st["inbox_seq"] == 0, st)
    check("state_guard: z list zostają tylko poprawne wpisy; soc_day/accuracy_fc z błędem są czyszczone", st["overrides"] == [{"id": 1}] and st["inbox"] == [{"kind": "a", "ts": 2, "level": "info"}] and st["soc_day"] == {} and st["accuracy_fc"] == {}, st)
    check("state_guard: nieznane klucze nietknięte, lista naprawionych niepusta", st["nieznany"] == [1, 2] and "watches" in fixed and "battery_sign_votes" in fixed, fixed)
    good = {"today_charge": 1.5, "soc_day": {"date": "2026-11-19", "min": 20.0, "max": 90}, "watches": [{"id": 1}], "price_reaction": {"active": True, "prev_mode": "x"}, "inbox_seq": 4}
    before = json.dumps(good, sort_keys=True)
    check("state_guard: poprawny stan bez zmian", SG.sanitize(good) == [] and json.dumps(good, sort_keys=True) == before)
    for bad in ({"pos": "x"}, {"pos": float("inf")}, {"pos": [1]}, None, 5, {"pos": 10**30}):
        try:
            v = SignLearner(bad).votes; ok = all(isinstance(x, int) and 0 <= x <= 80 for x in v.values())
        except Exception:
            ok = False
        check(f"SignLearner({str(bad)[:14]}) nie rzuca wyjątku", ok)
    # start integracji z uszkodzonym zapisem
    import stubs
    async def _load(self): return {"battery_sign_votes": {"pos": "x"}, "watches": 5, "overrides": [None], "soc_day": {"min": []}} if self.key == "bms_komp_dec_runtime" else None
    old = stubs.Store.async_load; stubs.Store.async_load = _load
    try:
        h2, c2, o2, rt2 = build(); rt2.optimizer = scheduler.ScheduleOptimizer(h2, c2, dict(const.SCHEDULER_DEFAULTS)); c2.runtime = rt2; await rt2.async_load()
        check("start z uszkodzonym zapisem: bez wyjątku, pola naprawione, wpis w dzienniku", rt2.state["watches"] == [] and rt2.state["overrides"] == [] and any("Naprawiono uszkodzony zapis" in e["msg"] for e in rt2.log.entries))
        await rt2.tick(stubs.CLOCK["now"])
    finally:
        stubs.Store.async_load = old

    # ---- kolizja okien
    def setup(times, sw=("bateria_sprzedaz_1", "ladowanie_z_sieci_1"), nums=None):
        h, c_, o, r = build(); s = h.states
        for k, v in times.items(): s.set(f"time.bms_{k}", v)
        for k in ("bateria_sprzedaz_1", "bateria_sprzedaz_2", "ladowanie_z_sieci_1", "ladowanie_z_sieci_2"): s.set(f"switch.bms_{k}", "on" if k in sw else "off")
        for k, v in (nums or {}).items(): s.set(f"number.bms_{k}", v)
        return r
    ch = lambda r: hlt.window_conflict_check(r)
    a = ch(setup(dict(start_grid_charge="22:00:00", stop_grid_charge="06:00:00", bateria_sprzedaz_start="05:00:00", bateria_sprzedaz_stop="08:00:00")))
    check("kolizja: ładowanie 22–06 + sprzedaż 05–08 → błąd z godzinami", a["status"] == "error" and "22:00–06:00" in a["detail"] and "05:00–08:00" in a["detail"], a)
    a = ch(setup(dict(start_grid_charge="01:00:00", stop_grid_charge="05:00:00", bateria_sprzedaz_start="22:00:00", bateria_sprzedaz_stop="02:00:00")))
    check("kolizja: sprzedaż przez północ 22–02 + ładowanie 01–05 → błąd", a["status"] == "error", a)
    a = ch(setup(dict(start_grid_charge="01:00:00", stop_grid_charge="05:00:00", bateria_sprzedaz_start="17:00:00", bateria_sprzedaz_stop="21:00:00")))
    check("bez kolizji (domyślne blokady włączone) → OK", a["status"] == "ok", a)
    a = ch(setup(dict(start_grid_charge="01:00:00", stop_grid_charge="05:00:00", bateria_sprzedaz_start="05:00:00", bateria_sprzedaz_stop="08:00:00")))
    check("styk okien (stop = start) nie jest kolizją", a["status"] == "ok", a)
    a = ch(setup(dict(start_grid_charge="01:00:00", stop_grid_charge="05:00:00", bateria_sprzedaz_start="03:00:00", bateria_sprzedaz_stop="04:00:00"), sw=("ladowanie_z_sieci_1",)))
    check("wyłączony zestaw sprzedaży nie liczy się do kolizji", a["status"] == "ok", a)
    a = ch(setup(dict(start_grid_charge="03:00:00", stop_grid_charge="03:00:00", bateria_sprzedaz_start="03:00:00", bateria_sprzedaz_stop="04:00:00")))
    check("puste okno (start = stop) i 00:00 są ignorowane", a["status"] == "ok", a)
    zero = {"grid_import_sell_block_w": 0, "grid_import_sell_block_kwh": 0, "grid_arbitrage_block_kwh": 0}
    a = ch(setup(dict(start_grid_charge="01:00:00", stop_grid_charge="05:00:00", bateria_sprzedaz_start="17:00:00", bateria_sprzedaz_stop="21:00:00"), nums=zero))
    check("wszystkie blokady sprzedaży = 0 → ostrzeżenie", a["status"] == "warn" and "wyłączone" in a["detail"], a)
    a = ch(setup(dict(start_grid_charge="22:00:00", stop_grid_charge="06:00:00", bateria_sprzedaz_start="05:00:00", bateria_sprzedaz_stop="08:00:00"), nums=zero))
    check("kolizja + blokady wyłączone → błąd z dopiskiem o blokadach", a["status"] == "error" and "blokady" in a["fix"], a)
    r = setup(dict(start_grid_charge="22:00:00", stop_grid_charge="06:00:00", bateria_sprzedaz_start="05:00:00", bateria_sprzedaz_stop="08:00:00"))
    ids = {x["id"]: x for x in hlt.health_check(r)["checks"]}
    check("kreator/autotest zawiera kontrolę kolizji", ids.get("window_conflict", {}).get("status") == "error")
    print(f"HARDENING PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
