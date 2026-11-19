"""Ceny zakupu na jutro (Pstryk, 19.11 o 16:25 „Jutro” puste): odczyt z „All prices”, z pozostałych encji integracji,
oraz czytelne wyjaśnienie, gdy jutra nie ma (jeszcze niepublikowane / integracja ma, ale encja nie wystawia / brak bez przyczyny)."""
import asyncio, json, sys
from datetime import date, timedelta
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import health as hlt, sensor as sens, diagnostics as DG, tariff as T

TODAY = [0.99, 0.95, 0.90, 0.88, 0.90, 0.95, 1.05, 1.20, 1.30, 1.10, 0.90, 0.84, 0.80, 0.82, 0.90, 1.40, 1.96, 1.80, 1.70, 1.50, 1.40, 1.30, 1.20, 1.16]
TOMOR = [0.70, 0.66, 0.62, 0.60, 0.63, 0.70, 0.90, 1.25, 1.40, 1.15, 0.80, 0.55, 0.50, 0.52, 0.70, 1.00, 1.60, 1.75, 1.65, 1.45, 1.30, 1.10, 0.95, 0.85]


def allp(d, f, tz="+01:00"):
    return [{"start": f"{d.isoformat()}T{h:02d}:00:00{tz}", "price": f(h), "is_cheap": False, "is_expensive": False} for h in range(24)]


def env(hour=16, tomorrow=True, flag=None, json_entity=False, extra_attrs=None, entity="sensor.pstryk_current_buy_price"):
    hass, c, opt, rt = build(); S = hass.states
    now = at(2026, 11, 19, hour, 25)
    d0 = now.date(); d1 = d0 + timedelta(days=1)
    lst = allp(d0, lambda h: TODAY[h]) + (allp(d1, lambda h: TOMOR[h]) if tomorrow else [])
    attrs = {"All prices": lst, "Best prices": lst[:3], "Worst prices": lst[3:6]}
    attrs.update(extra_attrs or {})
    S.set(entity, TODAY[hour], attrs)
    if flag is not None:
        S.set("sensor.pstryk_prices_fetched", "ok", {"tomorrow_available": flag})
    if json_entity:
        S.set("sensor.pstryk_json_buy", 0, {"prices_tomorrow": [{"time": f"{d1.isoformat()}T{h:02d}:00:00+01:00", "price": TOMOR[h]} for h in range(24)]})
    cfg = dict(const.SCHEDULER_DEFAULTS); cfg.update({"tariff_mode": "auto", "price_buy_entity": entity})
    sch = scheduler.ScheduleOptimizer(hass, c, cfg)
    T.set_profile(T.make_profile(cfg, prices_fn=sch.buy_hourly_for, eff_fn=lambda: 0.9, source="test"))
    rt.optimizer = sch; c.runtime = rt
    return hass, c, sch, rt, d0, d1


