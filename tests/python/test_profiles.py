"""Profile pracy (zima / lato / urlop): definicje, podgląd zmian, zastosowanie, cofnięcie, dryf, usługi i uprawnienia."""
import asyncio, json, sys, types
sys.path.insert(0, ".")
import common
from common import *   # noqa
from custom_components.bms_komp_dec import profiles as P, state_guard, const
import custom_components.bms_komp_dec as pkg
from stubs import HomeAssistantError, Unauthorized

NAN = float("nan")


def pure():
    ids = [p["id"] for p in P.PROFILES]
    check("trzy profile o unikalnych id", ids == ["winter", "summer", "vacation"] and len(set(ids)) == 3, ids)
    check("każdy profil ma nazwę, ikonę i opis", all(p["name"] and p["icon"] and len(p["desc"]) > 20 for p in P.PROFILES))
    bad = [(p["id"], k) for p in P.PROFILES for k, v in p["set"].items() if P.check_value(k, v) is None]
    check("wszystkie ustawienia profili istnieją i mieszczą się w zakresach encji", not bad, bad)
    check("profil nie zmienia tego samego ustawienia dwa razy", all(len(p["set"]) == len(set(p["set"])) for p in P.PROFILES))
    check("profile nie sięgają po ustawienia sprzętowe (czasy, prądy, moce)", not [k for p in P.PROFILES for k in p["set"]
          if k in ("normal_charge_current", "sell_export_power_w", "surplus_power_w", "grid_charge_power_kw", "grid_import_limit_kw", "inverter_floor_soc", "battery_charge_sign")])

    check("odmiana: ustawienie / ustawienia / ustawień", [P.settings_word(n) for n in (0, 1, 2, 4, 5, 11, 12, 14, 22, 25)]
          == ["0 ustawień", "1 ustawienie", "2 ustawienia", "4 ustawienia", "5 ustawień", "11 ustawień", "12 ustawień", "14 ustawień", "22 ustawienia", "25 ustawień"])
    check("get: znane i nieznane id", P.get("winter")["name"] == "Zima" and P.get("x") is None and P.get(None) is None and P.get(5) is None)
    check("kind", P.kind("vacation_mode") == "switch" and P.kind("reserve_floor_soc") == "number" and P.kind("nie_ma") is None)
    check("label i unit", P.label("reserve_floor_soc").startswith("Dynamiczna rezerwa") and P.unit("reserve_floor_soc") == "%" and P.label("nie_ma") == "nie_ma")

    # check_value
    check("przełącznik przyjmuje tylko bool", P.check_value("vacation_mode", True) is True and P.check_value("vacation_mode", 1) is None and P.check_value("vacation_mode", "on") is None)
    check("liczba w zakresie", P.check_value("reserve_floor_soc", 30) == 30.0 and P.check_value("reserve_floor_soc", 0) == 0.0 and P.check_value("reserve_floor_soc", 60) == 60.0)
    check("liczba poza zakresem / nan / inf / bool / napis → None", all(P.check_value("reserve_floor_soc", v) is None for v in (61, -1, NAN, float("inf"), True, "30", None)))
    check("nieznany klucz → None", P.check_value("nie_ma", 1) is None)

    # same / fmt
    check("same: liczby z tolerancją", P.same(30, 30.0) and P.same(0.1 + 0.2, 0.3) and not P.same(30, 31))
    check("same: bool nie równa się liczbie", not P.same(True, 1) and not P.same(0, False) and P.same(True, True) and not P.same(True, False))
    check("same: None / napis", not P.same(None, 1) and not P.same("x", 1))
    check("fmt: przełącznik, liczba z jednostką, brak", P.fmt("vacation_mode", True) == "włączone" and P.fmt("vacation_mode", False) == "wyłączone"
          and P.fmt("reserve_floor_soc", 30.0) == "30 %" and P.fmt("min_sell_margin", 0.25) == "0,25 PLN/kWh" and P.fmt("reserve_floor_soc", None) == "—")

    # changes / drifted
    vals = {"reserve_floor_soc": 15.0, "dawn_margin_soc": 15.0, "dynamic_reserve": False, "grid_charge_enabled": True, "pv_plan_pessimism_pct": None, "pv_forecast_correction": True}
    ch = {c["key"]: c for c in P.changes(P.get("winter"), vals.get)}
    check("changes: różni się, taka sama, niedostępna", ch["reserve_floor_soc"]["differs"] and ch["dynamic_reserve"]["differs"]
          and not ch["dawn_margin_soc"]["differs"] and not ch["grid_charge_enabled"]["differs"]
          and not ch["pv_plan_pessimism_pct"]["available"] and not ch["pv_plan_pessimism_pct"]["differs"], ch)
    check("changes: teksty przed i po", ch["reserve_floor_soc"]["now_text"] == "15 %" and ch["reserve_floor_soc"]["target_text"] == "30 %" and ch["dynamic_reserve"]["target_text"] == "włączone")
    check("drifted: brak zmian", P.drifted({"reserve_floor_soc": 30.0, "vacation_mode": True}, {"reserve_floor_soc": 30.0, "vacation_mode": True}.get) == [])
    check("drifted: zmieniona wartość i niedostępna encja", P.drifted({"reserve_floor_soc": 30.0, "vacation_mode": True, "x": 1}, {"reserve_floor_soc": 22.0, "vacation_mode": True}.get) == ["reserve_floor_soc", "x"])

    # clean_state
    good = {"id": "winter", "since": "2026-11-20T10:00:00+01:00", "prev": {"reserve_floor_soc": 15.0}, "applied": {"reserve_floor_soc": 30.0}, "ended": None}
    check("clean_state: poprawny zapis przechodzi", P.clean_state(good) == good, P.clean_state(good))
    for name, st in (("nie słownik", "x"), ("zły profil", dict(good, id="nie_ma")), ("brak daty", dict(good, since=5)), ("prev nie słownik", dict(good, prev=[1])),
                     ("applied pusty po czyszczeniu", dict(good, applied={"reserve_floor_soc": 999})), ("applied nan", dict(good, applied={"reserve_floor_soc": NAN}))):
        check(f"clean_state: {name} → None", P.clean_state(st) is None, st)
    st = P.clean_state(dict(good, prev={"reserve_floor_soc": 15.0, "nie_ma": 1, "dawn_margin_soc": 999, 5: 1}))
    check("clean_state: niepoprawne wartości prev są odrzucane pojedynczo", st["prev"] == {"reserve_floor_soc": 15.0}, st)
    st = P.clean_state(dict(good, ended={"at": "2026-11-20T11:00:00+01:00", "keys": ["a", 5, "b"]}))
    check("clean_state: ended zachowuje tylko napisy", st["ended"] == {"at": "2026-11-20T11:00:00+01:00", "keys": ["a", "b"]}, st["ended"])
    check("clean_state: ended w złym kształcie → None", P.clean_state(dict(good, ended="x"))["ended"] is None)


