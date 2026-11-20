"""Autokorekta ostrożności prognozy PV: czysta logika (próg, kierunek, wartość docelowa), propozycja z historii, zastosuj / cofnij / odrzuć, usługi."""
import asyncio, json, sys, types
from datetime import date, timedelta
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import pvcaution as PC, state_guard
import custom_components.bms_komp_dec as pkg
from stubs import HomeAssistantError, Unauthorized

TODAY = date(2026, 11, 20)


def pairs(n, f, a, start=1):
    return [((TODAY - timedelta(days=i)).isoformat(), f, a) for i in range(start, start + n)]


def pure():
    r = PC.evaluate(pairs(7, 10.0, 8.0), 0, TODAY)
    check("zawyżona prognoza (+25%) przy ostrożności 0: podwyżka o maks. 20 pkt", r and r["dir"] == "raise" and r["to"] == 20.0 and r["from"] == 0.0 and r["days"] == 7 and r["bias"] == 25.0, r)
    check("tekst: dni, błąd i wartości", r and "W 7 z ostatnich 7 dób" in r["text"] and "o 25%" in r["text"] and "z 0% do 20%" in r["text"], r and r["text"])
    check("wartość docelowa wyliczona z błędu (25% przy lo 0,7 → 65%)", r and abs(r["need"] - 66.7) < 0.1, r)
    r = PC.evaluate(pairs(7, 10.0, 8.0), 40, TODAY)
    check("z 40% proponuje 60% (krok 20), nie od razu 65%", r and r["to"] == 60.0, r)
    check("ostrożność już wystarczająca (65% ≈ potrzebne) → bez propozycji", PC.evaluate(pairs(7, 10.0, 8.0), 65, TODAY) is None)
    check("ostrożność 70% (maks.) → bez propozycji podwyżki", PC.evaluate(pairs(7, 10.0, 8.0), 70, TODAY) is None)
    r = PC.evaluate(pairs(7, 11.4, 10.0), 0, TODAY)
    check("zawyżenie 14%: cel ~40%, ale krok maks. 20", r and r["to"] == 20.0 and abs(r["need"] - 40.9) < 0.2, r)
    check("zawyżenie 11% (< 12%) → cisza", PC.evaluate(pairs(7, 11.1, 10.0), 0, TODAY) is None)
    check("lo 0,95: ostrożność prawie nic nie zmienia → bez propozycji", PC.evaluate(pairs(7, 10.0, 8.0), 0, TODAY, lo=0.95) is None)
    r = PC.evaluate(pairs(7, 10.0, 8.0), 0, TODAY, lo=0.5)
    check("lo 0,5: potrzeba (1−0,8)/(0,5)=40% → 20 (krok)", r and r["to"] == 20.0 and abs(r["need"] - 40.0) < 0.1 and r["lo"] == 0.5, r)
    check("lo śmieci → domyślne 0,7", PC.evaluate(pairs(7, 10.0, 8.0), 0, TODAY, lo="x")["lo"] == 0.7 and PC.evaluate(pairs(7, 10.0, 8.0), 0, TODAY, lo=float("nan"))["lo"] == 0.7
          and PC.evaluate(pairs(7, 10.0, 8.0), 0, TODAY, lo=5)["lo"] == 0.7)

    mixed = pairs(3, 10.0, 7.0) + pairs(4, 6.0, 10.0, start=4)
    check("dni w obie strony → cisza", PC.evaluate(mixed, 20, TODAY) is None)
    check("mniej niż 5 dób → cisza", PC.evaluate(pairs(4, 10.0, 7.0), 0, TODAY) is None)
    check("średnio zawyżone, ale tylko 2 z 7 dób wyraźnie → cisza", PC.evaluate(pairs(2, 20.0, 8.0) + pairs(5, 8.2, 8.0, start=3), 0, TODAY) is None)

    r = PC.evaluate(pairs(7, 6.0, 10.0), 40, TODAY)
    check("zaniżona prognoza (−40%) przy ostrożności 40%: obniżka do 20%", r and r["dir"] == "lower" and r["to"] == 20.0 and r["bad_days"] == 7 and r["bias"] == -40.0, r)
    check("tekst obniżki", r and "zmniejszyć ostrożność z 40% do 20%" in r["text"] and "o 40% za niska" in r["text"], r and r["text"])
    check("obniżka z 10% do 0%", PC.evaluate(pairs(7, 6.0, 10.0), 10, TODAY)["to"] == 0.0)
    check("ostrożność 0 i zaniżona prognoza → nic do obniżenia", PC.evaluate(pairs(7, 6.0, 10.0), 0, TODAY) is None)
    check("zaniżenie 18% (< 20%) → cisza", PC.evaluate(pairs(7, 8.2, 10.0), 40, TODAY) is None)

    check("bieżąca wartość niedostępna / spoza zakresu / nan → None", all(PC.evaluate(pairs(7, 10.0, 8.0), v, TODAY) is None for v in (None, "x", 150, -5, float("nan"), True)))
    check("dziś i przyszłość nie liczą się", PC.evaluate(pairs(7, 10.0, 8.0, start=-2)[:3] + pairs(2, 10.0, 8.0), 0, TODAY) is None)
    check("dni starsze niż 30 nie liczą się", PC.evaluate(pairs(7, 10.0, 8.0, start=40), 0, TODAY) is None)
    check("wykonanie < 0,5 kWh pomijane", PC.evaluate(pairs(7, 10.0, 0.3), 0, TODAY) is None)
    check("śmieci w parach pomijane, reszta liczona", PC.evaluate([("zła", 1, 1), None, (TODAY.isoformat(), 1, 1), ("2026-11-19", "x", 1), 5] + pairs(7, 10.0, 8.0), 0, TODAY)["days"] == 7)
    check("pairs None / nie lista → None", PC.evaluate(None, 0, TODAY) is None and PC.evaluate(5, 0, TODAY) is None)

    # uciszenie i czas na ustabilizowanie
    st = {"dismissed": (TODAY - timedelta(days=3)).isoformat(), "last": None}
    check("odrzucone 3 dni temu → cisza", PC.evaluate(pairs(7, 10.0, 8.0), 0, TODAY, st) is None)
    st = {"dismissed": (TODAY - timedelta(days=8)).isoformat(), "last": None}
    check("odrzucone 8 dni temu → znów proponuje", PC.evaluate(pairs(7, 10.0, 8.0), 0, TODAY, st) is not None)
    st = {"last": {"date": (TODAY - timedelta(days=1)).isoformat(), "from": 0.0, "to": 20.0, "reverted": False}}
    check("po zmianie wczoraj: cisza (3 doby na ustabilizowanie)", PC.evaluate(pairs(7, 10.0, 8.0), 20, TODAY, st) is None)
    st = {"last": {"date": (TODAY - timedelta(days=3)).isoformat(), "from": 0.0, "to": 20.0, "reverted": False}}
    r = PC.evaluate(pairs(7, 10.0, 8.0), 20, TODAY, st)
    check("po 3 dobach: kolejny krok 20 → 40", r and r["to"] == 40.0, r)

    # stan
    good = {"last": {"date": "2026-11-18", "from": 0, "to": 20, "reverted": False}, "dismissed": "2026-11-10"}
    check("clean_state: poprawny zapis przechodzi", PC.clean_state(good) == {"last": {"date": "2026-11-18", "from": 0.0, "to": 20.0, "reverted": False}, "dismissed": "2026-11-10"})
    for name, bad in (("nie słownik", "x"), ("None", None), ("liczba", 5), ("last nie słownik", {"last": 5}), ("zła data", {"last": {"date": "x", "from": 0, "to": 5}}),
                      ("from nan", {"last": {"date": "2026-11-18", "from": float("nan"), "to": 5}}), ("to poza zakresem", {"last": {"date": "2026-11-18", "from": 0, "to": 500}}),
                      ("dismissed śmieć", {"dismissed": "abc"})):
        c_ = PC.clean_state(bad)
        check(f"clean_state: {name} → pusty zapis", c_["last"] is None and c_["dismissed"] is None, c_)
    check("can_revert: wartość nadal nasza", PC.can_revert(good, 20) is not None and PC.can_revert(good, 20.0)["from"] == 0.0)
    check("can_revert: zmieniona ręcznie / cofnięta / brak encji → None", PC.can_revert(good, 25) is None and PC.can_revert(good, None) is None
          and PC.can_revert({"last": dict(good["last"], reverted=True)}, 20) is None and PC.can_revert({}, 20) is None)