async def main():
    # 1) „All prices” zawiera dziś i jutro → tabela jutra pełna, bez wyjaśnień
    hass, c, sch, rt, d0, d1 = env()
    b1 = sch.buy_hourly_for(d1)
    check("All prices z jutrem: 24 ceny na jutro, zgodne z listą", b1 and all(abs(b1[h] - TOMOR[h]) < 1e-9 for h in range(24)), b1)
    check("All prices z jutrem: źródło to All prices", "All prices" in (sch.buy_report()["tomorrow"]["source"] or ""), sch.buy_report().get("tomorrow"))
    st = sch.buy_tomorrow_status()
    check("All prices z jutrem: stan ok, bez tekstu", st == {"state": "ok", "text": None}, st)
    a = sens.BmsRuntimeSensor._price_attrs(rt)
    check("atrybuty sensora: jutro jest, notatki brak", a.get("prices_buy_tomorrow") and a.get("price_buy_tomorrow_state") == "ok" and a.get("price_buy_tomorrow_note") is None, a.get("price_buy_tomorrow_state"))

    # 2) lista bez jutra, integracja mówi „jutro jeszcze nie pobrane” (godz. 16:25)
    hass, c, sch, rt, d0, d1 = env(tomorrow=False, flag=False)
    check("bez jutra: brak cen na jutro", not sch.buy_hourly_for(d1))
    st = sch.buy_tomorrow_status()
    check("tomorrow_available=false → waiting, tekst o publikacji", st["state"] == "waiting" and "nie zostały jeszcze opublikowane" in st["text"] and "przeliczy" in st["text"], st)
    a = sens.BmsRuntimeSensor._price_attrs(rt)
    json.dumps(a, allow_nan=False)
    check("atrybuty sensora: stan i notatka trafiają na kartę", a.get("price_buy_tomorrow_state") == "waiting" and "opublikowane" in (a.get("price_buy_tomorrow_note") or "") and a.get("prices_buy_tomorrow") is None, a)

    # 3) integracja twierdzi, że jutro ma, a encja go nie pokazuje → konkretna wskazówka
    hass, c, sch, rt, d0, d1 = env(tomorrow=False, flag=True)
    st = sch.buy_tomorrow_status()
    check("tomorrow_available=true, a encja bez jutra → not_exposed", st["state"] == "not_exposed", st)
    check("…tekst wskazuje sensor.pstryk_json_buy i to, co widać w encji (All prices[24])", "sensor.pstryk_json_buy" in st["text"] and "All prices[24]" in st["text"] and "sensor.pstryk_current_buy_price" in st["text"], st["text"])
    chk = {x["id"]: x for x in hlt.health_check(rt)["checks"]}
    check("autotest: taryfa nadal OK, ale w opisie jest wyjaśnienie jutra", chk["tariff"]["status"] == "ok" and "Na jutro:" in chk["tariff"]["detail"] and "pstryk_json_buy" in chk["tariff"]["detail"], chk["tariff"])

    # 3b) prawdziwe atrybuty z instalacji użytkownika (19.11, 16:32): „All prices” = tylko dziś (24, godziny bez strefy czasowej),
    #     flaga „Tomorrow prices available: true”, „MQTT price count: 48” — jutra w tej encji po prostu nie ma
    REAL = [1.03, 0.99, 0.96, 1, 1.07, 1.15, 1.7, 1.56, 1.57, 1.47, 1.3, 1.4, 1.64, 1.53, 1.69, 2.36, 2.43, 2.41, 2.28, 2.16, 2.07, 1.84, 1.32, 1.2]
    hass, c, sch, rt, d0, d1 = env(hour=16, tomorrow=False)
    ent = [{"start": f"{d0.isoformat()}T{h:02d}:00:00", "price": REAL[h]} for h in range(24)]
    hass.states.set("sensor.pstryk_current_buy_price", 2.43, {"state_class": "measurement", "unit_of_measurement": "PLN/kWh",
        "friendly_name": "Pstryk Energy Pstryk Current Buy Price", "Average price today /8": 1.96, "Average price today /24": 1.59, "Next hour": 2.41,
        "All prices": ent, "Best prices": sorted(ent, key=lambda x: x["price"]), "Worst prices": sorted(ent, key=lambda x: -x["price"]),
        "Best count": 24, "Worst count": 24, "Price count": 24, "Last updated": "2026-11-19 16:32:39", "Using cached data": False,
        "Tomorrow prices available": True, "MQTT price count": 48, "Is cheap": False, "Is expensive": True, "mqtt_48h_mode": True})
    b0 = sch.buy_hourly_for(d0)
    check("prawdziwe atrybuty: dziś 24 godziny z „All prices” (start bez strefy), 16:00 = 2,43", b0 and len([v for v in b0 if v is not None]) == 24 and abs(b0[16] - 2.43) < 1e-9 and abs(b0[2] - 0.96) < 1e-9, b0)
    check("prawdziwe atrybuty: jutra w encji nie ma", not sch.buy_hourly_for(d1))
    check("prawdziwe atrybuty: flaga „Tomorrow prices available” rozpoznana", sch._tomorrow_published() is True)
    st = sch.buy_tomorrow_status()
    check("prawdziwe atrybuty: not_exposed, instrukcja włączenia sensorów JSON (nazwa opcji) i co widać w encji",
          st["state"] == "not_exposed" and "Włącz sensory JSON z cenami" in st["text"] and "All prices[24]" in st["text"] and "wystawia tylko dzisiejszą dobę" in st["text"], st)
    # po włączeniu sensorów JSON jutro jest czytane samo, bez żadnej zmiany w EMS
    hass.states.set("sensor.pstryk_json_buy", 2.43, {"prices_today": [{"time": f"{d0.isoformat()}T{h:02d}:00:00+01:00", "price": REAL[h]} for h in range(24)],
                                                     "prices_tomorrow": [{"time": f"{d1.isoformat()}T{h:02d}:00:00+01:00", "price": TOMOR[h], "tge_price": 0.5, "is_cheap": False} for h in range(24)]})
    b1 = sch.buy_hourly_for(d1)
    check("po włączeniu sensorów JSON: jutro z sensor.pstryk_json_buy, stan ok", b1 and abs(b1[12] - TOMOR[12]) < 1e-9 and sch.buy_tomorrow_status()["state"] == "ok", sch.buy_report().get("tomorrow"))
    # sensor JSON jest, ale bez jutra, a integracja twierdzi, że je ma → inny komunikat (nie każ włączać tego, co już włączone)
    hass.states.set("sensor.pstryk_json_buy", 2.43, {"prices_today": [{"time": f"{d0.isoformat()}T{h:02d}:00:00+01:00", "price": REAL[h]} for h in range(24)], "prices_tomorrow": []})
    st = sch.buy_tomorrow_status()
    check("sensor JSON bez prices_tomorrow: komunikat o sprawdzeniu atrybutów, bez „włącz”", st["state"] == "not_exposed" and "niepustą listę prices_tomorrow" in st["text"] and "Włącz sensory JSON" not in st["text"], st)
    # warianty zapisu flagi
    for key in ("tomorrow_available", "Tomorrow available", "tomorrow-prices-available"):
        hass2, c2, sch2, rt2, e0, e1 = env(tomorrow=False)
        hass2.states.set("sensor.pstryk_prices_fetched", "ok", {key: False})
        check(f"flaga zapisana jako „{key}” rozpoznana", sch2._tomorrow_published() is False, key)

    # 3c) druga instalacja użytkownika (ten sam zrzut co na karcie: 10:00 = 0,84 minimum, 16:00 = 1,96) — identyczna sytuacja
    REAL2 = [0.99, 0.95, 0.92, 0.96, 1.03, 1.11, 1.24, 1.1, 1.11, 1.01, 0.84, 0.94, 1.18, 1.49, 1.65, 1.9, 1.96, 1.95, 1.82, 1.7, 1.61, 1.37, 1.28, 1.16]
    hass, c, sch, rt, d0, d1 = env(hour=16, tomorrow=False)
    ent2 = [{"start": f"{d0.isoformat()}T{h:02d}:00:00", "price": REAL2[h]} for h in range(24)]
    hass.states.set("sensor.pstryk_current_buy_price", 1.96, {"Average price today /8": 1.61, "All prices": ent2, "Best prices": sorted(ent2, key=lambda x: x["price"])[:5],
        "Worst prices": sorted(ent2, key=lambda x: -x["price"])[:5], "Best count": 5, "Worst count": 5, "Price count": 24, "Last updated": "2026-11-19 16:00:05",
        "Using cached data": True, "Tomorrow prices available": True, "MQTT price count": 48, "mqtt_48h_mode": True, "friendly_name": "Pstryk Current Buy Price"})
    b0 = sch.buy_hourly_for(d0)
    st = sch.buy_tomorrow_status()
    check("druga instalacja: dziś jak na karcie (min 0,84 o 10:00, 16:00 = 1,96), jutra brak, stan not_exposed",
          b0 and abs(b0[10] - 0.84) < 1e-9 and abs(b0[16] - 1.96) < 1e-9 and min(b0) == b0[10] and not sch.buy_hourly_for(d1) and st["state"] == "not_exposed" and "Włącz sensory JSON z cenami" in st["text"], (b0 and b0[10], st))

    # 4) brak flagi: rano „czekamy”, po południu „brak bez przyczyny”
    hass, c, sch, rt, d0, d1 = env(hour=10, tomorrow=False)
    st = sch.buy_tomorrow_status()
    check("bez flagi, 10:25 → waiting", st["state"] == "waiting", st)
    hass, c, sch, rt, d0, d1 = env(hour=16, tomorrow=False)
    st = sch.buy_tomorrow_status()
    check("bez flagi, 16:25 → missing, z listą widzianych atrybutów i podpowiedzią", st["state"] == "missing" and "All prices[24]" in st["text"] and "tomorrow_available" in st["text"], st)
    chk = {x["id"]: x for x in hlt.health_check(rt)["checks"]}
    check("autotest: stan missing też opisany (bez zmiany statusu na błąd)", chk["tariff"]["status"] == "ok" and "Na jutro:" in chk["tariff"]["detail"], chk["tariff"])
    hass, c, sch, rt, d0, d1 = env(hour=10, tomorrow=False, flag=False)
    chk = {x["id"]: x for x in hlt.health_check(rt)["checks"]}
    check("autotest: samo oczekiwanie na publikację nie jest alarmem", "Na jutro:" not in chk["tariff"]["detail"], chk["tariff"]["detail"])

    # 5) jutro pojawia się po chwili → od razu czytane, stan ok (bez starej pamięci podręcznej)
    hass, c, sch, rt, d0, d1 = env(tomorrow=False, flag=False)
    check("przed publikacją: brak jutra", not sch.buy_hourly_for(d1) and sch.buy_tomorrow_status()["state"] == "waiting")
    lst = allp(d0, lambda h: TODAY[h]) + allp(d1, lambda h: TOMOR[h])
    hass.states.set("sensor.pstryk_current_buy_price", 1.96, {"All prices": lst})
    hass.states.set("sensor.pstryk_prices_fetched", "ok", {"tomorrow_available": True})
    b1 = sch.buy_hourly_for(d1)
    check("po publikacji: ceny na jutro widoczne od razu, stan ok", b1 and abs(b1[12] - TOMOR[12]) < 1e-9 and sch.buy_tomorrow_status()["state"] == "ok", b1)

    # 6) jutro w innej encji tej samej integracji (nazwa nieznana z góry) — odkrywana po prefiksie
    d1_ = date(2026, 11, 20)
    hass, c, sch, rt, d0, d1 = env(tomorrow=False, flag=True, extra_attrs={})
    hass.states.set("sensor.pstryk_buy_price_hourly", 1.0, {"Prices": allp(d1, lambda h: TOMOR[h])})
    b1 = sch.buy_hourly_for(d1)
    check("encja pstryk_* o nieznanej nazwie z listą jutra jest odkrywana", b1 and abs(b1[3] - TOMOR[3]) < 1e-9 and "pstryk_buy_price_hourly" in (sch.buy_report()["tomorrow"]["source"] or ""), sch.buy_report().get("tomorrow"))
    check("…a dziś nadal z encji zakupu (pełniejsze pokrycie)", abs((sch.buy_hourly_for(d0) or [0] * 24)[16] - 1.96) < 1e-9)
    # encje SPRZEDAŻY Pstryka nigdy nie stają się cenami zakupu
    hass, c, sch, rt, d0, d1 = env(tomorrow=False, flag=True)
    hass.states.set("sensor.pstryk_current_sell_price", 0.4, {"All prices": allp(d1, lambda h: 0.3)})
    hass.states.set("sensor.pstryk_json_sell", 0, {"prices_tomorrow": allp(d1, lambda h: 0.3)})
    check("sprzedaż Pstryka nie jest źródłem cen zakupu", not sch.buy_hourly_for(d1) and not any("sell" in e for e in sch._buy_entities()), sch._buy_entities())

    # 7) sensor json (opcjonalny) z prices_tomorrow wystarcza
    hass, c, sch, rt, d0, d1 = env(tomorrow=False, flag=True, json_entity=True)
    b1 = sch.buy_hourly_for(d1)
    check("sensor.pstryk_json_buy z prices_tomorrow → jutro odczytane", b1 and abs(b1[17] - TOMOR[17]) < 1e-9 and sch.buy_tomorrow_status()["state"] == "ok", b1)

    # 8) inne źródło (G12w z energy_hub): bez odkrywania pstryk_*, flaga nieznana
    hass, c, sch, rt, d0, d1 = env(entity="sensor.energy_hub_aktualna_cena_g12w", tomorrow=False)
    hass.states.set("sensor.pstryk_prices_fetched", "ok", {"tomorrow_available": True})
    check("źródło spoza Pstryka: flaga „tomorrow_available” ignorowana", sch._tomorrow_published() is None and sch._buy_entities() == ["sensor.energy_hub_aktualna_cena_g12w"], sch._buy_entities())

    # 9) flaga jako tekst („true”/„false”) i śmieci
    hass, c, sch, rt, d0, d1 = env(tomorrow=False)
    hass.states.set("sensor.pstryk_prices_fetched", "ok", {"tomorrow_available": "False"})
    check("flaga jako tekst „False” → False", sch._tomorrow_published() is False)
    hass.states.set("sensor.pstryk_prices_fetched", "ok", {"tomorrow_available": "kto wie"})
    check("flaga nieczytelna → None", sch._tomorrow_published() is None)

    # 10) raport do zgłoszenia ma sekcję cen z widzianymi atrybutami
    hass, c, sch, rt, d0, d1 = env(tomorrow=False, flag=True)
    out = await DG.async_build_report(rt)
    txt = out["text"]
    check("raport: sekcja „Źródła cen” z atrybutami encji zakupu", "== Źródła cen" in txt and "All prices[24]" in txt and "sensor.pstryk_current_buy_price" in txt, txt[txt.find("== Źródła cen"):][:600])
    check("raport: stan cen na jutro (not_exposed)", '"zakup_jutro"' in txt and "not_exposed" in txt)
    print(f"BUY TOMORROW PASS={common.PASS} FAIL={common.FAIL}")


asyncio.run(main())
