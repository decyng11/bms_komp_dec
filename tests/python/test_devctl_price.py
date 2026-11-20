"""Sterowanie urządzeniami: ujemna cena zakupu (tryb „neg” i dodatek do „pv”/„cheap”), godziny z przerwami i termin „gotowe do godziny X”."""
import asyncio, sys
from common import *   # noqa
import common
from custom_components.bms_komp_dec import devices as DV, device_ctl as DC
from custom_components.bms_komp_dec.const import DEFAULT_PRICE_BUY_ENTITY as BUY


def sw_calls(hass, eid="switch.boj"):
    return [c[1] for c in hass.services.calls if c[0] in ("switch", "input_boolean") and c[2].get("entity_id") == eid]


def setup(mode="neg", **kw):
    hass, c, opt, rt = build()
    dev = dict({"id": "boj", "name": "Bojler", "category": "boiler", "power_eid": "sensor.boj_p", "switch_eid": "switch.boj",
                "ctl_mode": mode, "ctl_power_w": 2000, "ctl_soc": 90}, **kw)
    rt.devices.set_devices([dev])
    hass.states.set("switch.boj", "off")
    hass.states.set("sensor.boj_p", 0, {"unit_of_measurement": "W"})
    hass.states.set("switch.bms_device_control", "on")
    hass.states.set(c.config["soc"], 95)
    hass.states.set(BUY, 0.5)
    return hass, c, rt


async def run(rt, t0, minutes, grid=500, hook=None):
    for m in range(minutes):
        t = t0 + timedelta(minutes=m)
        stubs.CLOCK["now"] = t
        rt.coordinator.data = dict(rt.coordinator.data or {}, grid_power=grid(m) if callable(grid) else grid)
        if hook:
            hook(m)
        await rt.dev_ctl.tick(t)


def follow(hass):
    """Przełącznik w HA podąża za naszą ostatnią komendą (jak prawdziwe urządzenie)."""
    def _f(m):
        last = sw_calls(hass)[-1:]
        if last:
            hass.states.set("switch.boj", "on" if last[0] == "turn_on" else "off")
    return _f