def nv(S, eid):
    """Liczbowa wartość encji (stub zapisuje stany jako napisy)."""
    return float(S.get(eid).state)


def logs(rt, text):
    return [e for e in rt.log.last(80) if text in str(e.get("msg", ""))]


async def runtime_part():
    # ---------- podgląd na domyślnych ustawieniach
    hass, c, opt, rt = build()
    S = hass.states
    v = rt.profile_view()
    check("widok: trzy profile, brak aktywnego", [p["id"] for p in v["profiles"]] == ["winter", "summer", "vacation"] and v["active"] is None, v["active"])
    w = next(p for p in v["profiles"] if p["id"] == "winter")
    wc = {x["key"]: x for x in w["changes"]}
    check("widok: Zima — rezerwa 15 → 30 %, dynamiczna rezerwa wyłączone → włączone",
          wc["reserve_floor_soc"]["now_text"] == "15 %" and wc["reserve_floor_soc"]["target_text"] == "30 %"
          and wc["dynamic_reserve"]["now_text"] == "wyłączone" and wc["dynamic_reserve"]["differs"], wc["reserve_floor_soc"])
    check("widok: ustawienie już zgodne nie jest oznaczone jako zmiana", not wc["grid_charge_enabled"]["differs"], wc["grid_charge_enabled"])
    check("widok: nic do zmiany = False przy różnicach", w["nothing_to_change"] is False)
    json.dumps(v, allow_nan=False)

    # ---------- zastosowanie: Zima
    res = await rt.apply_profile("winter")
    check("apply: zmieniono cztery ustawienia (dwa już były zgodne)", res["ok"] and res["changed"] == 4 and res["skipped"] == [], res)
    check("apply: stany encji", nv(S, "number.bms_reserve_floor_soc") == 30.0 and nv(S, "number.bms_dawn_margin_soc") == 15.0
          and nv(S, "number.bms_pv_plan_pessimism_pct") == 40.0 and S.get("switch.bms_dynamic_reserve").state == "on")
    pf = rt.state["profile"]
    check("apply: zapamiętano poprzednie wartości tylko zmienionych", pf["prev"] == {"reserve_floor_soc": 15.0, "dawn_margin_soc": 10.0, "pv_plan_pessimism_pct": 0.0, "dynamic_reserve": False}, pf["prev"])
    check("apply: applied zawiera też ustawienia, które były już zgodne", "grid_charge_enabled" in pf["applied"] and "pv_forecast_correction" in pf["applied"], pf["applied"])
    check("apply: wpis w dzienniku decyzji", len(logs(rt, "Włączono profil „Zima”: zmieniono 4 ustawienia")) == 1)
    v = rt.profile_view()
    check("widok po zastosowaniu: aktywny profil i lista do przywrócenia", v["active"]["id"] == "winter" and v["active"]["can_revert"] and len(v["active"]["restore"]) == 4
          and next(p for p in v["profiles"] if p["id"] == "winter")["active"] is True, v["active"])
    check("widok: w liście przywracania wartość teraz i wcześniej", any(r["key"] == "reserve_floor_soc" and r["now_text"] == "30 %" and r["prev_text"] == "15 %" for r in v["active"]["restore"]))
    json.dumps(v, allow_nan=False)
    await rt.profile_tick(at(2026, 11, 20, 12, 0))
    check("tick: bez zmian profil nadal obowiązuje", rt.state["profile"]["ended"] is None)

    # ---------- zmiana profilu: najpierw cofnięcie poprzedniego
    res = await rt.apply_profile("summer")
    check("zmiana Zima → Lato: wartości zimowe cofnięte, letnie ustawione", nv(S, "number.bms_reserve_floor_soc") == 15.0 and nv(S, "number.bms_pv_plan_pessimism_pct") == 0.0
          and S.get("switch.bms_dynamic_reserve").state == "off" and nv(S, "number.bms_min_soc_for_sell") == 40.0, [nv(S, f"number.bms_{k}") for k in ("reserve_floor_soc", "min_soc_for_sell")])
    check("zmiana profilu: baza to stan sprzed obu profili (min_soc_for_sell było 50)", rt.state["profile"]["id"] == "summer" and rt.state["profile"]["prev"].get("min_soc_for_sell") == 50.0, rt.state["profile"]["prev"])

    # ---------- ręczna zmiana po profilu → profil przestaje obowiązywać, powrót nie nadpisuje zmian ręcznych
    S.set("number.bms_min_soc_for_sell", 55)
    await rt.profile_tick(at(2026, 11, 20, 12, 5))
    pf = rt.state["profile"]
    check("tick: ręczna zmiana kończy profil, zapisuje które ustawienie", pf["ended"] and pf["ended"]["keys"] == ["min_soc_for_sell"], pf["ended"])
    check("tick: wpis w dzienniku o końcu profilu", len(logs(rt, "Profil „Lato” przestał obowiązywać")) == 1)
    v = rt.profile_view()
    check("widok: zakończony profil nie jest „aktywny”, ale można wrócić", next(p for p in v["profiles"] if p["id"] == "summer")["active"] is False and v["active"]["ended"] and v["active"]["can_revert"])
    await rt.profile_tick(at(2026, 11, 20, 12, 6))
    check("tick: drugi raz nie dubluje wpisu", len(logs(rt, "Profil „Lato” przestał obowiązywać")) == 1)
    S.set("number.bms_reserve_floor_soc", 15.0)
    res = await rt.revert_profile()
    check("revert: ręcznie zmienione zostaje (55), reszta wraca", nv(S, "number.bms_min_soc_for_sell") == 55 and res["kept"] and "Min SOC do sprzedaży 6000W" in res["kept"][0], res)
    check("revert: profil wyczyszczony, wpis w dzienniku", rt.state["profile"] is None and len(logs(rt, "Cofnięto profil „Lato”")) == 1)
    try:
        await rt.revert_profile(); e = False
    except ValueError:
        e = True
    check("revert bez profilu → ValueError", e)

    # ---------- pełny cykl: zastosuj i cofnij, wszystko wraca do początku
    hass, c, opt, rt = build()
    S = hass.states
    before = {k: nv(S, f"number.bms_{k}") for k in ("reserve_floor_soc", "dawn_margin_soc", "pv_plan_pessimism_pct")}
    sw_before = S.get("switch.bms_dynamic_reserve").state
    await rt.apply_profile("winter")
    res = await rt.revert_profile()
    after = {k: nv(S, f"number.bms_{k}") for k in before}
    check("zastosuj + cofnij: ustawienia jak na początku", after == before and S.get("switch.bms_dynamic_reserve").state == sw_before and res["restored"] == 4 and res["kept"] == [], (before, after, res))

    # ---------- niepoprawne wywołania
    try:
        await rt.apply_profile("nie_ma"); e = False
    except ValueError:
        e = True
    check("apply: nieznany profil → ValueError", e)
    try:
        await rt.apply_profile(None); e = False
    except ValueError:
        e = True
    check("apply: None → ValueError", e)

    # ---------- brak encji i zapis, który nie zadziałał
    hass, c, opt, rt = build()
    S = hass.states
    del S._s["number.bms_dawn_margin_soc"]
    hass.services.ignore.add("number.bms_pv_plan_pessimism_pct")
    res = await rt.apply_profile("winter")
    check("apply: brak encji i nieudany zapis → pominięte, reszta ustawiona", len(res["skipped"]) == 2 and res["changed"] == 2 and nv(S, "number.bms_reserve_floor_soc") == 30.0, res)
    check("apply: pominięte nie trafiają do prev/applied", "dawn_margin_soc" not in rt.state["profile"]["prev"] and "pv_plan_pessimism_pct" not in rt.state["profile"]["applied"], rt.state["profile"])
    check("apply: ostrzeżenie w dzienniku o pominiętych", any(e.get("level") == "warn" and "pominięto 2" in str(e.get("msg")) and "zmieniono 2 ustawienia" in str(e.get("msg")) for e in rt.log.last(40)))
    v = rt.profile_view()
    wc = {x["key"]: x for x in next(p for p in v["profiles"] if p["id"] == "winter")["changes"]}
    check("widok: niedostępne ustawienie oznaczone", wc["dawn_margin_soc"]["available"] is False and wc["dawn_margin_soc"]["now_text"] == "—")

    # ---------- urlop: włącza tryb urlopowy
    hass, c, opt, rt = build()
    S = hass.states
    res = await rt.apply_profile("vacation")
    check("urlop: tryb urlopowy włączony, sprzedaż z baterii włączona (domyślnie już była)", S.get("switch.bms_vacation_mode").state == "on" and S.get("switch.bms_sell_enabled").state == "on", res)
    check("urlop: zmieniono tylko to, co się różniło (1)", res["changed"] == 1, res)

    # ---------- uszkodzony zapis w stanie
    hass, c, opt, rt = build()
    rt.state["profile"] = {"id": "winter", "since": 5}
    await rt.profile_tick(at(2026, 11, 20, 12, 0))
    check("tick: uszkodzony zapis profilu jest czyszczony", rt.state["profile"] is None)
    rt.state["profile"] = "śmieć"
    check("widok: uszkodzony zapis nie wywala widoku", rt.profile_view()["active"] is None)
    st = {"profile": "śmieć"}
    fixed = state_guard.sanitize(st)
    check("state_guard: profil nie będący słownikiem → None", st["profile"] is None and "profile" in fixed, (st, fixed))
    st = {"profile": {"id": "winter"}}
    check("state_guard: słownik zostaje (czyści go profile_tick)", state_guard.sanitize(st) == [] and isinstance(st["profile"], dict))

    # ---------- usługi i uprawnienia
    hass, c, opt, rt = build()
    users = {"adm": types.SimpleNamespace(is_admin=True), "usr": types.SimpleNamespace(is_admin=False)}
    async def get_user(uid): return users.get(uid)
    hass.auth = types.SimpleNamespace(async_get_user=get_user)
    pkg._get_runtime = lambda h_: rt
    pkg._register_services(hass)
    H = {n: hh for (d, n), (hh, _r) in hass.services.handlers.items() if d == "bms_komp_dec"}
    check("usługi: profiles_get, profile_apply, profile_revert zarejestrowane", all(n in H for n in ("profiles_get", "profile_apply", "profile_revert")))
    def call(data, uid=None): return types.SimpleNamespace(data=data, context=types.SimpleNamespace(user_id=uid))
    r = await H["profiles_get"](call({}, "usr"))
    check("profiles_get: odczyt dla zwykłego użytkownika", len(r["profiles"]) == 3)
    for name, data in (("profile_apply", {"id": "winter"}), ("profile_revert", {})):
        try:
            await H[name](call(data, "usr")); ok_ = False
        except Unauthorized:
            ok_ = True
        check(f"usługi: {name} odrzuca użytkownika bez uprawnień admina", ok_)
    check("odrzucone wywołanie nic nie zmieniło", nv(hass.states, "number.bms_reserve_floor_soc") == 15 and rt.state.get("profile") is None)
    r = await H["profile_apply"](call({"id": "winter"}, "adm"))
    check("profile_apply: admin; odpowiedź zawiera nowy widok", r["ok"] and r["active"]["id"] == "winter" and len(r["profiles"]) == 3, r.get("active"))
    try:
        await H["profile_apply"](call({"id": "xx"}, "adm")); ok_ = False
    except HomeAssistantError:
        ok_ = True
    check("profile_apply: nieznany profil → HomeAssistantError", ok_)
    r = await H["profile_revert"](call({}, None))
    check("profile_revert: automatyzacja (bez użytkownika) cofa profil", r["ok"] and r["active"] is None and nv(hass.states, "number.bms_reserve_floor_soc") == 15.0, r)
    try:
        await H["profile_revert"](call({}, "adm")); ok_ = False
    except HomeAssistantError:
        ok_ = True
    check("profile_revert bez profilu → HomeAssistantError", ok_)


async def main():
    pure()
    await runtime_part()


asyncio.run(main())
print(f"PROFILES PASS={common.PASS} FAIL={common.FAIL}")