def nv(S, eid):
    return float(S.get(eid).state)


def seed(rt, n, f, a, start=1):
    for i in range(start, start + n):
        rt.insights.fc[(TODAY - timedelta(days=i)).isoformat()] = {"pv_adj_by_h": {"1": f}, "pv_act": a}


async def runtime_part():
    at(2026, 11, 20, 10, 0)
    hass, c, opt, rt = build()
    S = hass.states
    v = rt.pv_caution()
    check("bez historii: brak propozycji, bieżąca 0, nic do cofnięcia", v["proposal"] is None and v["current"] == 0.0 and v["last"] is None and v["can_revert"] is False, v)
    seed(rt, 7, 10.0, 8.0)
    v = rt.pv_caution()
    check("z historią: propozycja podwyżki 0 → 20", v["proposal"] and v["proposal"]["dir"] == "raise" and v["proposal"]["to"] == 20.0, v)
    json.dumps(v, allow_nan=False)
    S.set("switch.bms_pv_forecast_correction", "off")
    check("korekta PV wyłączona: planer nie stosuje ostrożności → brak propozycji", rt.pv_caution()["proposal"] is None)
    S.set("switch.bms_pv_forecast_correction", "on")

    # zastosowanie
    res = await rt.pv_caution_apply()
    check("apply: ostrożność ustawiona na 20", res["ok"] and res["to"] == 20.0 and nv(S, "number.bms_pv_plan_pessimism_pct") == 20.0, res)
    check("apply: zapis ostatniej zmiany i wpis w dzienniku", rt.state["pv_caution"]["last"] == {"date": "2026-11-20", "from": 0.0, "to": 20.0, "reverted": False}
          and any("Ostrożność prognozy PV: 0% → 20%" in str(e.get("msg")) for e in rt.log.last(30)), rt.state.get("pv_caution"))
    v = rt.pv_caution()
    check("po zmianie: można cofnąć, propozycja wstrzymana na 3 doby", v["can_revert"] is True and v["last"]["to"] == 20.0 and v["proposal"] is None, v)
    try:
        await rt.pv_caution_apply(); e = False
    except ValueError:
        e = True
    check("apply bez propozycji → ValueError", e)

    # cofnięcie
    res = await rt.pv_caution_revert()
    check("revert: wraca 0, zapis oznaczony jako cofnięty, propozycja uciszona", res["to"] == 0.0 and nv(S, "number.bms_pv_plan_pessimism_pct") == 0.0
          and rt.state["pv_caution"]["last"]["reverted"] is True and rt.state["pv_caution"]["dismissed"] == "2026-11-20" and rt.pv_caution()["proposal"] is None, rt.state["pv_caution"])
    try:
        await rt.pv_caution_revert(); e = False
    except ValueError:
        e = True
    check("drugie cofnięcie → ValueError", e)

    # ręczna zmiana po zastosowaniu blokuje cofnięcie (ręczna wygrywa)
    hass, c, opt, rt = build(); S = hass.states
    seed(rt, 7, 10.0, 8.0)
    await rt.pv_caution_apply()
    S.set("number.bms_pv_plan_pessimism_pct", 35)
    check("po ręcznej zmianie nie można cofnąć", rt.pv_caution()["can_revert"] is False)
    try:
        await rt.pv_caution_revert(); e = False
    except ValueError:
        e = True
    check("revert po ręcznej zmianie → ValueError i wartość ręczna zostaje", e and nv(S, "number.bms_pv_plan_pessimism_pct") == 35.0)

    # odrzucenie
    hass, c, opt, rt = build(); S = hass.states
    seed(rt, 7, 10.0, 8.0)
    rt.pv_caution_dismiss()
    check("dismiss: propozycja uciszona, ustawienie bez zmian", rt.pv_caution()["proposal"] is None and nv(S, "number.bms_pv_plan_pessimism_pct") == 0.0 and rt.state["pv_caution"]["dismissed"] == "2026-11-20")
    at(2026, 11, 28, 10, 0)
    seed(rt, 7, 10.0, 8.0)       # (te same dni względem „dziś” — stare dni wypadają, nowe dochodzą)
    rt.insights.fc.clear(); globals()["TODAY"] = date(2026, 11, 28); seed(rt, 7, 10.0, 8.0)
    check("po 8 dobach znów proponuje", rt.pv_caution()["proposal"] is not None)
    globals()["TODAY"] = date(2026, 11, 20)
    at(2026, 11, 20, 10, 0)

    # zapis w pliku nie wywala widoku
    hass, c, opt, rt = build()
    rt.state["pv_caution"] = "śmieć"
    check("uszkodzony zapis: widok działa", rt.pv_caution()["last"] is None)
    st = {"pv_caution": "x"}
    fixed = state_guard.sanitize(st)
    check("state_guard: nie-słownik → {}", st["pv_caution"] == {} and "pv_caution" in fixed, (st, fixed))
    st = {"pv_caution": {"last": {"date": "x", "from": 1, "to": 2}, "dismissed": 5, "extra": 1}}
    fixed = state_guard.sanitize(st)
    check("state_guard: zła zawartość czyszczona", st["pv_caution"] == {"last": None, "dismissed": None} and "pv_caution" in fixed, st)
    st = {"pv_caution": {"last": {"date": "2026-11-18", "from": 0.0, "to": 20.0, "reverted": False}, "dismissed": None}}
    check("state_guard: poprawny zapis nietknięty", state_guard.sanitize(st) == [] and st["pv_caution"]["last"]["to"] == 20.0)

    # zapis, który nie działa
    hass, c, opt, rt = build(); S = hass.states
    seed(rt, 7, 10.0, 8.0)
    hass.services.ignore.add("number.bms_pv_plan_pessimism_pct")
    try:
        await rt.pv_caution_apply(); e = False
    except ValueError as err:
        e = "Nie udało się" in str(err)
    check("encja nie przyjmuje zapisu → ValueError i brak zapisu w stanie", e and not rt.state.get("pv_caution"), rt.state.get("pv_caution"))

    # aktywny profil nie uznaje zmiany autokorekty za ręczną
    hass, c, opt, rt = build(); S = hass.states
    await rt.apply_profile("winter")       # ostrożność 40
    seed(rt, 7, 10.0, 8.0)
    v = rt.pv_caution()
    check("przy profilu Zima (40%): propozycja 40 → 60", v["proposal"] and v["proposal"]["to"] == 60.0, v["proposal"])
    await rt.pv_caution_apply()
    await rt.profile_tick(at(2026, 11, 20, 11, 0))
    check("profil nadal obowiązuje po zmianie z autokorekty", rt.state["profile"]["ended"] is None and rt.state["profile"]["applied"]["pv_plan_pessimism_pct"] == 60.0, rt.state["profile"])
    await rt.pv_caution_revert()
    await rt.profile_tick(at(2026, 11, 20, 11, 5))
    check("po cofnięciu profil też obowiązuje (40)", rt.state["profile"]["ended"] is None and nv(S, "number.bms_pv_plan_pessimism_pct") == 40.0, rt.state["profile"])

    # powiadomienie o propozycji: rano, raz w tygodniu, wyłączalne
    from custom_components.bms_komp_dec import notify_cfg as N
    def pcn(hass_): return [x for x in hass_.services.calls if x[0] == "persistent_notification" and x[1] == "create" and "ostrożności prognozy PV" in x[2]["title"]]
    hass, c, opt, rt = build()
    seed(rt, 7, 10.0, 8.0)
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    await rt.monitor._pv_caution(at(2026, 11, 20, 8, 0))
    check("przed 9:00 cisza", not pcn(hass))
    await rt.monitor._pv_caution(at(2026, 11, 20, 9, 30))
    m = pcn(hass)
    check("rano: powiadomienie z propozycją i wskazówką gdzie zatwierdzić", len(m) == 1 and "z 0% do 20%" in m[0][2]["message"] and "Trafność prognoz" in m[0][2]["message"], m)
    await rt.monitor._pv_caution(at(2026, 11, 20, 15, 0)); await rt.monitor._pv_caution(at(2026, 11, 21, 10, 0))
    check("ta sama propozycja w tym samym tygodniu: bez powtórki", len(pcn(hass)) == 1, len(pcn(hass)))
    check("wpis w skrzynce panelu", any(i.get("kind") == "pv_caution" for i in rt.state.get("inbox", [])))
    hass, c, opt, rt = build()
    rt.state["notify_cfg"] = N.effective({"kinds": {"pv_caution": {"on": False}}, "phone_level": "all"})
    seed(rt, 7, 10.0, 8.0)
    await rt.monitor._pv_caution(at(2026, 11, 20, 9, 30))
    check("wyłączone w konfiguratorze → cisza", not pcn(hass))
    hass, c, opt, rt = build()
    rt.state["notify_cfg"] = N.effective({"phone_level": "all"})
    await rt.monitor._pv_caution(at(2026, 11, 20, 9, 30))
    check("brak propozycji → cisza", not pcn(hass))
    check("katalog: rodzaj pv_caution, info, raz w tygodniu, domyślnie bez telefonu", N.PRIORITY["pv_caution"] == 3 and N.CATALOG["pv_caution"][5] == 10080 and N.CATALOG["pv_caution"][4] is False and 10080 in N.COOLDOWNS)

    # usługi i uprawnienia
    hass, c, opt, rt = build()
    seed(rt, 7, 10.0, 8.0)
    users = {"adm": types.SimpleNamespace(is_admin=True), "usr": types.SimpleNamespace(is_admin=False)}
    async def get_user(uid): return users.get(uid)
    hass.auth = types.SimpleNamespace(async_get_user=get_user)
    pkg._get_runtime = lambda h_: rt
    pkg._register_services(hass)
    H = {n: hh for (d, n), (hh, _r) in hass.services.handlers.items() if d == "bms_komp_dec"}
    check("usługi zarejestrowane", all(n in H for n in ("pv_caution_apply", "pv_caution_revert", "pv_caution_dismiss")))
    def call(data, uid=None): return types.SimpleNamespace(data=data, context=types.SimpleNamespace(user_id=uid))
    for name in ("pv_caution_apply", "pv_caution_revert", "pv_caution_dismiss"):
        try:
            await H[name](call({}, "usr")); ok_ = False
        except Unauthorized:
            ok_ = True
        check(f"{name}: odrzuca zwykłego użytkownika", ok_)
    check("odrzucone wywołania nic nie zmieniły", nv(hass.states, "number.bms_pv_plan_pessimism_pct") == 0.0 and not rt.state.get("pv_caution"))
    r = await H["pv_caution_apply"](call({}, "adm"))
    check("apply (admin): odpowiedź z nowym widokiem", r["ok"] and r["pv_caution"]["can_revert"] and r["pv_caution"]["current"] == 20.0, r)
    r = await H["pv_caution_revert"](call({}, "adm"))
    check("revert (admin)", r["ok"] and r["pv_caution"]["current"] == 0.0 and not r["pv_caution"]["can_revert"], r)
    try:
        await H["pv_caution_revert"](call({}, "adm")); ok_ = False
    except HomeAssistantError:
        ok_ = True
    check("revert bez czego cofać → HomeAssistantError", ok_)
    r = await H["pv_caution_dismiss"](call({}, None))
    check("dismiss (automatyzacja bez użytkownika)", r["ok"] and r["pv_caution"]["proposal"] is None)
    try:
        await H["pv_caution_apply"](call({}, "adm")); ok_ = False
    except HomeAssistantError:
        ok_ = True
    check("apply bez propozycji → HomeAssistantError", ok_)
    ins = await H["insights_get"](call({}, "usr"))
    check("insights_get zawiera pv_caution dla każdego użytkownika", "pv_caution" in ins and ins["pv_caution"]["current"] == 0.0)
    json.dumps(ins["pv_caution"], allow_nan=False)


async def main():
    pure()
    await runtime_part()


asyncio.run(main())
print(f"PVCAUTION PASS={common.PASS} FAIL={common.FAIL}")