async def main():
    # ---------- konfiguracja
    base = {"name": "x", "power_eid": "sensor.a", "switch_eid": "switch.a"}
    d = DV.sanitize_device(dict(base, ctl_mode="neg", ctl_neg_price=99, ctl_ready_h=40, ctl_split=True, ctl_neg=True))
    check("tryb neg dozwolony; próg i termin przycięte", d["ctl_mode"] == "neg" and d["ctl_neg_price"] == 5.0 and d["ctl_ready_h"] == 23, d)
    d = DV.sanitize_device(dict(base, ctl_mode="cheap", ctl_neg_price="abc", ctl_ready_h="x"))
    check("śmieci w polach → wartości domyślne", d["ctl_neg_price"] == 0.0 and d["ctl_ready_h"] == 0 and d["ctl_split"] is False and d["ctl_neg"] is False, d)
    d = DV.sanitize_device({"name": "x", "power_eid": "sensor.a", "ctl_mode": "neg", "ctl_neg": True, "ctl_split": True})
    check("bez przełącznika: tryb wyłączony, dodatki wyłączone", d["ctl_mode"] == "off" and not d["ctl_neg"] and not d["ctl_split"], d)
    d = DV.sanitize_device(dict(base, ctl_mode="pv", ctl_neg_price=float("nan")))
    check("nan w progu → 0", d["ctl_neg_price"] == 0.0)

    # ---------- cena zakupu ze znakiem
    hass, c, rt = setup()
    hass.states.set(BUY, -0.12)
    check("buy_price_signed oddaje ujemną cenę z encji", rt.buy_price_signed() == -0.12, rt.buy_price_signed())
    check("buy_price() nadal odrzuca ujemną (zachowanie sprzed zmiany)", rt.buy_price() != -0.12)
    hass.states.set(BUY, "unavailable")
    check("brak odczytu → cena z taryfy", rt.buy_price_signed() == 0.7, rt.buy_price_signed())
    hass.states.set(BUY, 999)
    check("wartość spoza ±20 → cena z taryfy", rt.buy_price_signed() == 0.7)
    hass.states.set(BUY, "nan")
    check("„nan” → cena z taryfy", rt.buy_price_signed() == 0.7)

    # ---------- tryb „neg”
    hass, c, rt = setup()
    t0 = at(2026, 6, 10, 13, 0)
    hass.states.set(BUY, -0.10)
    await run(rt, t0, 4, hook=follow(hass))
    check("ujemna cena < 5 min → jeszcze nic", sw_calls(hass) == [], sw_calls(hass))
    st = rt.dev_ctl.status()["devices"]["boj"]
    check("powód: potwierdzam", "potwierdzam" in (st.get("reason") or ""), st)
    await run(rt, t0 + timedelta(minutes=4), 3, hook=follow(hass))
    check("ujemna cena ≥ 5 min → włączenie", sw_calls(hass) == ["turn_on"], sw_calls(hass))
    check("powód w dzienniku zawiera cenę", any("cena zakupu -0.10" in e.get("msg", "") for e in rt.log.last(20)), [e.get("msg") for e in rt.log.last(5)])
    hass.states.set(BUY, 0.35)
    await run(rt, t0 + timedelta(minutes=7), 15, hook=follow(hass))
    check("cena wróciła do dodatniej → wyłączenie (po 10 min od ostatniej zmiany)", sw_calls(hass) == ["turn_on", "turn_off"], sw_calls(hass))
    check("powód stanu: czeka na ujemną cenę", "czeka na cenę zakupu" in (rt.dev_ctl.status()["devices"]["boj"].get("reason") or ""))

    # cena dokładnie 0 nie jest ujemna; próg własny
    hass, c, rt = setup()
    hass.states.set(BUY, 0.0)
    await run(rt, at(2026, 6, 10, 13, 0), 8, hook=follow(hass))
    check("cena 0,00 przy progu 0 → bez włączenia", sw_calls(hass) == [])
    hass, c, rt = setup(ctl_neg_price=0.10)
    hass.states.set(BUY, 0.05)
    await run(rt, at(2026, 6, 10, 13, 0), 8, hook=follow(hass))
    check("własny próg 0,10: cena 0,05 → włączenie", sw_calls(hass) == ["turn_on"], sw_calls(hass))

    # krótki skok ceny (błąd odczytu) nie włącza
    hass, c, rt = setup()
    await run(rt, at(2026, 6, 10, 13, 0), 10, hook=lambda m: hass.states.set(BUY, -0.2 if m == 2 else 0.5))
    check("pojedynczy odczyt ujemny (1 min) nie włącza", sw_calls(hass) == [], sw_calls(hass))

    # zanik sieci: nic nie włączamy
    hass, c, rt = setup()
    hass.states.set(BUY, -0.3)
    rt.state["grid_outage"] = {"since": 1.0}
    await run(rt, at(2026, 6, 10, 13, 0), 10, hook=follow(hass))
    check("zanik sieci przy ujemnej cenie → bez włączenia", sw_calls(hass) == [])

    # główny przełącznik wyłączony
    hass, c, rt = setup()
    hass.states.set(BUY, -0.3); hass.states.set("switch.bms_device_control", "off")
    await run(rt, at(2026, 6, 10, 13, 0), 10, hook=follow(hass))
    check("sterowanie wyłączone → bez włączenia", sw_calls(hass) == [])

    # limit pracy na dobę obowiązuje także przy ujemnej cenie
    hass, c, rt = setup(ctl_max_h=0.25)
    hass.states.set(BUY, -0.3)
    await run(rt, at(2026, 6, 10, 13, 0), 40, hook=follow(hass))
    check("limit pracy 15 min → wyłączenie mimo ujemnej ceny", sw_calls(hass) == ["turn_on", "turn_off"], sw_calls(hass))

    # ---------- „neg” jako dodatek do nadwyżki PV
    hass, c, rt = setup(mode="pv", ctl_neg=True)
    hass.states.set(BUY, -0.2)
    await run(rt, at(2026, 6, 10, 13, 0), 8, grid=800, hook=follow(hass))      # import z sieci: brak nadwyżki PV
    check("PV + ujemna cena: włącza mimo braku nadwyżki", sw_calls(hass) == ["turn_on"], sw_calls(hass))
    hass, c, rt = setup(mode="pv")
    hass.states.set(BUY, -0.2)
    await run(rt, at(2026, 6, 10, 13, 0), 8, grid=800, hook=follow(hass))
    check("sam tryb PV (bez dodatku) ignoruje ujemną cenę", sw_calls(hass) == [])
    hass, c, rt = setup(mode="pv", ctl_neg=True)
    hass.states.set(BUY, 0.5)
    await run(rt, at(2026, 6, 10, 12, 0), 8, grid=-3000, hook=follow(hass))
    check("PV + dodatek: zwykła nadwyżka PV nadal działa", sw_calls(hass) == ["turn_on"], sw_calls(hass))

    # ---------- funkcje: godziny z przerwami i termin
    buy = [0.9] * 30
    buy[6] = buy[8] = buy[9] = 0.2             # krzywa od 20:00: 02:00, 04:00, 05:00
    buy[14] = 0.05                              # 10:00 następnego dnia — najtaniej, ale po terminie 07:00
    curve = {"start": "2026-06-10T20:00:00+02:00", "pv": [0.0] * 30, "load": [0.5] * 30, "buy": buy, "sell": [0.3] * 30}
    got = DC.cheapest_slots(curve, 3, 2.0)
    check("cheapest_slots bez terminu (24 h): 02:00, 04:00 i 10:00 następnego dnia", [t.hour for t in got[0]] == [2, 4, 10], got)
    got = DC.cheapest_slots(curve, 3, 2.0, deadline=datetime(2026, 6, 11, 7, 0, tzinfo=TZ))
    check("termin 07:00: godziny 02:00, 04:00, 05:00 (10:00 odpada)", [t.hour for t in got[0]] == [2, 4, 5], got)
    check("koszt = 3 h × 2 kW × 0,2", abs(got[1] - 1.2) < 1e-6, got)
    got = DC.cheapest_slots(curve, 3, 2.0, deadline=datetime(2026, 6, 10, 22, 0, tzinfo=TZ))
    check("termin za wcześnie: tylko dostępne godziny (20:00 i 21:00)", [t.hour for t in got[0]] == [20, 21], got)
    check("termin przed początkiem planu → brak godzin", DC.cheapest_slots(curve, 3, 2.0, deadline=datetime(2026, 6, 10, 20, 0, tzinfo=TZ)) is None)
    check("brak planu → None", DC.cheapest_slots(None, 2, 1.0) is None)
    got = DC.cheapest_slots(curve, 2, 2.0, not_before=datetime(2026, 6, 10, 23, 30, tzinfo=TZ))
    check("not_before: godziny już zakończone odpadają (nieodświeżony plan)", all(t >= datetime(2026, 6, 10, 23, 0, tzinfo=TZ) for t in got[0]), got)
    bw = DC.best_window(curve, 2, 2.0, deadline=datetime(2026, 6, 11, 7, 0, tzinfo=TZ))
    check("best_window z terminem kończy się przed terminem", bw is not None and bw[1] <= datetime(2026, 6, 11, 7, 0, tzinfo=TZ), bw)
    bw2 = DC.best_window(curve, 2, 2.0)
    check("best_window bez terminu — jak dotąd (najtańsze dwie sąsiednie godziny 04:00–06:00)", bw2 is not None and bw2[0].hour == 4, bw2)
    curve2 = dict(curve, buy=[0.9, None] + [0.5] * 28)
    check("brak ceny w godzinie wyklucza ją z wyboru", all(t.hour != 21 for t in DC.cheapest_slots(curve2, 5, 1.0)[0]))
    check("_ranges zwija kolejne godziny", DC._ranges([datetime(2026, 6, 11, h, 0, tzinfo=TZ) for h in (2, 3, 5)]) == "02:00–04:00, 05:00–06:00")

    # ---------- godziny z przerwami w sterowaniu (auto, termin 07:00)
    hass, c, rt = setup(mode="cheap", ctl_hours=3, ctl_power_w=2000, ctl_split=True, ctl_ready_h=7, category="ev")
    t0 = at(2026, 6, 10, 20, 0)
    rt._plan = {"curve": curve}
    await run(rt, t0, 30, hook=follow(hass))
    st = rt.dev_ctl.status()["devices"]["boj"]
    check("zestaw godzin wybrany raz: 02:00–03:00, 04:00–06:00", "02:00–03:00, 04:00–06:00" in (st["reason"] or ""), st)
    check("przed pierwszą godziną nic", sw_calls(hass) == [])
    # plan zmienia się w trakcie okresu — zestaw się nie przesuwa
    rt._plan = {"curve": dict(curve, buy=[0.9] * 30)}
    await run(rt, at(2026, 6, 11, 1, 55), 10, hook=follow(hass))
    check("02:00 → włączenie (mimo zmiany planu)", sw_calls(hass) == ["turn_on"], sw_calls(hass))
    await run(rt, at(2026, 6, 11, 2, 5), 60, hook=follow(hass))
    check("03:00 → wyłączenie (przerwa)", sw_calls(hass) == ["turn_on", "turn_off"], sw_calls(hass))
    await run(rt, at(2026, 6, 11, 3, 5), 65, hook=follow(hass))
    check("04:00 → ponowne włączenie", sw_calls(hass) == ["turn_on", "turn_off", "turn_on"], sw_calls(hass))
    await run(rt, at(2026, 6, 11, 4, 10), 120, hook=follow(hass))
    check("06:00 → koniec zestawu, wyłączone", sw_calls(hass) == ["turn_on", "turn_off", "turn_on", "turn_off"], sw_calls(hass))
    check("po zestawie: komunikat, że godziny minęły", "minęły" in (rt.dev_ctl.status()["devices"]["boj"]["reason"] or ""), rt.dev_ctl.status()["devices"]["boj"])
    # planer odświeża plan (od 08:00) — nowy zestaw dopiero po terminie 07:00
    rt._plan = {"curve": {"start": "2026-06-11T08:00:00+02:00", "pv": [0.0] * 30, "load": [0.5] * 30, "buy": [0.9] * 30, "sell": [0.3] * 30}}
    await run(rt, at(2026, 6, 11, 6, 15), 60, hook=follow(hass))       # nic więcej do terminu 07:00
    check("do terminu nie włącza ponownie", len(sw_calls(hass)) == 4, sw_calls(hass))
    await run(rt, at(2026, 6, 11, 7, 20), 2, hook=follow(hass))
    st = rt.dev_ctl.status()["devices"]["boj"]
    check("po terminie wybrany nowy zestaw na kolejną dobę", st["reason"] and "czeka na godziny" in st["reason"], st)

    # split bez terminu: okres 24 h od wyboru
    hass, c, rt = setup(mode="cheap", ctl_hours=2, ctl_power_w=2000, ctl_split=True)
    at(2026, 6, 10, 20, 0)
    rt._plan = {"curve": curve}
    await run(rt, at(2026, 6, 10, 20, 0), 3, hook=follow(hass))
    check("bez terminu: okres 24 h", rt.state["dev_ctl"]["boj"]["slots_end"].startswith("2026-06-11T20:0"), rt.state["dev_ctl"]["boj"])
    # brak planu
    hass, c, rt = setup(mode="cheap", ctl_split=True, ctl_ready_h=7)
    await run(rt, at(2026, 6, 10, 20, 0), 3)
    check("brak planu z cenami", "brak planu" in (rt.dev_ctl.status()["devices"]["boj"]["reason"] or ""))
    # uszkodzony zapis zestawu nie wywala sterowania
    hass, c, rt = setup(mode="cheap", ctl_split=True)
    rt._plan = {"curve": curve}
    rt.state["dev_ctl"] = {"boj": {"slots": ["śmieć", 5, None], "slots_end": "nie-data"}}
    try:
        await run(rt, at(2026, 6, 10, 20, 0), 3); ok = True
    except Exception as e:
        ok = False; print("wyjątek:", repr(e))
    check("uszkodzone pola zestawu godzin nie wywalają sterowania i są wybierane od nowa", ok and (rt.state["dev_ctl"]["boj"].get("slots") or [None])[0] != "śmieć")

    # zwykłe „najtańsze godziny” (ciągłe) z terminem
    hass, c, rt = setup(mode="cheap", ctl_hours=2, ctl_power_w=2000, ctl_ready_h=7)
    rt._plan = {"curve": curve}
    await run(rt, at(2026, 6, 10, 20, 0), 3)
    w = rt.dev_ctl.status()["devices"]["boj"]["window"]
    check("ciągłe okno z terminem kończy się przed 07:00", w and datetime.fromisoformat(w[1]) <= datetime(2026, 6, 11, 7, 0, tzinfo=TZ), w)

    print(f"DEVCTL_PRICE PASS={common.PASS} FAIL={common.FAIL}")

asyncio.run(main())
