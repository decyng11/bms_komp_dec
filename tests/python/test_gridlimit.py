"""Ochrona przyłącza: limit poboru z sieci i moc ładowania z sieci (sterowanie prądem ładowania Deye)."""
import asyncio, sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import gridlimit as GL

# ---------- czysta decyzja
D = GL.plan_decision
V = 50.0
a, why = D(60, None, 60, 12500, 5000, 11.0, V)        # 12,5 kW przy limicie 11 → redukcja o (1,5+0,3) kW / 50 V = 36 A
check("pobór ponad limit i ładowanie: redukcja prądu", why == "reduce" and abs(a - 24) < 0.6, (a, why))
a, why = D(60, None, 60, 12500, 0, 11.0, V)
check("ponad limit, ale bateria się nie ładuje: nic nie da (cannot)", why == "cannot" and a == 60)
a, why = D(10, None, 60, 12500, 5000, 11.0, V)
check("redukcja nie schodzi poniżej minimum", a >= GL.MIN_A and (a == 10 or why in ("reduce", "cannot")), (a, why))
a, why = D(5, None, 60, 12500, 5000, 11.0, V)
check("już na minimum i nadal ponad limit: cannot", why == "cannot" and a == 5)
a, why = D(20, None, 60, 6000, 4000, 11.0, V)         # zapas 5 kW → przywracamy (5−0,5)/50 V = 90 A do sufitu 60
check("duży zapas: przywracamy do wartości sprzed redukcji", why == "restore" and a == 60, (a, why))
a, why = D(20, None, 60, 10400, 4000, 11.0, V)        # zapas 0,6 kW < 1 kW → trzymamy
check("mały zapas: bez zmian (histereza)", why == "hold" and a == 20, (a, why))
a, why = D(60, 30.0, 60, 3000, 0, 0.0, V)             # brak limitu, sufit 30 A, prąd 60 → sufit
check("sam sufit mocy: prąd ściągany do sufitu", why == "ceiling" and a == 30)
a, why = D(30, 30.0, 60, 3000, 0, 0.0, V)
check("sam sufit: gdy zgodny, bez zmian", why == "hold")
a, why = D(60, 30.0, 60, 9000, 3000, 11.0, V)
check("sufit mocy ogranicza też przywracanie", a <= 30.0, a)
check("nigdy powyżej sufitu przy redukcji", D(60, 30.0, 60, 12000, 5000, 11.0, V)[0] <= 30.0)

# ---------- tick na atrapie
class _Log:
    def __init__(s): s.rows = []
    def add(s, k, m, l="info"): s.rows.append((k, m, l))
class _Notif:
    def __init__(s): s.sent = []
    async def send(s, kind, title, msg, **kw): s.sent.append(kind); return True
class _Mon:
    def __init__(s): s.notifier = _Notif()
class _Coord:
    def __init__(s): s.data = {"battery_power": 4000.0}; s.v = 50.0
    def get_float_opt(s, key): return s.v
class _RT:
    def __init__(s, hass):
        s.hass = hass; s.cfg = {}; s.state = {}; s.log = _Log(); s.coordinator = _Coord(); s.monitor = _Mon()
        s.calls = []; s._lock = asyncio.Lock(); s.p = 12000.0
    def brand(s): return "deye"
    def battery_sign(s): return {"sign": 1}
    def grid_power(s): return s.p
    def _save_state(s): pass
    async def _call(s, d, eid, v):
        s.calls.append((d, eid, v)); s.hass.states.set(eid, str(v), {"max": 100})

def mk(limit, cap, cur=60.0):
    h = stubs.FakeHass()
    h.states.set("select.inverter_work_mode", "Zero Export To CT", {"options": ["Selling First", "Zero Export To CT"]})
    h.states.set("number.inverter_battery_grid_charging_current", str(cur), {"max": 100})
    h.states.set("number.bms_grid_import_limit_kw", str(limit), {})
    h.states.set("number.bms_grid_charge_power_kw", str(cap), {})
    return h

class _Now:
    def __init__(s, t): s.t = t
    def timestamp(s): return s.t

