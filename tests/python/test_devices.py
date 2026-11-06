"""0.8.1: urządzenia — konfiguracja, całkowanie kWh (W / licznik), koszt, źródła, czuwanie, cykle, nietypowa praca,
podpowiedzi, plan dla elastycznych, nierozpoznany odbiornik, prognoza z podziałem; poprawka podwójnej temperatury."""
import asyncio, sys, types
from common import *   # noqa
import common
from custom_components.bms_komp_dec import devices as DV, notify_cfg as N, load_forecast as LF
from homeassistant.exceptions import HomeAssistantError

def pn(h, nid=None): return [c for c in h.services.calls if c[0] == "persistent_notification" and c[1] == "create" and (nid is None or c[2].get("notification_id") == nid)]
def S_(h, eid, v, unit): h.states.set(eid, v, {"unit_of_measurement": unit})
def tick(dm, t, house=None, price=0.8):
    return dm.update(t, house or {"load_power": 1000, "pv_power": 0, "grid_power": 1000}, price)

async def main():
    # ---------- 1. konfiguracja
    raw = [{"name": "Pralka", "category": "washer", "power_eid": "sensor.pralka_moc"},
           {"name": "Zły", "category": "xxx", "power_eid": "light.lampa", "energy_eid": "sensor.ok_e"},
           {"name": "Bez encji", "category": "fridge"},
           {"id": "BAD ID!", "name": "<b>x</b>" * 20, "category": "ev", "energy_eid": "sensor.ev_e", "cycle_w": 1e9, "max_run_h": -5}]
    lst = DV.sanitize_list(raw)
    check("bez encji → pominięte", len(lst) == 3, len(lst))
    check("domyślne kategorii (pralka: cykle, elastyczna, próg 10 W)", lst[0]["cycles"] and lst[0]["flexible"] and lst[0]["cycle_w"] == 10 and lst[0]["notify_cycle"])
    check("nieznana kategoria → inne; zła encja (light.) odrzucona", lst[1]["category"] == "other" and lst[1]["power_eid"] == "" and lst[1]["energy_eid"] == "sensor.ok_e")
    check("zły id → nowy; nazwa ≤ 40; liczby przycięte", lst[2]["id"] != "BAD ID!" and len(lst[2]["name"]) <= 40 and lst[2]["cycle_w"] == 20000 and lst[2]["max_run_h"] == 0)
    check("powtórzone id rozdzielone", len({d["id"] for d in DV.sanitize_list([{"id": "a", "power_eid": "sensor.x"}, {"id": "a", "power_eid": "sensor.y"}])}) == 2)
    check("limit 40 urządzeń", len(DV.sanitize_list([{"power_eid": f"sensor.x{i}"} for i in range(60)])) == DV.MAX_DEVICES)
    check("katalog: ≥ 30 kategorii w 9 grupach", len(DV.CATEGORIES) >= 30 and all(c[0] in DV.GROUPS for c in DV.CATEGORIES.values()))

    # ---------- 2. całkowanie
    hass = stubs.FakeHass(); dm = DV.DeviceManager(hass)
    dm.set_devices([{"id": "p", "name": "Pralka", "category": "washer", "power_eid": "sensor.p"},
                    {"id": "e", "name": "Bojler", "category": "boiler", "energy_eid": "sensor.e"},
                    {"id": "k", "name": "Auto", "category": "ev", "power_eid": "sensor.k"}])
    S_(hass, "sensor.p", 1000, "W"); S_(hass, "sensor.e", 100.0, "kWh"); S_(hass, "sensor.k", 2.0, "kW")
    t0 = at(2026, 11, 5, 12, 0)
    for i in range(361):
        if i % 36 == 0:
            S_(hass, "sensor.e", 100.0 + 0.2 * (i // 36), "kWh")
        tick(dm, t0 + timedelta(seconds=10 * i))
    d = "2026-11-05"
    check("sama moc 1000 W przez 1 h → 1 kWh", abs(dm.data["p"]["daily"][d] - 1.0) < 0.01, dm.data["p"]["daily"])
    check("moc w kW przeliczona (2 kW × 1 h = 2 kWh)", abs(dm.data["k"]["daily"][d] - 2.0) < 0.02, dm.data["k"]["daily"])
    check("licznik kWh: przyrosty (2,0 kWh)", abs(dm.data["e"]["daily"][d] - 2.0) < 1e-6, dm.data["e"]["daily"])
    check("godzina 12 w profilu godzinowym", abs(dm.data["p"]["hourly"][d][12] - 1.0) < 0.01)
    check("koszt = kWh × cena (0,80)", abs(dm.data["p"]["cost"][d] - 0.8) < 0.01, dm.data["p"]["cost"])
    S_(hass, "sensor.e", 0.3, "kWh"); tick(dm, t0 + timedelta(hours=1, seconds=20))
    check("wyzerowany licznik dzienny → przyrost = nowa wartość", abs(dm.data["e"]["daily"][d] - 2.3) < 1e-6, dm.data["e"]["daily"])
    S_(hass, "sensor.e", 500.0, "kWh"); tick(dm, t0 + timedelta(hours=1, seconds=30))
    check("skok > 20 kWh odrzucony (błąd odczytu)", abs(dm.data["e"]["daily"][d] - 2.3) < 1e-6)
    S_(hass, "sensor.e", 500500.0, "Wh"); tick(dm, t0 + timedelta(hours=1, seconds=40))
    check("licznik w Wh przeliczony (500 500 Wh = +0,5 kWh)", abs(dm.data["e"]["daily"][d] - 2.8) < 1e-6, dm.data["e"]["daily"][d])
    before = dm.data["p"]["daily"][d]; tick(dm, t0 + timedelta(hours=3))
    check("przerwa > 2 min w odczytach nie jest całkowana", abs(dm.data["p"]["daily"][d] - before) < 1e-9)
    hass.states.set("sensor.p", "unavailable"); b2 = dm.data["p"]["daily"][d]; tick(dm, t0 + timedelta(hours=3, seconds=10))
    check("niedostępna encja: bez przyrostu", dm.data["p"]["daily"][d] == b2)
    # źródła
    check("źródła: PV pokrywa całość", DV.DeviceManager._shares({"load_power": 1000, "pv_power": 2500, "grid_power": -1500}) == (1.0, 0.0, 0.0))
    sh = DV.DeviceManager._shares({"load_power": 1000, "pv_power": 0, "grid_power": 500})
    check("źródła: 50% sieć, 50% bateria", abs(sh[2] - 0.5) < 1e-9 and abs(sh[1] - 0.5) < 1e-9, sh)
    check("źródła: brak poboru → sieć (bez dzielenia przez zero)", DV.DeviceManager._shares({"load_power": 0}) == (0.0, 0.0, 1.0))

    # ---------- 3. czuwanie, cykle, nietypowa praca
    hass = stubs.FakeHass(); dm = DV.DeviceManager(hass)
    dm.set_devices([{"id": "w", "name": "Pralka", "category": "washer", "power_eid": "sensor.w"},
                    {"id": "f", "name": "Lodówka", "category": "fridge", "power_eid": "sensor.f"}])
    t = at(2026, 11, 5, 2, 0)
    for i, p in enumerate([3.0, 1.5, 2.0]):
        S_(hass, "sensor.w", p, "W"); tick(dm, t + timedelta(seconds=10 * i))
    check("czuwanie: najniższa moc w nocy (1,5 W)", dm.data["w"]["standby"]["2026-11-05"] == 1.5)
    S_(hass, "sensor.w", 0.0, "W"); tick(dm, at(2026, 11, 5, 14, 0))
    check("czuwanie liczone tylko 1:00–5:00", dm.data["w"]["standby"]["2026-11-05"] == 1.5)
    ev_all = []
    t = at(2026, 11, 5, 10, 0)
    S_(hass, "sensor.w", 2000, "W")
    for i in range(361):
        ev_all += tick(dm, t + timedelta(seconds=10 * i))
    S_(hass, "sensor.w", 1.0, "W")
    for i in range(1, 80):
        ev_all += tick(dm, t + timedelta(hours=1, seconds=10 * i))
    cyc = [e for e in ev_all if e["type"] == "cycle"]
    check("koniec cyklu po 10 min poniżej progu", len(cyc) == 1 and 59 <= cyc[0]["cycle"]["min"] <= 61 and abs(cyc[0]["cycle"]["kwh"] - 2.0) < 0.05, cyc and cyc[0]["cycle"])
    check("cykl zapisany z kosztem i mocą szczytową", dm.data["w"]["cycles"][-1]["peak_w"] == 2000 and dm.data["w"]["cycles"][-1]["cost"] is not None)
    S_(hass, "sensor.w", 2000, "W"); ev2 = []
    for i in range(6):
        ev2 += tick(dm, at(2026, 11, 5, 15, 0, i * 10))
    S_(hass, "sensor.w", 0, "W")
    for i in range(1, 80):
        ev2 += tick(dm, at(2026, 11, 5, 15, 1) + timedelta(seconds=10 * i))
    check("krótki skok (< 3 min) to nie cykl", not [e for e in ev2 if e["type"] == "cycle"])
    # przerwa krótsza niż „koniec cyklu” (np. namaczanie) nie dzieli cyklu
    ev5 = []; tt = at(2026, 11, 5, 17, 0)
    for i, p in enumerate([2000] * 180 + [1] * 30 + [2000] * 180 + [1] * 80):
        S_(hass, "sensor.w", p, "W"); ev5 += tick(dm, tt + timedelta(seconds=10 * i))
    c5 = [e for e in ev5 if e["type"] == "cycle"]
    check("przerwa 5 min w środku cyklu nie dzieli go (jeden cykl ~65 min)", len(c5) == 1 and 64 <= c5[0]["cycle"]["min"] <= 66, [e["cycle"]["min"] for e in c5])
    S_(hass, "sensor.f", 80, "W"); ev3 = []
    for i in range(0, 4 * 360 + 10):
        ev3 += tick(dm, at(2026, 11, 5, 16, 0) + timedelta(seconds=10 * i))
    an = [e for e in ev3 if e["type"] == "anomaly"]
    check("lodówka: ciągła praca > 3 h → jedno ostrzeżenie", len(an) == 1 and an[0]["hours"] > 3)
    # sam licznik kWh odświeżany co 5 min: moc z okna 5 min, cykl nie kończy się między odczytami
    hass7 = stubs.FakeHass(); dm7 = DV.DeviceManager(hass7)
    dm7.set_devices([{"id": "z", "name": "Zmywarka", "category": "dishwasher", "energy_eid": "sensor.z"}])
    ev7 = []; tz = at(2026, 11, 5, 19, 0); e_ = 10.0
    for i in range(0, 6 * 120):                      # 2 h, licznik +0,1 kWh co 5 min przez 1 h (1,2 kW), potem stoi
        if i % 30 == 0 and i < 360:
            e_ += 0.1
        S_(hass7, "sensor.z", round(e_, 3), "kWh"); ev7 += tick(dm7, tz + timedelta(seconds=10 * i))
    c7 = [x for x in ev7 if x["type"] == "cycle"]
    check("licznik co 5 min: jeden cykl ok. 1 h, bez fałszywych końców", len(c7) == 1 and 50 <= c7[0]["cycle"]["min"] <= 70 and abs(c7[0]["cycle"]["kwh"] - 1.1) < 0.15, [x["cycle"] for x in c7])

    # ---------- 4. podsumowanie
    hass = stubs.FakeHass(); dm = DV.DeviceManager(hass)
    dm.set_devices([{"id": "b", "name": "Bojler", "category": "boiler", "power_eid": "sensor.b"}])
    at(2026, 11, 5, 20, 0)
    rec = dm.data["b"]
    for i in range(30):
        k = (date(2026, 11, 5) - timedelta(days=i)).isoformat()
        rec["daily"][k] = 3.0; rec["cost"][k] = 3.0; rec["standby"][k] = 2.0; rec["src"][k] = [1.5, 0.0, 1.5]
        dm.price_min[k] = 0.5
    house = {(date(2026, 11, 5) - timedelta(days=i)).isoformat(): 12.0 for i in range(31)}
    sm = dm.summary(house)[0]
    check("podsumowanie: 30 dni, % domu, śr. cena", sm["kwh_30d"] == 90.0 and sm["share_house_30d"] == 25.0 and sm["avg_price"] == 1.0, sm)
    check("czuwanie 2 W → ok. 18 zł/rok przy 1 zł/kWh", sm["standby_w"] == 2.0 and sm["standby_cost_year"] == 18.0, sm)
    check("źródła 50% PV / 50% sieć", sm["src_pct"] == [50, 0, 50])
    check("oszczędność (elastyczne): (1,0 − 0,5) × 90 kWh = 45 zł", sm["saving_30d"] == 45.0, sm["saving_30d"])
    check("duże urządzenie (≥ 15% domu)", [d["id"] for d in dm.big_devices(house)] == ["b"])

    # ---------- 5. plan dla elastycznych
    rec["cycles"] = [{"start": "x", "min": 60, "kwh": 2.0, "peak_w": 2000, "cost": 2.0}] * 5
    curve = {"start": "2026-11-05T21:00:00+01:00", "hours": 24,
             "pv": [0.0] * 15 + [3.5] * 3 + [0.0] * 6, "load": [0.5] * 24,
             "buy": [1.2] * 5 + [0.6] * 4 + [1.2] * 15, "sell": [0.3] * 24}
    fp = dm.flex_plan(curve)
    check("plan: bojler (3 kWh / 2 kW → 2 h) w nadwyżce PV jutro 12:00", fp and fp[0]["hours"] == 2 and fp[0]["start"].startswith("2026-11-06T12") and fp[0]["why"] == "nadwyżka PV", fp)
    curve2 = dict(curve, pv=[0.0] * 24)
    fp2 = dm.flex_plan(curve2)
    check("plan bez PV: najtańsze godziny (02:00)", fp2 and fp2[0]["start"].startswith("2026-11-06T02") and fp2[0]["why"] == "najtańsze godziny", fp2)
    check("plan: brak krzywej → pusto", dm.flex_plan(None) == [] and dm.flex_plan({"start": "zły"}) == [])

    # ---------- 6. nierozpoznany odbiornik
    prof = [1 / 24] * 24
    spike = [0.6 / 14.0] * 24; spike[18] = 2.8 / 14.0
    s_sum = sum(spike); spike = [x / s_sum for x in spike]
    profiles, days = {}, {}
    for i in range(1, 8):
        k = (date(2026, 11, 5) - timedelta(days=i)).isoformat()
        profiles[k] = spike if i != 3 else prof; days[k] = 14.0
    u = dm.unknown_load(profiles, days)
    check("nierozpoznany odbiornik ok. 18:00 (6 z 7 dni)", u and u["hour"] == 18 and u["days"] == 6, u)
    for i, k in enumerate(sorted(profiles)):
        profiles[k] = spike if i < 3 else prof
    check("skok tylko w 3 z 7 dni → brak podpowiedzi", dm.unknown_load(profiles, days) is None)
    for k in profiles: profiles[k] = prof
    check("równy profil → brak podpowiedzi", dm.unknown_load(profiles, days) is None)

    # ---------- 7. podpowiedzi „uruchom teraz”
    hass = stubs.FakeHass(); dm = DV.DeviceManager(hass)
    dm.set_devices([{"id": "w", "name": "Pralka", "category": "washer", "power_eid": "sensor.w"},
                    {"id": "f", "name": "Lodówka", "category": "fridge", "power_eid": "sensor.f", "notify_hint": True}])
    exp = {"grid_power": -2000}
    h1 = dm.hints(at(2026, 11, 5, 12, 0), exp, 95, False)
    h2 = dm.hints(at(2026, 11, 5, 12, 5), exp, 95, False)
    h3 = dm.hints(at(2026, 11, 5, 12, 11), exp, 95, False)
    h4 = dm.hints(at(2026, 11, 5, 13, 0), exp, 95, False)
    check("nadwyżka: dopiero po 10 min, tylko elastyczne, raz na dobę", not h1 and not h2 and [e["device"]["id"] for e in h3] == ["w"] and not h4)
    check("przy SOC < 90% bez podpowiedzi", not dm.hints(at(2026, 11, 6, 12, 30), exp, 80, False))
    check("najtańsza godzina (taryfa dynamiczna)", [e["why"] for e in dm.hints(at(2026, 11, 6, 3, 0), {}, 50, True)] == ["cheap"])

    # ---------- 8. prognoza z podziałem (atrapa modelu: średnia z 7 dni przed datą)
    class FakeLF:
        def __init__(self): self.days = {}; self.temperatures = {}
        def _model_core(self, target, today):
            cut = min(target, today)
            vals = [v for k, v in self.days.items() if date.fromisoformat(k) < cut][-7:]
            return sum(vals) / len(vals) if len(vals) >= 5 else None
    hass = stubs.FakeHass(); dm = DV.DeviceManager(hass)
    dm.set_devices([{"id": "hp", "name": "Pompa ciepła", "category": "heat_pump", "energy_eid": "sensor.hp"}])
    lf = FakeLF(); today = date(2026, 11, 20); at(2026, 11, 20, 12, 0)
    for i in range(1, 41):
        dd = today - timedelta(days=i); k = dd.isoformat()
        temp = 10.0 - (i % 10)            # 1–10 °C
        hp = 0.8 * (18 - temp)            # pompa: 0,8 kWh na stopniodzień
        lf.temperatures[k] = temp; lf.days[k] = 6.0 + hp; dm.data["hp"]["daily"][k] = hp
    lf.temperatures[(today + timedelta(days=1)).isoformat()] = 0.0
    lf.temperatures[today.isoformat()] = 5.0
    r = DV.forecast_split(dm, lf, today + timedelta(days=1), today)
    check("podział: reszta domu ~6 + pompa ~14,4 przy 0 °C", r and abs(r["residual"] - 6.0) < 0.3 and abs(r["parts"][0]["kwh"] - 14.4) < 0.3, r)
    check("podział używany, gdy dokładniejszy na ostatnich dniach", r["use"] and r["mae_split"] < r["mae_total"], r)
    check("prognoza z podziałem buforowana", DV.forecast_split(dm, lf, today + timedelta(days=1), today) is r)
    dm.state.pop("split_cache", None)
    keep = {(today - timedelta(days=i)).isoformat() for i in range(1, 11)}
    for k in [k for k in dm.data["hp"]["daily"] if k not in keep]: dm.data["hp"]["daily"].pop(k)
    r2 = DV.forecast_split(dm, lf, today + timedelta(days=1), today)
    check("za mało dni danych urządzenia → bez podziału", r2 and not r2["use"] and "za mało danych" in r2["reason"], r2)
    check("model domu nietknięty po liczeniu podziału", len(lf.days) == 40)
    dm2 = DV.DeviceManager(hass)
    check("bez urządzeń → None", DV.forecast_split(dm2, lf, today, today) is None)
    # urządzenie stałe (nic nie tłumaczy) → podział nie jest dokładniejszy → nie używany
    dm6 = DV.DeviceManager(hass); dm6.set_devices([{"id": "c", "name": "Serwer", "category": "server", "energy_eid": "sensor.c"}])
    for k in lf.days: dm6.data["c"]["daily"][k] = 3.0
    r6 = DV.forecast_split(dm6, lf, today + timedelta(days=1), today)
    check("podział nie lepszy → nie używany", r6 and r6["use"] is False and r6["mae_split"] is not None, r6)

    # ---------- 9. poprawka temperatury bez podwójnego liczenia
    hass = stubs.FakeHass()
    f = LF.LoadForecaster(hass, lambda: None)
    f.hdd_coef = 0.05
    tgt = date(2026, 11, 6)
    for i in range(1, 21):
        k = (tgt - timedelta(days=i)).isoformat(); f.days[k] = 8.0; f.temperatures[k] = 3.0
    f.temperatures[tgt.isoformat()] = 3.0
    v = f._model_core(tgt, tgt)
    check("zimno już w historii: prognoza = historia (8,0), nie 8 × 1,75", abs(v - 8.0) < 0.05, v)
    f.temperatures[tgt.isoformat()] = -7.0
    v2 = f._model_core(tgt, tgt)
    check("dzień chłodniejszy niż historia → więcej (8 × 2,25/1,75)", abs(v2 - 8.0 * 2.25 / 1.75) < 0.05, v2)
    f.temperatures = {tgt.isoformat(): 3.0}
    check("brak temperatur historii → bez poprawki", abs(f._model_core(tgt, tgt) - 8.0) < 0.05)
    f.temperatures = {}; f.seasonal_factors = {10: 0.8, 11: 1.2, 12: 1.4}
    t26 = date(2026, 11, 26); f.days = {(t26 - timedelta(days=i)).isoformat(): 8.0 for i in range(1, 21)}
    v3 = f._model_core(t26, t26)
    check("sezon: ten sam miesiąc co historia → bez zmiany (dawniej × 1,1)", abs(v3 - 8.0) < 0.01, v3)
    v4 = f._model_core(date(2026, 12, 1), t26)
    check("sezon: grudzień po listopadowej historii → więcej (1,2/1,1)", abs(v4 - 8.0 * 1.2 / 1.1) < 0.01, v4)

    # ---------- 10. runtime: zdarzenia, plan wieczorem, zanik sieci, usługi
    hass, c, opt, rt = build()
    c.config["notify_service"] = "notify.mobile_app_tel"; hass.states.set("switch.bms_notifications_enabled", "on")
    rt.devices.set_devices([{"id": "w", "name": "Pralka", "category": "washer", "power_eid": "sensor.w"}])
    d0 = rt.devices.devices[0]
    await rt._device_event({"type": "cycle", "device": d0, "cycle": {"start": "s", "min": 62, "kwh": 0.85, "cost": 0.68}})
    cy = pn(hass, "bms_device_cycle")
    check("powiadomienie: koniec cyklu z kWh i kosztem (przecinki)", cy and "0,85 kWh" in cy[0][2]["message"] and "0,68 zł" in cy[0][2]["message"] and "62 min" in cy[0][2]["message"], cy)
    d0["notify_cycle"] = False; hass.services.calls.clear()
    await rt._device_event({"type": "cycle", "device": d0, "cycle": {"start": "s2", "min": 62, "kwh": 0.85, "cost": 0.68}})
    check("wyłączone przy urządzeniu → brak", not pn(hass, "bms_device_cycle"))
    rt.state["grid_outage"] = {"notified": True}
    c.data["load_power"] = 3000.0
    hass.states.set("sensor.w", "2500", {"unit_of_measurement": "W"})
    await rt._devices_tick(at(2026, 11, 5, 9, 0))
    check("zanik sieci, pobór 3 kW < próg 5 kW → bez powiadomienia", not pn(hass, "bms_island_overload"))
    c.data["load_power"] = 6500.0
    hass.states.set("sensor.w", "2500", {"unit_of_measurement": "W"})
    await rt._devices_tick(at(2026, 11, 5, 10, 0))
    io = pn(hass, "bms_island_overload")
    check("zanik sieci + pobór 6,5 kW > 5 kW → lista urządzeń", io and "Pralka 2.5 kW" in io[0][2]["message"], io)
    rt._plan = {"curve": curve}
    rt.devices.data["w"]["cycles"] = [{"start": "x", "min": 60, "kwh": 2.0, "peak_w": 2000, "cost": 2.0}] * 5
    for i in range(1, 15):
        rt.devices.data["w"]["daily"][(date(2026, 11, 5) - timedelta(days=i)).isoformat()] = 2.0
    setcfg = lambda kinds: rt.state.__setitem__("notify_cfg", N.effective({"kinds": kinds}))
    await rt._devices_tick(at(2026, 11, 5, 20, 5)); await rt._devices_tick(at(2026, 11, 5, 20, 6))
    pl = pn(hass, "bms_device_plan")
    check("plan wieczorem raz na dobę", len(pl) == 1 and "Pralka" in pl[0][2]["message"], pl)
    # usługi
    hass.auth = types.SimpleNamespace(async_get_user=None)
    async def gu(uid): return types.SimpleNamespace(is_admin=(uid == "admin"))
    hass.auth.async_get_user = gu
    common.pkg._register_services(hass)
    common.pkg._get_runtime = lambda h: rt
    H = {n: h for (dd, n), (h, _r) in hass.services.handlers.items() if dd == "bms_komp_dec"}
    call = lambda data, uid="admin": types.SimpleNamespace(data=data, context=types.SimpleNamespace(user_id=uid))
    r = await H["devices_get"](call({"history": True}, uid="user"))
    check("odczyt dla każdego użytkownika (z historią)", r["devices"][0]["id"] == "w" and "history" in r and len(r["categories"]) == len(DV.CATEGORIES))
    r = await H["devices_get"](call({}))
    check("bez history — mniejsza odpowiedź", "history" not in r)
    try:
        await H["devices_set"](call({"devices": []}, uid="user")); denied = False
    except Exception as e_: denied = "Unauthorized" in type(e_).__name__
    check("zapis tylko administrator", denied)
    r = await H["devices_set"](call({"devices": [{"name": "A", "power_eid": "sensor.a"}, {"name": "zły"}]}))
    check("zapis: poprawne zapisane, bez encji pominięte (dropped)", len(r["devices"]) == 1 and r["dropped"] == 1)
    check("dane usuniętego urządzenia skasowane", "w" not in rt.devices.data)
    try:
        await H["devices_set"](call({"devices": "x"})); bad = False
    except HomeAssistantError: bad = True
    check("zły format → błąd", bad)
    # sensor
    from custom_components.bms_komp_dec import sensor as SE
    s_ = SE.BmsRuntimeSensor(c, "devices", "BMS Urządzenia", None, "mdi:power-plug")
    hass.states.set("sensor.a", "150", {"unit_of_measurement": "W"})
    check("sensor urządzeń: liczba i moc łączna", s_.native_value == 1 and s_.extra_state_attributes["power_total"] == 150.0)
    # zapis i odczyt magazynu
    dm3 = DV.DeviceManager(hass); dm3.set_devices([{"id": "z", "name": "Z", "power_eid": "sensor.z"}]); dm3.data["z"]["daily"]["2026-11-05"] = 1.5
    payload = dm3._payload()
    dm4 = DV.DeviceManager(hass)
    async def fake_load(): return payload
    dm4._store.async_load = fake_load
    await dm4.async_load()
    check("magazyn: urządzenia i dane po restarcie", dm4.devices[0]["id"] == "z" and dm4.data["z"]["daily"]["2026-11-05"] == 1.5)
    async def junk(): return {"devices": "x", "data": [1, 2], "price_min": None}
    dm5 = DV.DeviceManager(hass); dm5._store.async_load = junk; await dm5.async_load()
    check("magazyn ze śmieciami → pusto, bez wyjątku", dm5.devices == [])

    print(f"DEVICES PASS={common.PASS} FAIL={common.FAIL}")
    sys.exit(1 if common.FAIL else 0)
asyncio.run(main())