async def main():
    # brand Deye = stała z modułu brands
    from custom_components.bms_komp_dec import brands
    h = mk(11.0, 0.0)
    rt = _RT(h); rt.brand = lambda: brands.DEYE
    lim = GL.GridLimiter(rt)
    await lim.tick(_Now(1000.0))
    check("tick: pobór 12 kW > limit 11 → zapis mniejszego prądu", rt.calls and rt.calls[0][1].endswith("battery_grid_charging_current") and rt.calls[0][2] < 60, rt.calls)
    check("tick: wpis w dzienniku", any("Ochrona przyłącza" in m for _k, m, _l in rt.log.rows), rt.log.rows)
    n = len(rt.calls)
    await lim.tick(_Now(1005.0))
    check("tick: zapisy nie częściej niż co 20 s", len(rt.calls) == n)
    rt.p = 3000.0
    await lim.tick(_Now(1030.0))
    check("tick: po spadku poboru prąd wraca do wartości sprzed redukcji (60 A)", rt.calls[-1][2] == 60, rt.calls)
    # wyłączone = zero zapisów
    h2 = mk(0.0, 0.0); rt2 = _RT(h2); rt2.brand = lambda: brands.DEYE
    await GL.GridLimiter(rt2).tick(_Now(2000.0))
    check("limit 0 i moc 0: EMS niczego nie zapisuje", rt2.calls == [])
    # sama moc ładowania 3 kW przy 50 V = 60 A; ustawiamy 1,5 kW = 30 A
    h3 = mk(0.0, 1.5, cur=60.0); rt3 = _RT(h3); rt3.brand = lambda: brands.DEYE
    await GL.GridLimiter(rt3).tick(_Now(3000.0))
    check("moc 1,5 kW przy 50 V → 30 A", rt3.calls and rt3.calls[0][2] == 30, rt3.calls)
    # inny falownik niż Deye: nie ruszamy
    h4 = mk(11.0, 0.0); rt4 = _RT(h4); rt4.brand = lambda: "sofar_hybrid"
    await GL.GridLimiter(rt4).tick(_Now(4000.0))
    check("nie-Deye: bez zapisu", rt4.calls == [])
    # brak encji prądu: komunikat raz, bez błędu
    h5 = stubs.FakeHass(); h5.states.set("number.bms_grid_import_limit_kw", "11", {}); rt5 = _RT(h5); rt5.brand = lambda: brands.DEYE
    lm5 = GL.GridLimiter(rt5); await lm5.tick(_Now(5000.0)); await lm5.tick(_Now(5040.0))
    check("brak encji prądu: jedno ostrzeżenie w dzienniku", len([1 for r in rt5.log.rows if "Battery Grid Charging Current" in r[1]]) == 1 and rt5.calls == [])
    # użytkownik zmienia prąd ręcznie → nowy punkt odniesienia
    h6 = mk(11.0, 0.0, cur=40.0); rt6 = _RT(h6); rt6.brand = lambda: brands.DEYE; rt6.p = 3000.0
    lm6 = GL.GridLimiter(rt6); await lm6.tick(_Now(6000.0))
    check("brak redukcji i brak zapisów, gdy pobór jest pod limitem", rt6.calls == [])
    # wyłączenie ochrony po redukcji przywraca prąd sprzed redukcji
    h7 = mk(11.0, 0.0, cur=60.0); rt7 = _RT(h7); rt7.brand = lambda: brands.DEYE
    lm7 = GL.GridLimiter(rt7); await lm7.tick(_Now(7000.0))
    reduced = rt7.calls[-1][2]
    h7.states.set("number.bms_grid_import_limit_kw", "0", {})
    await lm7.tick(_Now(7100.0))
    check("wyłączenie ochrony przywraca 60 A", reduced < 60 and rt7.calls[-1][2] == 60 and rt7.state.get("grid_limit") == {}, (reduced, rt7.calls))
    await lm7.tick(_Now(7200.0))
    check("po przywróceniu nic więcej nie jest zapisywane", len(rt7.calls) == 2)
    # plan: sufit mocy obniża max_chg_kw
    from custom_components.bms_komp_dec import scheduler as SCH
    opt = SCH.ScheduleOptimizer.__new__(SCH.ScheduleOptimizer)
    opt.hass = mk(0.0, 2.0); opt._cfg_num = lambda k, d: 6000.0
    check("plan: sufit 2 kW obniża moc ładowania z 6 do 2 kW", abs(opt._grid_chg_kw() - 2.0) < 1e-9)
    opt.hass = mk(0.0, 0.0)
    check("plan: bez sufitu zostaje moc z konfiguracji", abs(opt._grid_chg_kw() - 6.0) < 1e-9)

    print(f"GRIDLIMIT PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)
asyncio.run(main())
